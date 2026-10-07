"""Read-only live check on the Pi: real --all picker, wheel, pager and unsent draft."""
import argparse
import asyncio
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import sqlite3
import struct
import subprocess
import sys
import termios
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.native import Native


def tmux(*args, check=True):
    return subprocess.run(['tmux', *args], capture_output=True, text=True, check=check).stdout


def main(slug):
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    db = sqlite3.connect('file:state/codexpi.db?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    project = dict(db.execute('SELECT * FROM projects WHERE slug=?', (slug,)).fetchone())
    assert project['goal_status'] in ('stalled', 'paused'), 'Use a non-executing project'
    assert not project['operation'] and project['lifecycle'] == 'ready'
    assert not tmux('list-clients', '-F', '#{session_name}').strip(), 'A user TUI is attached'

    async def native_state():
        native = await Native(root / 'state/native.sock').connect()
        try:
            sid = project['codex_session_id']
            goal = (await native.rpc('thread/goal/get', {'threadId': sid})).get('goal')
            turns = (await native.rpc('thread/turns/list', {
                'threadId': sid, 'limit': 1, 'sortDirection': 'desc'}))['data']
            return {'goal': goal, 'latest_turn_id': turns[0]['id'] if turns else None}
        finally:
            await native.close()

    def queue_state():
        return [tuple(row) for row in db.execute(
            'SELECT project_id,queue_position FROM projects ORDER BY project_id')]

    before, queue = asyncio.run(native_state()), queue_state()
    assert not before['goal'] or before['goal']['status'] != 'active'
    existing = set(tmux('list-sessions', '-F', '#{session_name}').splitlines())
    name = None
    pid, fd = pty.fork()
    if pid == 0:
        os.execvpe(str(root / 'bin/codexpi'), ['codexpi', '--all'],
                   {**os.environ, 'TERM': 'xterm-256color'})
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', 36, 120, 0, 0))

    def drain(seconds=.2):
        deadline = time.monotonic() + seconds
        data = b''
        while time.monotonic() < deadline:
            if select.select([fd], [], [], .05)[0]:
                data += os.read(fd, 65536)
        return data

    def wait(predicate, message, timeout=25):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            drain()
            if predicate():
                return
        raise AssertionError(message)

    def screen():
        return tmux('capture-pane', '-p', '-t', name + ':0.0')

    def mode():
        return tmux('display-message', '-p', '-t', name + ':0.0', '#{pane_in_mode}').strip() == '1'

    try:
        def find_view():
            nonlocal name
            new = set(tmux('list-sessions', '-F', '#{session_name}').splitlines()) - existing
            assert len(new) <= 1, 'Another session appeared; stop rather than touch it'
            if new:
                name = new.pop()
                assert name.startswith('codexpi-browser-')
            return name
        wait(find_view, 'No --all view appeared')
        wait(lambda: 'Resume a previous session' in screen(), 'Native picker missing')
        os.write(fd, project['display_name'].encode())
        wait(lambda: any(line.lstrip().startswith('› ') and project['display_name'] in line
                         for line in screen().splitlines()), 'Requested session not in picker')
        os.write(fd, b'\r')
        wait(lambda: 'Resume paused goal?' in screen() or 'Goal stalled' in screen(), 'Session not opened')
        if 'Resume paused goal?' in screen():
            # Never accept the default Resume option during a read-only test.
            if '› 2. Leave paused' not in screen():
                tmux('send-keys', '-t', name + ':0.0', 'Down')
                wait(lambda: '› 2. Leave paused' in screen(), 'Safe Leave paused choice missing')
            os.write(fd, b'\r')
            wait(lambda: 'Resume paused goal?' not in screen(), 'Modal did not close')
        assert tmux('show-options', '-v', '-t', name, 'mouse').strip() == 'on'
        draft = 'CODEXPI_SCROLL_DRAFT_DO_NOT_SEND'
        os.write(fd, draft.encode())
        wait(lambda: '› ' + draft in screen(), 'Unsent draft missing')
        os.write(fd, b'\x1b[<64;60;10M' * 12)
        wait(mode, 'Wheel did not enter scrollback')
        position = tmux('display-message', '-p', '-t', name + ':0.0', '#{scroll_position}').strip()
        assert position.isdigit() and int(position) > 0, 'Wheel did not move the visible transcript'
        assert '› ' + draft in screen(), 'Wheel replaced the underlying composer draft'
        tmux('send-keys', '-t', name + ':0.0', '-X', 'cancel')
        wait(lambda: not mode(), 'Scrollback did not close')
        assert '› ' + draft in screen(), 'Draft lost after scrolling'
        os.write(fd, b'\x02\x1b[5~')  # tmux prefix + PageUp: keyboard scrollback
        wait(mode, 'Keyboard scrollback unavailable')
        tmux('send-keys', '-t', name + ':0.0', '-X', 'cancel')
        drain()
        os.write(fd, b'\x14')  # Native full transcript, including paginated older messages.
        wait(lambda: 'T R A N S C R I P T' in screen(), 'Native transcript pager missing')
        pager = screen()
        os.write(fd, b'\x1b[5~')
        wait(lambda: screen() != pager, 'Native PageUp did not scroll')
        os.write(fd, b'q')
        wait(lambda: '› ' + draft in screen(), 'Native pager did not preserve the draft')
        assert asyncio.run(native_state()) == before, 'Native goal or turn changed'
        assert queue_state() == queue, 'Queue changed'
        print(json.dumps({'project': slug, 'real_codexpi_all': True, 'wheel_scroll': True,
                          'keyboard_scroll': True, 'native_transcript_pager': True,
                          'draft_preserved': True, 'goal_turn_and_queue_unchanged': True}))
    finally:
        if name:
            tmux('kill-session', '-t', '=' + name, check=False)
        os.close(fd)
        os.waitpid(pid, 0)
        db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('slug', help='Existing, non-executing project to inspect; no prompt is sent')
    try:
        main(parser.parse_args().slug)
    except Exception as exc:
        print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
