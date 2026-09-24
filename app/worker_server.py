import asyncio
import json
import re
import secrets
import time
import uuid
from pathlib import PureWindowsPath

from aiohttp import WSMsgType, web

from .common import SignedChannel, atomic_write
from .controller import command


async def send(controller, body):
    async with controller.worker_send_lock:
        if not controller.windows_online:
            raise ValueError('Windows offline')
        await controller.worker.send_json(controller.worker_key.sign(body))


async def worker_socket(request):
    controller = request.app['controller']
    socket = web.WebSocketResponse(max_msg_size=12 * 1024 * 1024, autoping=True)
    await socket.prepare(request)
    challenge = secrets.token_hex(32)
    channel = SignedChannel(controller.config['worker_secret'], challenge, 'controller')
    await socket.send_json({'challenge': challenge})
    try:
        packet = await asyncio.wait_for(socket.receive_json(), 10)
        body = channel.verify(packet)
        if body != {'type': 'hello'}:
            raise ValueError('Invalid worker handshake')
        # A single live authenticated worker connection is permitted.
        if controller.worker is not None and not controller.worker.closed:
            await controller.worker.close(code=1000, message=b'replaced by authenticated reconnect')
        controller.worker = socket
        controller.worker_key = channel
        controller.worker_seen = 0  # only a signed alive message establishes online status
        async def reply(body):
            async with controller.worker_send_lock:
                await socket.send_json(channel.sign(body))

        await reply({'type': 'accepted'})
        reconciled = False
        async for packet in socket:
            if packet.type != WSMsgType.TEXT:
                continue
            body = channel.verify(json.loads(packet.data))
            if body.get('type') == 'inventory' and not reconciled:
                inventory = body.get('jobs')
                if (not isinstance(inventory, list) or len(inventory) > 10000 or
                        any(not isinstance(item, dict) or not isinstance(item.get('job_id'), str)
                            or item.get('status') not in ('running', 'finished') for item in inventory)):
                    raise ValueError('Invalid worker inventory')
                present = {item['job_id'] for item in inventory}
                # Absent jobs were never durably accepted. Same-ID delivery is idempotent at the worker.
                with controller.db.transaction():
                    for row in controller.db.conn.execute("SELECT job_id FROM jobs WHERE status IN ('sent','running')"):
                        if row['job_id'] not in present:
                            controller.db.conn.execute("UPDATE jobs SET status='pending',updated_at=? WHERE job_id=?",
                                                      (time.time(), row['job_id']))
                reconciled = True
            elif body == {'type': 'alive'} and reconciled:
                was_online = controller.windows_online
                controller.worker_seen = time.monotonic()
                if not was_online:
                    await unblock_windows(controller)
                await dispatch_pending(controller)
            elif body.get('type') == 'result':
                job = controller.db.conn.execute('SELECT * FROM jobs WHERE job_id=?', (body.get('job_id'),)).fetchone()
                if job is None:
                    raise ValueError('Unknown job result')
                result = body.get('result')
                if (not isinstance(result, dict) or not isinstance(result.get('stdout'), str)
                        or not isinstance(result.get('stderr'), str) or type(result.get('exit_code')) is not int
                        or not isinstance(result.get('artifacts'), list)):
                    raise ValueError('Invalid job result')
                result = json.loads(controller.redactor.clean(json.dumps(result)))
                if job['status'] == 'finished' and json.loads(job['result']) != result:
                    raise ValueError('Conflicting result for a completed job')
                controller.db.conn.execute('UPDATE jobs SET status=?,result=?,updated_at=? WHERE job_id=?',
                                          ('finished', json.dumps(result), time.time(), job['job_id']))
                await reply({'type': 'ack', 'job_id': job['job_id']})
                await dispatch_pending(controller)
            elif body.get('type') == 'started':
                controller.db.conn.execute('UPDATE jobs SET status=?,updated_at=? WHERE job_id=? AND status=?',
                                          ('running', time.time(), body['job_id'], 'sent'))
            else:
                raise ValueError('Unknown worker message')
    except (ValueError, asyncio.TimeoutError, ConnectionError):
        await socket.close(code=1008, message=b'worker protocol rejected')
    finally:
        if controller.worker is socket:
            controller.worker = None
            controller.worker_seen = 0
    return socket


async def dispatch_pending(controller):
    job = controller.db.conn.execute('SELECT * FROM jobs WHERE status=? ORDER BY created_at LIMIT 1', ('pending',)).fetchone()
    if job is None or controller.db.conn.execute('SELECT 1 FROM jobs WHERE status IN (?,?)', ('sent', 'running')).fetchone():
        return
    controller.db.conn.execute('UPDATE jobs SET status=?,updated_at=? WHERE job_id=?', ('sent', time.time(), job['job_id']))
    await send(controller, {'type': 'job', 'job_id': job['job_id'], **json.loads(job['payload'])})


async def unblock_windows(controller):
    async with controller.lock:
        if controller.db.setting('pause_all', False):
            return
        for project in controller.db.all():
            reason = json.loads(project['block_reason'] or '{}')
            if (project['goal_status'] != 'stalled' or reason.get('reason') != 'Windows offline'
                    or reason.get('requires_user') is not False or not project['windows_required']
                    or project['operation'] or project['queue_position'] != 1 or not controller.can_auto_resume(project)):
                continue
            selected = controller.db.setting('selected')
            if selected and selected != project['project_id']:
                continue
            controller.select(project['project_id'])
            controller.db.update(project['project_id'], operation=json.dumps({'kind': 'resume', 'source': 'windows',
                'id': str(uuid.uuid4()), 'requested_at': time.time()}), resume_result=None)
            return


async def submit_job(controller, body):
    async with controller.lock:
        return await _submit_job(controller, body)


async def _submit_job(controller, body):
    project = controller.db.get(body['project_id'])
    if project['lifecycle'] != 'ready':
        raise ValueError('Project lifecycle operation is in progress')
    if not controller.windows_online:
        reason = {'reason': 'Windows offline', 'details': str(body.get('reason', 'Native Windows test required')),
                  'requires_user': False}
        clean = controller.redactor.clean(json.dumps(reason))
        atomic_write(__import__('pathlib').Path(project['project_path']) / '.codexpi/block.json', clean)
        await controller.native.rpc('thread/goal/set', {'threadId': project['codex_session_id'], 'status': 'blocked'})
        with controller.db.transaction():
            controller.db.update(project['project_id'], goal_status='stalled', windows_required=1, block_reason=clean)
            controller.db.event(project['project_id'], 'stalled', {'reason': clean})
        raise ValueError('Windows offline')
    argv, commit = body.get('argv'), body.get('commit')
    if (not isinstance(argv, list) or not argv or len(argv) > 128 or
            any(not isinstance(a, str) or '\x00' in a or len(a) > 65536 for a in argv)):
        raise ValueError('argv must be a nonempty list of strings')
    if not isinstance(commit, str) or not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('An exact 40-character pushed commit SHA is required')
    timeout = body.get('timeout', 900)
    if type(timeout) is not int or not 1 <= timeout <= 7200:
        raise ValueError('Job timeout must be 1-7200 seconds')
    artifacts = body.get('artifacts', [])
    if (not isinstance(artifacts, list) or len(artifacts) > 128 or any(
            not isinstance(p, str) or not p or '\x00' in p or ':' in p or
            PureWindowsPath(p).drive or PureWindowsPath(p).root or '..' in PureWindowsPath(p).parts
            for p in artifacts)):
        raise ValueError('Artifact paths must be relative to the project checkout')
    await command('gh', 'api', 'repos/' + project['github_repo'] + '/commits/' + commit, '--jq', '.sha')
    payload = {'repo': project['github_repo'], 'slug': project['slug'], 'commit': commit,
               'argv': argv, 'timeout': timeout, 'artifacts': artifacts}
    ident = str(uuid.uuid4())
    controller.db.conn.execute('INSERT INTO jobs(job_id,project_id,payload,created_at,updated_at) VALUES (?,?,?,?,?)',
                              (ident, project['project_id'], json.dumps(payload), time.time(), time.time()))
    await dispatch_pending(controller)
    return {'job_id': ident}
