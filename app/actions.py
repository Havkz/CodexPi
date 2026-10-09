"""Observe real local GitHub jobs before admitting lower-priority Windows work."""
import json
import time
import uuid


def registrations(controller):
    return [(p, controller.db.setting('actions_registration/' + p['project_id'], {}))
            for p in controller.db.all() if p['lifecycle'] == 'ready' and p['github_repo']]


async def register(controller, project):
    from .power import request_wake
    from .worker_server import send
    project = controller.db.get(project['project_id'])
    if project['lifecycle'] != 'ready':
        raise RuntimeError('Project lifecycle must finish before runner registration')
    key = 'actions_registration/' + project['project_id']
    state = controller.db.setting(key, {})
    now = time.time()
    if not state or state.get('repo') != project['github_repo']:
        state = {'id': str(uuid.uuid4()), 'repo': project['github_repo'], 'phase': 'pending', 'requested_at': now}
        controller.db.set_setting(key, state)
    if state['phase'] in ('sent', 'pending', 'registered') and now - state['requested_at'] > 900:
        state.update(phase='failed', error='Windows runner registration was not confirmed within 15 minutes; inspect the worker before retrying')
        controller.db.set_setting(key, state)
    if state['phase'] == 'failed':
        raise RuntimeError(state['error'])
    if not controller.windows_online:
        if controller.db.setting('auto_boot_windows', False):
            request_wake(controller, ['github-actions-setup', project['github_repo'], state['id']])
        raise RuntimeError('Windows runner registration is waiting for the authenticated Windows worker: ' + project['github_repo'])
    if state['phase'] == 'pending' and not controller.db.conn.execute(
            "SELECT 1 FROM jobs WHERE status IN ('sent','running')").fetchone():
        if any(other.get('phase') == 'sent' and other.get('id') != state['id'] for p, other in registrations(controller)):
            raise RuntimeError('Windows runner registration is queued behind another setup')
        state['phase'] = 'sent'
        controller.db.set_setting(key, state)
        try:
            await send(controller, {'type': 'actions_setup', 'id': state['id'], 'repo': state['repo'],
                                    'project_id': project['project_id']})
        except (ConnectionError, ValueError):
            pass  # Only a signed reconnect inventory can authorize redelivery.
    raise RuntimeError('Windows runner setup is awaiting GitHub confirmation: ' + project['github_repo'])


def setup_result(controller, body):
    if (not isinstance(body.get('job_id'), str) or not isinstance(body.get('repo'), str)
            or not isinstance(body.get('result'), dict) or type(body['result'].get('exit_code')) is not int
            or not isinstance(body['result'].get('stderr'), str)):
        raise ValueError('Invalid Actions setup result')
    for project, state in registrations(controller):
        if state.get('id') == body['job_id'] and state.get('repo') == body['repo']:
            if state['phase'] != 'sent':
                return
            if body['result']['exit_code'] == 0:
                state['phase'] = 'registered'  # GitHub's actual runner observation owns final confirmation.
            else:
                state.update(phase='failed', error=controller.redactor.clean(body['result']['stderr'])
                             or 'Windows runner setup failed; inspect the worker before retrying')
            controller.db.set_setting('actions_registration/' + project['project_id'], state)
            return


def setup_inventory(controller, present):
    if (not isinstance(present, list) or len(present) > 1000 or
            any(not isinstance(ident, str) for ident in present)):
        raise ValueError('Invalid Actions setup inventory')
    for project, state in registrations(controller):
        if state.get('phase') == 'sent' and state['id'] not in present:
            state['phase'] = 'pending'
            controller.db.set_setting('actions_registration/' + project['project_id'], state)


def busy(controller):
    if not controller.db.setting('self_hosted_actions', False):
        return False
    state = controller.db.setting('github_actions', {})
    return bool(state.get('error') or not state.get('checked_at')
                or time.time() - state['checked_at'] > 90 or state.get('jobs'))


async def poll(controller):
    if not controller.db.setting('self_hosted_actions', False):
        return
    from .controller import command
    now = time.time()
    if now - controller.db.setting('github_actions', {}).get('checked_at', 0) < 30:
        return
    repos = {controller.config['github_account'] + '/CodexPi'}
    repos.update(p['github_repo'] for p in controller.db.all()
                 if p['github_repo'] and p['lifecycle'] == 'ready')
    jobs = []
    previous = controller.db.setting('github_actions', {})
    first_seen = previous.get('first_seen', {})
    try:
        for repo in sorted(repos):
            runners = json.loads((await command('gh', 'api', '--header', 'Cache-Control: no-cache',
                                               'repos/' + repo + '/actions/runners',
                                               timeout=20))['stdout'])['runners']
            local = {r['id'] for r in runners if r['os'] == 'Windows'
                     and any(label['name'] == 'codexpi' for label in r['labels'])}
            if not local:
                project = next((p for p in controller.db.all() if p['github_repo'] == repo and p['lifecycle'] == 'ready'), None)
                if project:
                    await register(controller, project)
                raise RuntimeError('No configured CodexPi Windows runner for ' + repo)
            for project, registration in registrations(controller):
                if (project['github_repo'] == repo and registration.get('phase') != 'ready' and registration
                        and any(r['id'] in local and r.get('status') == 'online' for r in runners)):
                    registration.update(phase='ready', confirmed_at=now)
                    controller.db.set_setting('actions_registration/' + project['project_id'], registration)
            for status in ('queued', 'in_progress', 'waiting', 'requested', 'pending'):
                pages = json.loads((await command('gh', 'api', '--header', 'Cache-Control: no-cache', '--paginate', '--slurp',
                    'repos/' + repo + '/actions/runs?status=' + status + '&per_page=100', timeout=20))['stdout'])
                for page in pages:
                    for run in page['workflow_runs']:
                        job_pages = json.loads((await command('gh', 'api', '--header', 'Cache-Control: no-cache', '--paginate', '--slurp',
                            'repos/' + repo + '/actions/runs/' + str(run['id']) + '/jobs?per_page=100',
                            timeout=20))['stdout'])
                        if not any(p['jobs'] for p in job_pages):
                            raise RuntimeError('GitHub has not exposed the local jobs for active run ' + repo + ' / ' + str(run['id']))
                        for job in (j for p in job_pages for j in p['jobs']):
                            if job['status'] == 'completed':
                                continue
                            labels = {label.lower() for label in job['labels']}
                            if not {'self-hosted', 'windows', 'codexpi'} <= labels:
                                raise RuntimeError('Non-local GitHub job detected in ' + repo + ': ' + job['name'])
                            if job.get('runner_id') and job['runner_id'] not in local:
                                raise RuntimeError('GitHub job is assigned to an unexpected runner in ' + repo)
                            observation = {'repo': repo, 'run_id': run['id'], 'job_id': job['id'],
                                           'status': job['status'], 'runner_id': job.get('runner_id')}
                            key = repo + '/' + str(job['id'])
                            first_seen.setdefault(key, now)
                            if not any(j['job_id'] == job['id'] and j['repo'] == repo for j in jobs):
                                jobs.append(observation)
        executing = any(j['status'] == 'in_progress' and j['runner_id'] for j in jobs)
        for job in jobs:
            if job['status'] != 'queued':
                continue
            key = job['repo'] + '/' + str(job['job_id'])
            if executing:
                first_seen[key] = now  # A busy local PC is queueing normally, not a failed runner pickup.
            elif now - first_seen[key] > 900:
                raise TimeoutError('Local GitHub job was not picked up within 15 minutes: ' +
                                   job['repo'] + ' / job ' + str(job['job_id']))
        # Publish only a complete observation: a partial API failure is never "idle".
        keys = {j['repo'] + '/' + str(j['job_id']) for j in jobs}
        controller.db.set_setting('github_actions', {'checked_at': time.time(), 'jobs': jobs,
            'first_seen': {key: first_seen[key] for key in keys}})
        controller.health_errors.pop('github_actions', None)
    except Exception as exc:
        error = controller.redactor.clean(str(exc))
        state = controller.db.setting('github_actions', {})
        state.update(error=error, checked_at=time.time(), first_seen=first_seen)
        controller.db.set_setting('github_actions', state)
        controller.health_errors['github_actions'] = error
