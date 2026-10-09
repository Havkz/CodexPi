"""Observe real local GitHub jobs before admitting lower-priority Windows work."""
import json
import time


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
    try:
        for repo in sorted(repos):
            runners = json.loads((await command('gh', 'api', 'repos/' + repo + '/actions/runners',
                                               timeout=20))['stdout'])['runners']
            local = {r['id'] for r in runners if r['os'] == 'Windows'
                     and any(label['name'] == 'codexpi' for label in r['labels'])}
            if not local:
                raise RuntimeError('No configured CodexPi Windows runner for ' + repo)
            for status in ('queued', 'in_progress', 'waiting', 'requested', 'pending'):
                pages = json.loads((await command('gh', 'api', '--paginate', '--slurp',
                    'repos/' + repo + '/actions/runs?status=' + status + '&per_page=100', timeout=20))['stdout'])
                for page in pages:
                    for run in page['workflow_runs']:
                        job_pages = json.loads((await command('gh', 'api', '--paginate', '--slurp',
                            'repos/' + repo + '/actions/runs/' + str(run['id']) + '/jobs?per_page=100',
                            timeout=20))['stdout'])
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
                            if not any(j['job_id'] == job['id'] and j['repo'] == repo for j in jobs):
                                jobs.append(observation)
        # Publish only a complete observation: a partial API failure is never "idle".
        controller.db.set_setting('github_actions', {'checked_at': time.time(), 'jobs': jobs})
        controller.health_errors.pop('github_actions', None)
    except Exception as exc:
        error = controller.redactor.clean(str(exc))
        state = controller.db.setting('github_actions', {})
        state.update(error=error, checked_at=time.time())
        controller.db.set_setting('github_actions', state)
        controller.health_errors['github_actions'] = error
