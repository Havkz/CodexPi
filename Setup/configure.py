"""Run on Pi after copying reviewed sources; preserve and back up user config."""
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.common import atomic_write, read_env

root = Path('/home/raspberry/CodexPi')
home = Path('/home/raspberry')
backup = root / 'backups' / ('configure-' + time.strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True, exist_ok=True)


def preserve(path):
    if path.exists():
        destination = backup / path.relative_to(home)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


env = read_env(root / '.env')
if not env.get('DISCORD_BOT_TOKEN'):
    raise SystemExit('Discord token must be supplied using the masked setup dialog')
if not env.get('WORKER_SECRET'):
    env['WORKER_SECRET'] = secrets.token_hex(32)
    preserve(root / '.env')
    atomic_write(root / '.env', ''.join(f'{key}={value}\n' for key, value in env.items()))
os.chmod(root / '.env', 0o600)
ponytail = home / '.config/ponytail/config.json'
preserve(ponytail)
values = json.loads(ponytail.read_text()) if ponytail.exists() else {}
values['defaultMode'] = 'full'
atomic_write(ponytail, json.dumps(values, indent=2) + '\n')
hooks = home / '.codex/hooks.json'
preserve(hooks)
values = json.loads(hooks.read_text()) if hooks.exists() else {'hooks': {}}
for event in ('SessionStart', 'UserPromptSubmit', 'PostToolUse', 'Stop'):
    groups = values.setdefault('hooks', {}).setdefault(event, [])
    command = '/usr/bin/python3 /home/raspberry/CodexPi/Setup/goal-hook.py'
    if event == 'UserPromptSubmit':
        command += ' --snapshot-only'
    if not any(handler.get('command') == command for group in groups for handler in group.get('hooks', [])):
        groups.insert(0, {'hooks': [{'type': 'command', 'command': command, 'timeout': 10}]})
atomic_write(hooks, json.dumps(values, indent=2) + '\n')
agents = home / '.codex/AGENTS.md'
preserve(agents)
old = agents.read_text() if agents.exists() else ''
marker = '<!-- CODEXPI GLOBAL -->'
if marker not in old:
    old += '\n' + marker + '\nFor projects managed by CodexPi, read /home/raspberry/CodexPi/templates/AGENTS.md and obey all infrastructure requirements.\n'
    atomic_write(agents, old, 0o644)
units = home / '.config/systemd/user'
units.mkdir(parents=True, exist_ok=True)
for unit in ('codexpi-native.service', 'codexpi.service', 'codexpi-unsnooze.service'):
    destination = units / unit
    preserve(destination)
    atomic_write(destination, (root / 'config' / unit).read_text(), 0o644)
for executable in (root / 'bin').iterdir():
    if executable.is_file():
        executable.chmod(0o755)
print('Configured secrets, merged hooks, Ponytail full, instructions and user service units')
