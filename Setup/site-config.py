"""Generate only a password hash from the user-owned specification."""
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.common import password_hash

root = Path(__file__).resolve().parents[1]
password = Path('C:/CODEXPI_GOAL.md').read_text(encoding='cp1252').splitlines()[121].strip('`')
if not password:
    raise SystemExit('Dashboard password not found in the specified source line')
user = json.loads(subprocess.run(['gh', 'api', 'user'], capture_output=True, check=True).stdout)
config = {'listen_host': '192.168.2.105', 'lan_subnet': '192.168.2.0/24',
          'password_hash': password_hash(password), 'github_account': user['login'],
          'github_email': str(user['id']) + '+' + user['login'] + '@users.noreply.github.com',
          'discord_category': '1550840767969370163'}
target = root / 'config/site.json'
if target.exists():
    raise SystemExit('Existing config preserved; refusing to replace its password hash')
target.write_text(json.dumps(config, indent=2) + '\n')
print('Site config generated; plaintext password was not written')
