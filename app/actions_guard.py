"""Reject paid-runner workflows before a managed Git push can trigger them."""
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import yaml


def validate(workflow, files):
    if not isinstance(workflow, dict) or not isinstance(workflow.get('jobs'), dict):
        raise ValueError('Workflow must declare jobs')
    for job in workflow['jobs'].values():
        if not isinstance(job, dict):
            raise ValueError('Invalid workflow job')
        if 'uses' in job:
            target = job['uses']
            if not isinstance(target, str) or not target.startswith('./.github/workflows/') or target[2:] not in files:
                raise ValueError('Only checked local reusable workflows are allowed')
            continue
        labels = job.get('runs-on')
        if isinstance(labels, dict):
            labels = labels.get('labels')
        if (not isinstance(labels, list) or any(not isinstance(label, str) for label in labels)
                or not {'self-hosted', 'windows', 'x64', 'codexpi'} <= {label.lower() for label in labels}):
            raise ValueError('Every job must select [self-hosted, Windows, X64, codexpi]; no hosted fallback')


def check(commit):
    result = subprocess.run(['git', '-c', 'core.quotepath=false', 'ls-tree', '-r', '--name-only', commit,
                             '--', '.github/workflows'], check=True, capture_output=True, text=True)
    files = {name for name in result.stdout.splitlines() if name.endswith(('.yml', '.yaml'))}
    for name in sorted(files):
        content = subprocess.check_output(['git', 'show', commit + ':' + name], text=True)
        try:
            validate(yaml.safe_load(content), files)
        except yaml.YAMLError:
            raise ValueError(name + ': invalid YAML; push refused') from None
        except ValueError as exc:
            raise ValueError(name + ': ' + str(exc)) from None


def install(path):
    path = Path(path)
    custom = subprocess.run(['git', 'config', '--get', 'core.hooksPath'], cwd=path,
                            capture_output=True, text=True)
    if custom.stdout.strip():
        effective = Path(custom.stdout.strip())
        if not effective.is_absolute():
            effective = path / effective
        if effective.exists():
            raise ValueError('Existing custom Git hook path must be integrated before enabling managed pushes')
        # Keep the user's global config intact; only shadow a missing path in this managed repo.
        backup = path / '.git/config.before-actions-guard'
        if not backup.exists():
            shutil.copy2(path / '.git/config', backup)
        subprocess.run(['git', 'config', '--local', 'core.hooksPath', '.git/hooks'], cwd=path, check=True)
    hook = path / '.git/hooks/pre-push'
    marker = '# CodexPi local Actions admission'
    if hook.exists() and marker not in hook.read_text():
        raise ValueError('Existing pre-push hook must be integrated; preserving it')
    hook.parent.mkdir(parents=True, exist_ok=True)
    from .common import atomic_write
    atomic_write(hook, '#!/bin/sh\n' + marker + '\nexec ' + shlex.quote(Path(sys.executable).as_posix())
                 + ' ' + shlex.quote(Path(__file__).resolve().as_posix()) + '\n', 0o700)


if __name__ == '__main__':
    try:
        if len(sys.argv) == 3 and sys.argv[1] == 'install':
            install(sys.argv[2])
        else:
            checked = set()
            for line in sys.stdin:
                local_ref, commit, remote_ref, remote_commit = line.split()
                if set(commit) == {'0'} or commit in checked:
                    continue
                check(commit)
                checked.add(commit)
    except (ValueError, subprocess.SubprocessError) as exc:
        print('CodexPi Actions admission: ' + str(exc), file=sys.stderr)
        sys.exit(1)
