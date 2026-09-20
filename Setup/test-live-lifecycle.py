"""Create, rename and delete ONLY a dedicated lifecycle E2E project via real UI.

Private GitHub repository and local recovery backup intentionally remain.
No model goal is invented; the same native empty session is preserved/archived.
"""
import base64
import json
from pathlib import Path
import subprocess

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://192.168.2.105:8787'
NAME = 'CodexPi Lifecycle E2E 20260920'
RENAMED = 'CodexPi Lifecycle Renamed E2E 20260920'
RECORD = ROOT / 'state/lifecycle-e2e.json'


def remote(code):
    encoded = base64.b64encode(code.encode()).decode()
    result = subprocess.run(['ssh', 'raspberry@192.168.2.105',
        'export PATH=/home/raspberry/.local/bin:$PATH; cd /home/raspberry/CodexPi && .venv/bin/python -c "import base64;exec(base64.b64decode(\'' + encoded + '\'))"'],
        capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:])
    return json.loads(result.stdout)


def open_project(name):
    return remote('''import asyncio,json
from aiohttp import ClientSession,UnixConnector
async def main():
    async with ClientSession(connector=UnixConnector(path='state/local.sock')) as client:
        async with client.post('http://localhost/projects/open',json={'name': ''' + repr(name) + '''}) as response:
            result=await response.json()
            if response.status != 200: raise RuntimeError(result)
            print(json.dumps(result))
asyncio.run(main())
''')


def main():
    if RECORD.exists():
        project = json.loads(RECORD.read_text())
        if project.get('verified'):
            verify_deleted(project, project['renamed'])
            return
    else:
        project = open_project(NAME)
        RECORD.write_text(json.dumps(project, indent=2))
    ident = project['project_id']
    snapshot = remote('''import json
from pathlib import Path
from app.db import Database
db=Database('state/codexpi.db')
row=db.conn.execute('SELECT 1 FROM projects WHERE project_id=?',(''' + repr(ident) + ''',)).fetchone()
print(json.dumps({'deleted':not bool(row),'renamed':json.loads((Path('backups/deleted')/''' + repr(ident) + '''/'manifest.json').read_text())['project'] if not row else None}))
db.conn.close()
''')
    if snapshot['deleted']:
        verify_deleted(project, snapshot['renamed'])
        return
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.goto(BASE)
        password = Path('C:/CODEXPI_GOAL.md').read_text(encoding='cp1252').splitlines()[121].strip('`')
        page.get_by_label('Passwort').fill(password)
        password = None
        page.get_by_role('button', name='Anmelden').click()
        page.locator('.infra-card').first.wait_for()
        current = next(p for p in page.request.get(BASE + '/api/state').json()['projects'] if p['project_id'] == ident)
        assert current['display_name'] in (NAME, RENAMED), 'Refuse to modify any unrelated project'
        if current['display_name'] == NAME:
            page.locator('#projects .project-card').filter(has=page.get_by_role('heading', name=NAME, exact=True)).get_by_role('button', name='Details').click()
            page.locator('#project-dialog').get_by_role('button', name='Rename', exact=True).click()
            page.get_by_label('Neuer Projektname', exact=True).fill(RENAMED)
            page.get_by_role('button', name='Umbenennen', exact=True).click()
            try:
                page.locator('#lifecycle-dialog').wait_for(state='hidden', timeout=90000)
            except Exception:
                print(page.locator('#lifecycle-error').text_content())
                raise
        renamed = open_project(RENAMED)
        assert renamed['project_id'] == ident and renamed['codex_session_id'] == project['codex_session_id']
        assert renamed['slug'] != project['slug']
        check = remote('''import asyncio,json,subprocess
from pathlib import Path
from app.native import Native
async def main():
    n=await Native('state/native.sock').connect()
    try:
        thread=(await n.rpc('thread/read',{'threadId': ''' + repr(project['codex_session_id']) + '''}))['thread']
        print(json.dumps({'name':thread['name'],'cwd':thread['cwd'],
            'origin':subprocess.check_output(['git','remote','get-url','origin'],cwd=''' + repr(renamed['project_path']) + ''',text=True).strip(),
            'old_path_exists':Path(''' + repr(project['project_path']) + ''').exists()}))
    finally: await n.close()
asyncio.run(main())
''')
        assert check['name'] == RENAMED, check
        assert check['cwd'] == renamed['project_path'], check
        assert check['origin'] == 'https://github.com/' + renamed['github_repo'] + '.git', check
        assert not check['old_path_exists'], check
        page.reload()
        card = page.locator('#projects .project-card').filter(has=page.get_by_role('heading', name=RENAMED, exact=True))
        card.get_by_role('button', name='Details').click()
        page.locator('#project-dialog').get_by_role('button', name='Delete', exact=True).click()
        confirmation = page.locator('#lifecycle-input')
        confirmation.fill('wrong confirmation')
        page.get_by_role('button', name='Löschen bestätigen', exact=True).click()
        assert page.get_by_text('Der Projektname stimmt nicht überein.', exact=True).is_visible()
        confirmation.fill(RENAMED)
        page.get_by_role('button', name='Löschen bestätigen', exact=True).click()
        try:
            page.locator('#lifecycle-dialog').wait_for(state='hidden', timeout=90000)
        except Exception:
            print(page.locator('#lifecycle-error').text_content())
            raise
        remaining = page.request.get(BASE + '/api/state').json()['projects']
        assert all(p['project_id'] != ident for p in remaining)
        page.get_by_role('button', name='Abmelden').click()
        page.get_by_label('Passwort').wait_for()
        browser.close()
    verify_deleted(project, renamed)


def verify_deleted(project, renamed):
    ident = project['project_id']
    final = remote('''import asyncio,json,subprocess
from pathlib import Path
from app.db import Database
from app.native import Native
from app.common import read_env
from aiohttp import ClientSession
db=Database('state/codexpi.db')
backup=Path('backups/deleted')/''' + repr(ident) + '''
repo=json.loads(subprocess.check_output(['gh','repo','view',''' + repr(renamed['github_repo']) + ''','--json','visibility'],text=True))
result={'repo_private':repo['visibility']=='PRIVATE','backup_exists':(backup/'project/.env').exists(),
    'project_path_exists':Path(''' + repr(renamed['project_path']) + ''').exists(),
    'db_absent':db.conn.execute('SELECT 1 FROM projects WHERE project_id=?',(''' + repr(ident) + ''',)).fetchone() is None,
    'tmux_absent':subprocess.run(['tmux','has-session','-t',''' + repr('=' + renamed['tmux_session_name']) + '''],capture_output=True).returncode!=0}
db.conn.close()
async def check():
    native=await Native('state/native.sock').connect()
    try:
        archived=(await native.rpc('thread/read',{'threadId':''' + repr(project['codex_session_id']) + '''}))['thread']
        result['session_archived']=Path(archived['path']).parent.name=='archived_sessions'
    finally: await native.close()
    async with ClientSession(headers={'Authorization':'Bot '+read_env('.env')['DISCORD_BOT_TOKEN']}) as client:
        async with client.get('https://discord.com/api/v10/channels/''' + str(project['discord_channel_id']) + '''') as response:
            result['discord_deleted']=response.status==404
    print(json.dumps(result))
asyncio.run(check())
''')
    assert final == {'repo_private': True, 'backup_exists': True, 'project_path_exists': False,
                     'db_absent': True, 'tmux_absent': True, 'session_archived': True, 'discord_deleted': True}, final
    project.update(verified=True, renamed=renamed, checks=final)
    RECORD.write_text(json.dumps(project, indent=2))
    print(json.dumps({'lifecycle_live': 'passed', 'project_id': ident, 'session_id': project['codex_session_id'], **final}))


if __name__ == '__main__':
    main()
