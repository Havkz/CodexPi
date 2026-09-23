"""Pi-only sandbox prerequisite and filesystem enforcement smoke test; no AI turn."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    bwrap = shutil.which('bwrap')
    assert bwrap == '/usr/bin/bwrap', bwrap
    subprocess.run([bwrap, '--ro-bind', '/', '/', '--unshare-user', '--unshare-pid',
                    '--proc', '/proc', '--dev', '/dev', '--die-with-parent', '/usr/bin/true'], check=True)
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='sandbox-check-', dir=root / 'state') as directory:
        test = Path(directory)
        workspace = test / 'workspace'
        workspace.mkdir()
        script = '''from pathlib import Path
import errno
import sys
Path('allowed').write_text('sandbox-check')
try:
    Path(sys.argv[1]).write_text('must-be-denied')
except OSError as exc:
    assert exc.errno in (errno.EACCES, errno.EPERM, errno.EROFS), exc
    print('WORKSPACE_WRITE_AND_OUTSIDE_DENIAL_OK')
else:
    raise AssertionError('Sandbox allowed a write outside its workspace')
'''
        result = subprocess.run(['/home/raspberry/.local/bin/codex', 'sandbox', '-P', ':workspace',
            '-C', str(workspace), '--', '/usr/bin/python3', '-c', script, str(test / 'outside')],
            capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        assert (workspace / 'allowed').read_text() == 'sandbox-check'
        assert not (test / 'outside').exists()
        assert 'could not find bubblewrap' not in result.stderr
        print(json.dumps({'bwrap': bwrap, 'namespace': 'passed', 'codex_sandbox': result.stdout.strip(),
                          'apparmor_restriction': Path('/proc/sys/kernel/apparmor_restrict_unprivileged_userns').read_text().strip()}))


if __name__ == '__main__':
    main()
