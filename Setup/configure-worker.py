"""Provision a CurrentUser DPAPI credential over the existing authenticated SSH link."""
import base64
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.common import atomic_write
from app.windows_worker import protect_secret

target = ROOT / 'windows-worker/config.json'
if target.exists():
    data = json.loads(target.read_text())
    secret = protect_secret(base64.b64decode(data['secret_dpapi']), decrypt=True)
    assert len(secret) >= 32
    print('Existing worker credential decrypts correctly; preserved')
else:
    command = "cd /home/raspberry/CodexPi && python3 -c \"from app.common import read_env; print(read_env('.env')['WORKER_SECRET'])\""
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', 'raspberry@192.168.2.105', command],
                            capture_output=True, check=True, timeout=30)
    secret = result.stdout.strip()
    if len(secret) != 64 or any(c not in b'0123456789abcdef' for c in secret):
        raise RuntimeError('Invalid provisioning response')
    encrypted = protect_secret(secret)
    assert protect_secret(encrypted, decrypt=True) == secret
    atomic_write(target, json.dumps({'url': 'ws://192.168.2.105:8787/worker/ws',
                                     'secret_dpapi': base64.b64encode(encrypted).decode()}, indent=2))
    print('Worker credential securely provisioned using CurrentUser DPAPI')
