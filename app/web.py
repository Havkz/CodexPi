import asyncio
import hashlib
import hmac
import ipaddress
import json
import secrets
import time

from aiohttp import web

from .common import password_valid
from .usage import windows


def session(request):
    cookie = request.cookies.get('codexpi')
    if not cookie:
        return None
    key = hashlib.sha256(cookie.encode()).hexdigest()
    return request.app['controller'].db.conn.execute(
        'SELECT * FROM sessions WHERE id_hash=? AND expires>?', (key, time.time())).fetchone()


@web.middleware
async def security(request, handler):
    try:
        response = await authorize(request, handler)
    except web.HTTPException as exc:
        response = web.Response(status=exc.status, headers=exc.headers, body=exc.body)
    except (ValueError, KeyError) as exc:
        response = web.json_response({'error': request.app['controller'].redactor.clean(str(exc))}, status=400)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    # no-referrer makes Chromium send Origin:null for native form POSTs.
    # Keep same-origin login provenance, while withholding referrers from external sites.
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; form-action 'self'"
    if isinstance(response, web.HTTPException):
        normalized = web.Response(status=response.status, headers=response.headers, body=response.body)
        normalized.cookies.update(response.cookies)
        return normalized
    return response


async def authorize(request, handler):
    address = request.remote
    if address:
        try:
            ip = ipaddress.ip_address(address)
            lan = ipaddress.ip_network(request.app['controller'].config['lan_subnet'])
            if not (ip.is_loopback or ip in lan):
                raise web.HTTPForbidden()
        except ValueError:
            raise web.HTTPForbidden()
    host = request.host.split(':')[0]
    if address and host not in ('192.168.2.105', '127.0.0.1', 'localhost'):
        raise web.HTTPForbidden(text='Invalid Host')
    if request.path.startswith('/api/') and not session(request):
        raise web.HTTPUnauthorized()
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and request.path != '/login':
        current = session(request)
        if not current or not hmac.compare_digest(request.headers.get('X-CSRF-Token', ''), current['csrf']):
            raise web.HTTPForbidden(text='Invalid CSRF token')
        origin = request.headers.get('Origin')
        if origin and origin != str(request.url.origin()):
            raise web.HTTPForbidden(text='Invalid Origin')
    return await handler(request)


async def index(request):
    template = 'index.html' if session(request) else 'login.html'
    response = web.FileResponse(request.app['controller'].root / 'app/web_assets' / template)
    if template == 'login.html':
        tokens = request.app['login_tokens']
        now = time.monotonic()
        for key, expiry in list(tokens.items()):
            if expiry < now:
                del tokens[key]
        if len(tokens) >= 1024:
            raise web.HTTPTooManyRequests(text='Too many pending login pages')
        nonce = secrets.token_urlsafe(32)
        tokens[nonce] = now + 300
        response.set_cookie('codexpi_login', nonce, httponly=True, samesite='Strict', max_age=300)
    return response


async def favicon(request):
    return web.FileResponse(request.app['controller'].root / 'app/web_assets/favicon.ico')


async def login(request):
    # ponytail: one password verifier at a time; adequate for a single-user LAN UI.
    async with request.app['login_lock']:
        return await verify_login(request)


async def verify_login(request):
    controller = request.app['controller']
    nonce = request.cookies.get('codexpi_login', '')
    expires = request.app['login_tokens'].pop(nonce, 0)
    origin = request.headers.get('Origin')
    if expires < time.monotonic() or (origin and origin != str(request.url.origin())):
        raise web.HTTPForbidden(text='Reload the login page')
    address = request.remote or 'local'
    now = time.time()
    controller.db.conn.execute('DELETE FROM sessions WHERE expires<=?', (now,))
    controller.db.conn.execute('DELETE FROM login_attempts WHERE window_start<=?', (now - 300,))
    row = controller.db.conn.execute('SELECT * FROM login_attempts WHERE address=?', (address,)).fetchone()
    if row and now - row['window_start'] < 300 and row['failures'] >= 5:
        raise web.HTTPTooManyRequests(text='Too many login attempts. Wait five minutes.')
    data = await request.post()
    password = data.get('password', '')
    if not isinstance(password, str) or len(password) > 1024:
        raise web.HTTPBadRequest()
    valid = await asyncio.to_thread(password_valid, password, controller.config['password_hash'])
    if not valid:
        failures = row['failures'] + 1 if row and now - row['window_start'] < 300 else 1
        start = row['window_start'] if failures > 1 else now
        controller.db.conn.execute('INSERT INTO login_attempts VALUES (?,?,?) ON CONFLICT(address) DO UPDATE SET failures=excluded.failures,window_start=excluded.window_start', (address, failures, start))
        raise web.HTTPUnauthorized(text='Wrong password. Return to the login page to retry.')
    controller.db.conn.execute('DELETE FROM login_attempts WHERE address=?', (address,))
    token = secrets.token_urlsafe(32)
    controller.db.conn.execute('INSERT INTO sessions VALUES (?,?,?)',
        (hashlib.sha256(token.encode()).hexdigest(), secrets.token_urlsafe(32), now + 43200))
    response = web.HTTPSeeOther('/')
    response.set_cookie('codexpi', token, httponly=True, samesite='Strict', secure=request.secure, max_age=43200)
    response.del_cookie('codexpi_login')
    return response


async def state(request):
    controller = request.app['controller']
    now = time.time()
    native = getattr(controller, 'native', None)
    native_online = bool(native and native.ws and not native.ws.closed)
    seen = getattr(controller, 'worker_seen', 0)
    worker_age = max(0, time.monotonic() - seen) if seen else None
    git_poll = getattr(controller, 'last_git_poll', 0)
    unsnooze_poll = getattr(controller, 'last_unsnooze_poll', 0)
    errors = getattr(controller, 'health_errors', {})
    infrastructure = [
        {'name': 'Raspberry Pi', 'status': 'online', 'checked_at': now,
         'detail': 'CodexPi controller · LAN only', 'error': errors.get('scheduler')},
        {'name': 'Native Codex Bridge', 'status': 'online' if native_online else 'offline',
         'checked_at': now, 'detail': 'Local native session connection'},
        {'name': 'Windows Worker', 'status': 'online' if controller.windows_online else 'offline',
         'checked_at': now, 'heartbeat_age': worker_age, 'detail': 'Authenticated outbound connection'},
        {'name': 'GitHub', 'status': 'error' if errors.get('github') else 'connected' if git_poll else 'unknown',
         'checked_at': now - (time.monotonic() - git_poll) if git_poll else None,
         'detail': controller.config['github_account'] + ' · private repositories', 'error': errors.get('github')},
        {'name': 'Discord', 'status': 'online' if controller.bot and controller.bot.is_ready() else 'offline',
         'checked_at': now, 'detail': 'Project notifications', 'error': errors.get('discord')},
        {'name': 'Unsnooze', 'status': 'online' if controller.unsnooze.get('daemonRunning') else 'offline',
         'checked_at': now - (time.monotonic() - unsnooze_poll) if unsnooze_poll else None,
         'detail': 'Selective wake · queue position 1', 'error': errors.get('unsnooze')},
    ]
    projects = [{**p, 'manual_paused': bool(controller.db.setting('manual_pause/' + p['project_id'], False))}
                for p in controller.db.all()]
    payload = {'projects': projects, 'selected': controller.db.setting('selected'),
        'account_usage': controller.db.setting('account_usage', {}),
        'pause_all': controller.db.setting('pause_all', False), 'windows_online': controller.windows_online,
        'discord_online': bool(controller.bot and controller.bot.is_ready()),
        'unsnooze': controller.unsnooze, 'github_account': controller.config['github_account'],
        'infrastructure': infrastructure, 'server_time': now,
        'csrf': session(request)['csrf']}
    return safe_json(controller, payload)


def safe_json(controller, value):
    # Redact before JSON escaping, including quoted/newline-containing secrets.
    def clean(item):
        if isinstance(item, str):
            return controller.redactor.clean(item)
        if isinstance(item, dict):
            return {key: clean(val) for key, val in item.items()}
        if isinstance(item, list):
            return [clean(val) for val in item]
        return item
    return web.json_response(clean(value))


async def usage(request):
    controller = request.app['controller']
    account = controller.db.setting('account_usage', {})
    now = time.time()
    return safe_json(controller, {'windows': windows(account), 'history': controller.db.usage_history(now),
        'checked_at': account.get('checked_at'), 'server_time': now,
        'error': getattr(controller, 'health_errors', {}).get('account_usage')})


async def project_detail(request):
    from .controller import command
    controller = request.app['controller']
    project = controller.db.get(request.match_info['project_id'])
    events = [dict(row) for row in controller.db.conn.execute(
        'SELECT event_id,kind,payload,created_at,sent_at FROM events WHERE project_id=? ORDER BY event_id DESC LIMIT 30',
        (project['project_id'],))]
    jobs = [dict(row) for row in controller.db.conn.execute(
        'SELECT job_id,status,result,created_at,updated_at FROM jobs WHERE project_id=? ORDER BY created_at DESC LIMIT 10',
        (project['project_id'],))]
    commits, git_error = [], None
    try:
        result = await command('git', 'log', '-8', '--format=%H%x00%s%x00%cI',
                               cwd=project['project_path'], timeout=10)
        for line in result['stdout'].splitlines():
            sha, subject, date = line.split('\0', 2)
            commits.append({'sha': sha, 'subject': subject, 'date': date})
    except (RuntimeError, OSError, ValueError, TimeoutError) as exc:
        git_error = str(exc)
    for event in events:
        event['payload'] = json.loads(event['payload'])
    # Project-specific job logs only; global logs can contain other projects' data.
    for job in jobs:
        result = json.loads(job.pop('result') or '{}')
        job['exit_code'] = result.get('exit_code')
        job['stdout'] = str(result.get('stdout', ''))[-16000:]
        job['stderr'] = str(result.get('stderr', ''))[-16000:]
        job['artifacts'] = result.get('artifacts', [])
    return safe_json(controller, {'project': project, 'events': events, 'jobs': jobs,
                                 'commits': commits, 'git_error': git_error})


async def action(request):
    controller = request.app['controller']
    body = await request.json()
    if not isinstance(body, dict):
        raise ValueError('Action payload must be an object')
    action_name = body.get('action')
    ident = body.get('project_id')
    if action_name in ('rename', 'delete'):
        from .lifecycle import begin
        try:
            await begin(controller, ident, action_name, name=body.get('name'), confirmation=body.get('confirmation'))
        except RuntimeError as exc:
            response = safe_json(controller, {'error': str(exc),
                'recovery_pending': controller.db.get(ident)['lifecycle'] != 'ready'})
            response.set_status(409)
            return response
    elif action_name in ('run-now', 'resume'):
        return safe_json(controller, await controller.resume(ident, promote=action_name == 'run-now'))
    elif action_name == 'pause':
        async with controller.lock:
            project = controller.db.get(ident)
            if project['lifecycle'] != 'ready':
                raise ValueError('Project lifecycle operation is in progress')
            await controller.pause(project, manual=True)
    elif action_name == 'pause-all':
        async with controller.lock:
            controller.db.set_setting('pause_all', True)
            for project in controller.db.all():
                if project['lifecycle'] == 'ready' and project['goal_status'] != 'complete':
                    controller.db.set_setting('manual_pause/' + project['project_id'], True)
                if project['lifecycle'] == 'ready' and project['codex_session_id'] and project['goal_status'] != 'complete':
                    await controller.pause(project, manual=True,
                        preserve_status=project['goal_status'] not in ('active', 'usage limited'))
    elif action_name == 'reorder':
        async with controller.lock:
            controller.db.reorder(body['ids'])
    elif action_name == 'logout':
        token = request.cookies.get('codexpi', '')
        controller.db.conn.execute('DELETE FROM sessions WHERE id_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))
        response = web.json_response({'ok': True})
        response.del_cookie('codexpi')
        return response
    else:
        raise ValueError('Unknown action')
    return web.json_response({'ok': True})


def make_app(controller):
    app = web.Application(middlewares=[security], client_max_size=64 * 1024)
    app['controller'] = controller
    app['login_tokens'] = {}
    app['login_lock'] = asyncio.Lock()
    app.add_routes([web.get('/', index), web.get('/favicon.ico', favicon), web.post('/login', login),
                    web.get('/api/state', state), web.get('/api/usage', usage), web.post('/api/action', action),
                    web.get('/api/projects/{project_id}', project_detail)])
    app.router.add_static('/static/', controller.root / 'app/web_assets', show_index=False)
    return app
