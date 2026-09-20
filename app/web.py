import asyncio
import hashlib
import hmac
import ipaddress
import json
import secrets
import time

from aiohttp import web

from .common import password_valid


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
        response = exc
    except (ValueError, KeyError) as exc:
        response = web.json_response({'error': request.app['controller'].redactor.clean(str(exc))}, status=400)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; form-action 'self'"
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
    payload = {'projects': controller.db.all(), 'selected': controller.db.setting('selected'),
        'pause_all': controller.db.setting('pause_all', False), 'windows_online': controller.windows_online,
        'discord_online': bool(controller.bot and controller.bot.is_ready()),
        'unsnooze': controller.unsnooze, 'github_account': controller.config['github_account'],
        'csrf': session(request)['csrf']}
    return web.Response(text=controller.redactor.clean(json.dumps(payload)), content_type='application/json')


async def action(request):
    controller = request.app['controller']
    body = await request.json()
    action_name = body.get('action')
    ident = body.get('project_id')
    if action_name in ('run-now', 'resume'):
        await controller.run_now(ident)
    elif action_name == 'pause':
        async with controller.lock:
            await controller.pause(controller.db.get(ident))
    elif action_name == 'pause-all':
        async with controller.lock:
            controller.db.set_setting('pause_all', True)
            for project in controller.db.all():
                if project['codex_session_id'] and project['goal_status'] in ('active', 'usage limited'):
                    await controller.pause(project)
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
    app.add_routes([web.get('/', index), web.post('/login', login),
                    web.get('/api/state', state), web.post('/api/action', action)])
    app.router.add_static('/static/', controller.root / 'app/web_assets', show_index=False)
    return app
