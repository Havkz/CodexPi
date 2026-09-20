"""Fail closed if a tracked file contains a configured secret; never print its value."""
import json
from pathlib import Path
import re
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from app.common import read_env

secrets = []
for path in [root / '.env', *root.glob('projects/*/.env')]:
    secrets.extend(value.encode() for value in read_env(path).values() if value)
source = Path('C:/CODEXPI_GOAL.md')
if source.exists():
    secrets.append(source.read_text(encoding='cp1252').splitlines()[121].strip('`').encode())
credential = root / 'windows-worker/config.json'
if credential.exists():
    secrets.append(json.loads(credential.read_text())['secret_dpapi'].encode())
tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
failures = []
for name in filter(None, tracked):
    data = (root / name).read_bytes()
    if any(secret in data for secret in secrets) or re.search(
            rb'(?i)(?:gh[pousr]_[a-z0-9_]{30,}|github_pat_[a-z0-9_]{30,}|sk-[a-z0-9_-]{30,})', data):
        failures.append(name)
if failures:
    raise SystemExit('Secret scan failed in: ' + ', '.join(failures))
print('Tracked source secret scan passed')
