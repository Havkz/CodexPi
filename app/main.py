import asyncio
import fcntl
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal

from aiohttp import web

from .common import Redactor, read_env
from .controller import Controller
from .discord_bot import Bot
from .native import tui_proxy
from .web import make_app
from .worker_server import request_windows, submit_job, worker_socket


ROOT = Path('/home/raspberry/CodexPi')


async def main():
    os.umask(0o077)
    lock = (ROOT / 'state/controller.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    config = json.loads((ROOT / 'config/site.json').read_text())
    env = read_env(ROOT / '.env')
    config['worker_secret'] = env['WORKER_SECRET']
    redactor = Redactor(ROOT)

    class LogFormatter(logging.Formatter):
        def format(self, record):
            return json.dumps({'time': self.formatTime(record), 'level': record.levelname,
                               'component': record.name, 'message': redactor.clean(record.getMessage())})

    handler = RotatingFileHandler(ROOT / 'logs/controller.log', maxBytes=2 * 1024 * 1024, backupCount=5)
    handler.setFormatter(LogFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    controller = Controller(ROOT, config)
    controller.db.set_setting('tui_ready', [])
    controller.bot = Bot(controller)
    bot_task = asyncio.create_task(controller.bot.start(env['DISCORD_BOT_TOKEN']))

    async def local_open(request):
        data = await request.json()
        try:
            return web.json_response(await controller.create(data['name']))
        except Exception as exc:
            return web.json_response({'error': redactor.clean(str(exc))}, status=400)

    async def local_status(request):
        from .power import public_state
        return web.json_response({'online': controller.windows_online, **public_state(controller)})

    async def local_wake(request):
        try:
            return web.json_response(await request_windows(controller, await request.json()))
        except Exception as exc:
            return web.json_response({'error': redactor.clean(str(exc))}, status=400)

    async def local_browse(request):
        try:
            return web.json_response(await controller.browse())
        except Exception as exc:
            return web.json_response({'error': redactor.clean(str(exc))}, status=400)

    async def local_job(request):
        try:
            return web.json_response(await submit_job(controller, await request.json()))
        except Exception as exc:
            return web.json_response({'error': redactor.clean(str(exc))}, status=400)

    async def job_status(request):
        row = controller.db.conn.execute('SELECT status,result FROM jobs WHERE job_id=?', (request.match_info['job_id'],)).fetchone()
        if row is None:
            raise web.HTTPNotFound()
        return web.json_response({'status': row['status'], 'result': json.loads(row['result']) if row['result'] else None})

    async def local_deploy(request):
        from .deployment import request as deploy
        try:
            return web.json_response(await deploy(controller, await request.json()))
        except Exception as exc:
            return web.json_response({'error': redactor.clean(str(exc))}, status=400)

    async def local_import(request):
        from .migration import request as migrate
        try:
            return web.json_response(await migrate(controller, await request.json()))
        except Exception as exc:
            return web.json_response({'error': redactor.clean(str(exc))}, status=400)

    local = web.Application(client_max_size=128 * 1024)
    local.add_routes([web.post('/projects/open', local_open), web.get('/windows-status', local_status),
                      web.post('/windows-wake', local_wake),
                      web.post('/jobs', local_job), web.get('/jobs/{job_id}', job_status),
                      web.post('/deployment/pi', local_deploy), web.post('/projects/import', local_import),
                      web.post('/sessions/browse', local_browse)])
    gate = web.Application()
    gate['controller'] = controller
    gate['sockets'] = set()
    async def close_tuis(app):
        await asyncio.gather(*(socket.close(code=1001, message=b'controller restarting')
                               for socket in list(app['sockets'])))
    gate.on_shutdown.append(close_tuis)
    gate.router.add_get('/{tail:.*}', tui_proxy)
    dashboard = make_app(controller)
    dashboard.router.add_get('/worker/ws', worker_socket)
    runners = []
    for app, filename in ((local, 'local.sock'), (gate, 'tui.sock')):
        socket = ROOT / 'state' / filename
        if socket.exists():
            socket.unlink()
        runner = web.AppRunner(app, access_log=None, shutdown_timeout=5)
        await runner.setup()
        await web.UnixSite(runner, str(socket)).start()
        os.chmod(socket, 0o600)
        runners.append(runner)
    await controller.start()
    runner = web.AppRunner(dashboard, access_log=None, shutdown_timeout=5)
    await runner.setup()
    await web.TCPSite(runner, config['listen_host'], 8787).start()
    runners.append(runner)
    logging.getLogger('controller').info('Controller, dashboard and local TUI gate started')
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stopped.set)
    stop_task = asyncio.create_task(stopped.wait())
    done, _ = await asyncio.wait((stop_task, bot_task), return_when=asyncio.FIRST_COMPLETED)
    try:
        if bot_task in done:
            bot_task.result()
    finally:
        stop_task.cancel()
        if controller.worker is not None:
            await controller.worker.close(code=1001, message=b'controller restarting')
        for runner in runners:
            await runner.cleanup()
        await controller.bot.close()
        await asyncio.gather(bot_task, return_exceptions=True)
        await controller.close()
        lock.close()


if __name__ == '__main__':
    asyncio.run(main())
