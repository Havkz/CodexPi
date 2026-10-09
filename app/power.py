"""One journaled WoL boot; power commands use the existing signed worker channel."""
import ipaddress
import json
import math
import re
import socket
import time
import uuid


def target(value, lan):
    if (not isinstance(value, dict) or not isinstance(value.get('mac'), str)
            or not re.fullmatch(r'(?:[0-9A-F]{2}-){5}[0-9A-F]{2}', value['mac'])):
        raise ValueError('Windows WoL network adapter is not configured')
    network = ipaddress.ip_network(lan)
    address = ipaddress.ip_address(value.get('address', ''))
    if network.version != 4 or address not in network or address in (network.network_address, network.broadcast_address):
        raise ValueError('Windows WoL target must be inside the configured LAN')
    return value['mac'], str(network.broadcast_address)


def wake(mac, broadcast):
    packet = b'\xff' * 6 + bytes.fromhex(mac.replace('-', '')) * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        sender.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sender.sendto(packet, (broadcast, 9))


def public_state(controller):
    state = controller.db.setting('windows_power', {})
    return {'auto_boot_windows': controller.db.setting('auto_boot_windows', False),
            'windows_power': {key: state[key] for key in ('phase', 'message', 'requested_at') if key in state}}


def eligible(controller):
    if controller.db.setting('pause_all', False) or controller.account_switch_pending:
        return None
    selected = controller.db.setting('selected')
    for project in controller.db.all():
        reason = json.loads(project['block_reason'] or '{}')
        if (project['queue_position'] == 1 and selected in (None, project['project_id'])
                and project['goal_status'] == 'stalled' and project['windows_required']
                and reason.get('reason') == 'Windows offline' and reason.get('requires_user') is False
                and controller.can_auto_resume(project)):
            return project


async def tick(controller):
    from .worker_server import send
    db, now = controller.db, time.time()
    state = db.setting('windows_power', {})
    if not db.setting('auto_boot_windows', False):
        return
    if state.get('phase') in ('waking', 'claiming'):
        if now > state['requested_at'] + 600:
            state.update(phase='failed', message='Windows wake timed out; no confirmed boot worker. Check power, WoL and the startup task.')
            db.set_setting('windows_power', state)
        return
    if state.get('phase') == 'shutdown_sent':
        if controller.windows_online and now > state['shutdown_at'] + 60:
            state.update(phase='failed', message='Windows is still online after the shutdown request; no automatic retry.')
            db.set_setting('windows_power', state)
        if controller.windows_online or not eligible(controller):
            return
        # A new Windows requirement may wake it again, without claiming the last shutdown succeeded.
    if state.get('phase') == 'owned':
        if not controller.windows_online:
            return  # Loss of heartbeat is neither power-off proof nor a shutdown permission.
        if db.conn.execute("SELECT 1 FROM jobs WHERE status IN ('pending','sent','running')").fetchone() or eligible(controller):
            state.pop('idle_since', None)
            db.set_setting('windows_power', state)
            return
        latest = db.conn.execute('SELECT project_id,updated_at FROM jobs ORDER BY updated_at DESC LIMIT 1').fetchone()
        ident = latest['project_id'] if latest and latest['updated_at'] >= state['requested_at'] else state['trigger'][0]
        project = next((p for p in db.all() if p['project_id'] == ident), None)
        if project:
            thread = (await controller.native.rpc('thread/read', {'threadId': project['codex_session_id'], 'includeTurns': False}))['thread']
            if (thread['id'] != project['codex_session_id'] or thread['cwd'] != project['project_path']
                    or thread['status']['type'] == 'active'):
                state.pop('idle_since', None)
                db.set_setting('windows_power', state)
                return
        state.setdefault('idle_since', now)
        if now - state['idle_since'] < 600:
            db.set_setting('windows_power', state)
            return
        state.update(phase='shutdown_sent', shutdown_at=now,
                     message='Shutdown requested for the CodexPi-owned boot; physical power-off is not inferred from an absent heartbeat.')
        db.set_setting('windows_power', state)  # Never repeat an ambiguously delivered power command.
        try:
            await send(controller, {'type': 'power_shutdown', 'id': state['id'], 'boot_at': state['boot_at'], 'expires_at': now + 30})
        except (ConnectionError, ValueError):
            state.update(phase='failed', message='Shutdown delivery is uncertain; inspect Windows. No automatic retry.')
            db.set_setting('windows_power', state)
        return
    if controller.windows_online:
        return
    project = eligible(controller)
    if not project:
        return
    event = db.conn.execute("SELECT MAX(event_id) FROM events WHERE project_id=? AND kind='stalled'",
                           (project['project_id'],)).fetchone()[0]
    trigger = [project['project_id'], project['codex_session_id'], event]
    request_wake(controller, trigger)


def request_wake(controller, trigger):
    db, now = controller.db, time.time()
    state = db.setting('windows_power', {})
    if state.get('phase') in ('waking', 'claiming') or state.get('trigger') == trigger:
        return state
    telemetry = db.setting('windows_power_observation', {})
    state = {'id': str(uuid.uuid4()), 'trigger': trigger, 'requested_at': now, 'phase': 'waking',
             'previous_boot': telemetry.get('boot_at'), 'message': 'Wake-on-LAN sent; waiting for the authenticated Windows boot worker.'}
    try:
        mac, broadcast = target(telemetry, controller.config['lan_subnet'])
        if not telemetry.get('startup_ready') or not state['previous_boot']:
            raise ValueError('Windows pre-login worker setup is incomplete; install the password-backed startup task first')
        db.set_setting('windows_power', state)
        wake(mac, broadcast)
    except (OSError, ValueError) as exc:
        state.update(phase='failed', message=str(exc))
        db.set_setting('windows_power', state)
    return state


async def observe(controller, observation):
    from .worker_server import send
    if (not isinstance(observation, dict) or type(observation.get('boot_at')) not in (int, float)
            or not math.isfinite(observation['boot_at'])
            or not 0 < observation['boot_at'] <= time.time() + 30
            or type(observation.get('startup_ready')) is not bool
            or type(observation.get('user_active')) is not bool
            or type(observation.get('boot_worker')) is not bool):
        raise ValueError('Invalid Windows power observation')
    target(observation, controller.config['lan_subnet'])
    controller.db.set_setting('windows_power_observation', {k: observation[k] for k in
        ('mac', 'address', 'boot_at', 'startup_ready', 'user_active', 'boot_worker')})
    state = controller.db.setting('windows_power', {})
    if state.get('phase') == 'owned' and (observation['boot_at'] != state.get('boot_at') or observation['user_active']):
        state.update(phase='released', message='Windows boot changed or a user logged in; automatic shutdown has been cancelled.')
        controller.db.set_setting('windows_power', state)
    if (state.get('phase') not in ('waking', 'claiming') or not controller.db.setting('auto_boot_windows', False)
            or time.time() > state['requested_at'] + 600):
        return
    if state.get('claim_attempts', 0) >= 2 or time.time() - state.get('claim_sent_at', 0) < 30:
        return
    state.update(phase='claiming', claim_sent_at=time.time(), claim_attempts=state.get('claim_attempts', 0) + 1,
                 message='Windows is online; checking boot ownership before allowing automatic shutdown.')
    controller.db.set_setting('windows_power', state)
    await send(controller, {'type': 'power_claim', 'id': state['id'], 'requested_at': state['requested_at'],
                            'previous_boot': state['previous_boot']})


def result(controller, body):
    state = controller.db.setting('windows_power', {})
    if (not isinstance(body.get('id'), str) or body['id'] != state.get('id')
            or type(body.get('accepted')) is not bool or body.get('command') not in ('claim', 'shutdown')):
        raise ValueError('Invalid Windows power acknowledgement')
    if state.get('phase') == 'claiming' and body.get('command') == 'claim':
        if (body['accepted'] and type(body.get('boot_at')) in (int, float) and math.isfinite(body['boot_at'])
                and state['previous_boot'] <= body['boot_at'] <= time.time()):
            state.update(phase='owned', boot_at=body['boot_at'], message='CodexPi boot confirmed; Windows stays on until related work is idle.')
        else:
            state.update(phase='released', message='No confirmed CodexPi network-wake ownership (or user activity); Windows will remain on.')
        controller.db.set_setting('windows_power', state)
    elif state.get('phase') == 'shutdown_sent' and body.get('command') == 'shutdown' and not body['accepted']:
        state.update(phase='released', message='The worker refused shutdown because ownership or idle checks no longer hold. Windows remains on.')
        controller.db.set_setting('windows_power', state)
