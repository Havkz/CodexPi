"""Register the official Windows services for explicitly selected private CodexPi repos."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def configure_hooks(names):
    directory = ROOT / 'actions-coordination'
    directory.mkdir(parents=True, exist_ok=True)
    user = os.environ['USERDOMAIN'] + '\\' + os.environ['USERNAME']
    subprocess.run(['icacls', str(directory), '/inheritance:r', '/grant:r',
                    '*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F',
                    '*S-1-5-20:(OI)(CI)M', user + ':(OI)(CI)M'],
                   check=True, capture_output=True)
    manifest = directory / 'repositories.json'
    previous = json.loads(manifest.read_text()) if manifest.exists() else []
    candidate = directory / ('repositories-' + str(os.getpid()) + '.tmp')
    candidate.write_text(json.dumps(sorted(set(previous + names))), encoding='utf-8')
    os.replace(candidate, manifest)
    linux = ROOT / 'actions-linux'
    linux.mkdir(parents=True, exist_ok=True)
    subprocess.run(['icacls', str(linux), '/inheritance:r', '/grant:r',
                    '*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F',
                    '*S-1-5-20:(OI)(CI)M'], check=True, capture_output=True)
    for name in names:
        destination = ROOT / 'actions-runner' / name.split('/')[1].lower()
        config = json.loads((destination / '.runner').read_text(encoding='utf-8-sig'))
        runner = next((r for r in gh('repos/' + name + '/actions/runners')['runners']
                       if r['id'] == config['agentId']), None)
        if not runner or runner['busy']:
            raise RuntimeError('Runner is absent or executing a job; do not restart it')
        environment = destination / '.env'
        values = {
            'ACTIONS_RUNNER_HOOK_JOB_STARTED': str(ROOT / 'Setup/actions-job-start.ps1'),
            'ACTIONS_RUNNER_HOOK_JOB_COMPLETED': str(ROOT / 'Setup/actions-job-finish.ps1'),
            'PSExecutionPolicyPreference': 'RemoteSigned',
            'PATH': str(Path(sys.executable).parent) + ';C:\\Program Files\\PowerShell\\7;'
                    'C:\\Program Files\\Git\\bin;' + os.environ['PATH'],
        }
        lines = environment.read_text(encoding='utf-8').splitlines() if environment.exists() else []
        text = '\n'.join([line for line in lines if line.partition('=')[0] not in values]
                         + [key + '=' + value for key, value in values.items()]) + '\n'
        if environment.exists() and environment.read_text(encoding='utf-8') == text:
            continue
        if environment.exists():
            shutil.copy2(environment, destination / ('.env.before-codexpi-' + str(time.time_ns())))
        environment.write_text(text, encoding='utf-8')
        service = (destination / '.service').read_text(encoding='utf-8-sig').strip()
        if not re.fullmatch(r'actions\.runner\.[A-Za-z0-9_.-]+', service):
            raise ValueError('Unexpected Windows runner service identity')
        subprocess.run(['powershell', '-NoProfile', '-Command',
                        "Restart-Service -Name '" + service + "' -ErrorAction Stop"],
                       check=True, capture_output=True, text=True, timeout=60)
        print(name + ': CI priority hooks configured; service restarted while idle')


def gh(*args):
    result = subprocess.run(['gh', 'api', *args], capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError('GitHub API request failed: ' + result.stderr.strip())
    return json.loads(result.stdout)


def validate_repository(name, data):
    if (not re.fullmatch(r'Havkz/[A-Za-z0-9_.-]+', name)
            or data.get('full_name', '').lower() != name.lower()
            or not data.get('private') or data.get('archived')
            or (name.lower() != 'havkz/codexpi' and not re.fullmatch(
                r'Managed by CodexPi project [0-9a-f-]{36}', data.get('description') or ''))):
        raise ValueError('Runner registration requires an explicitly selected private CodexPi repository')


def install(name, release, *, label='codexpi-setup', project_id=None):
    repository = gh('repos/' + name)
    validate_repository(name, repository)
    if project_id and repository.get('description') != 'Managed by CodexPi project ' + project_id:
        raise ValueError('GitHub repository does not match the requested CodexPi project identity')
    destination = ROOT / 'actions-runner' / name.split('/')[1].lower()
    destination.mkdir(parents=True, exist_ok=True)
    runner_config = destination / '.runner'
    if runner_config.exists():
        existing = json.loads(runner_config.read_text(encoding='utf-8-sig'))
        if existing.get('gitHubUrl', '').rstrip('/').lower() != ('https://github.com/' + name).lower():
            raise ValueError('Existing runner belongs to a different repository; preserving it')
        service = destination / '.service'
        if not service.exists():
            raise RuntimeError('Existing runner has no pre-login Windows service; preserving registration')
        print(name + ': existing service ' + service.read_text(encoding='utf-8-sig').strip())
        return
    if any(destination.iterdir()):
        raise RuntimeError('Unregistered runner directory is not empty; inspect before retrying')
    asset = next(a for a in release['assets'] if re.fullmatch(
        r'actions-runner-win-x64-[0-9.]+\.zip', a['name']))
    digest = asset.get('digest', '')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
        raise RuntimeError('Official runner release has no SHA-256 digest; refusing unverified install')
    cache = ROOT / 'actions-runner' / asset['name']
    if not cache.exists():
        urllib.request.urlretrieve(asset['browser_download_url'], cache)
    with cache.open('rb') as source:
        verified_digest = hashlib.file_digest(source, 'sha256').hexdigest()
    if verified_digest != digest.split(':')[1]:
        raise RuntimeError('Official runner archive SHA-256 verification failed')
    # Runner credentials must not inherit the personal PC's generic Users read access.
    subprocess.run(['icacls', str(destination), '/inheritance:r', '/grant:r',
                    '*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F',
                    '*S-1-5-20:(OI)(CI)F'], check=True, capture_output=True)
    with zipfile.ZipFile(cache) as archive:
        if any(not (destination / p.filename).resolve().is_relative_to(destination.resolve())
               for p in archive.infolist()):
            raise RuntimeError('Runner archive contains an escaping path')
        archive.extractall(destination)
    token = gh('--method', 'POST', 'repos/' + name + '/actions/runners/registration-token')['token']
    env = {**os.environ, 'ACTIONS_RUNNER_INPUT_TOKEN': token}
    # The official runner consumes and masks this environment input; never put it in argv.
    try:
        result = subprocess.run([str(destination / 'bin/Runner.Listener.exe'), 'configure',
            '--unattended', '--url', 'https://github.com/' + name,
            '--name', 'codexpi-windows-' + name.split('/')[1].lower(),
            '--labels', label, '--work', '_work', '--runasservice',
            '--windowslogonaccount', 'NT AUTHORITY\\NETWORK SERVICE'],
            cwd=destination, env=env, capture_output=True, text=True, timeout=180)
        output = (result.stdout + result.stderr).replace(token, '[REDACTED]')
        if result.returncode:
            raise RuntimeError('Runner configuration failed: ' + output[-4000:])
    finally:
        env.pop('ACTIONS_RUNNER_INPUT_TOKEN', None)
    print(name + ': installed ' + release['tag_name'] + ', service ' +
          (destination / '.service').read_text(encoding='utf-8-sig').strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repositories', nargs='+')
    parser.add_argument('--activate', action='store_true')
    parser.add_argument('--project-id')
    args = parser.parse_args()
    if args.project_id and (len(args.repositories) != 1 or not re.fullmatch('[0-9a-f-]{36}', args.project_id)):
        raise ValueError('Automatic registration requires exactly one immutable project identity')
    if os.name != 'nt' or not ctypes.windll.shell32.IsUserAnAdmin():
        raise RuntimeError('Official Windows runner service installation requires an Administrator terminal')
    release = gh('repos/actions/runner/releases/latest')
    for name in args.repositories:
        install(name, release, project_id=args.project_id)
    configure_hooks(args.repositories)
    if args.activate:
        for name in args.repositories:
            config = json.loads((ROOT / 'actions-runner' / name.split('/')[1].lower() / '.runner').read_text(encoding='utf-8-sig'))
            result = subprocess.run(['gh', 'api', '--method', 'PUT',
                'repos/' + name + '/actions/runners/' + str(config['agentId']) + '/labels', '--input', '-'],
                input=json.dumps({'labels': ['codexpi', 'codexpi-setup']}), text=True, capture_output=True, timeout=60)
            if result.returncode:
                raise RuntimeError('Runner activation failed: ' + result.stderr)
            print(name + ': local CI label activated')


if __name__ == '__main__':
    main()
