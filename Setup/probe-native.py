"""Probe the installed native protocol without requesting any model work."""
import json
import pathlib
import selectors
import subprocess
import time

root = pathlib.Path('/home/raspberry/CodexPi')
errors = (root / 'logs/native-probe.log').open('a')
proc = subprocess.Popen(['/home/raspberry/.local/bin/codex', 'app-server', '--stdio',
                         '--disable', 'multi_agent'], stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=errors, text=True, bufsize=1)
counter = 0


def rpc(method, params):
    global counter
    counter += 1
    proc.stdin.write(json.dumps({'id': counter, 'method': method, 'params': params}) + '\n')
    proc.stdin.flush()
    deadline = time.monotonic() + 90
    with selectors.DefaultSelector() as selector:
        selector.register(proc.stdout, selectors.EVENT_READ)
        while time.monotonic() < deadline:
            if not selector.select(timeout=2):
                if proc.poll() is not None:
                    raise RuntimeError('app-server exited')
                continue
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError('app-server closed stdout')
            msg = json.loads(line)
            if msg.get('id') == counter:
                if 'error' in msg:
                    raise RuntimeError(msg['error'])
                return msg['result']
    raise TimeoutError(method)


try:
    rpc('initialize', {'clientInfo': {'name': 'codexpi_probe', 'version': '0.1'},
                       'capabilities': {'experimentalApi': True}})
    proc.stdin.write('{"method":"initialized","params":{}}\n')
    proc.stdin.flush()
    result = rpc('thread/start', {'cwd': str(root), 'ephemeral': False,
                                 'approvalPolicy': 'never', 'sandbox': 'read-only',
                                 'config': {'features.multi_agent': False}})
    session = result['thread']['id']
    (root / 'state/native-probe-session.json').write_text(json.dumps({'session_id': session}))
    rpc('thread/name/set', {'threadId': session, 'name': 'CodexPi native interface probe'})
    paused = rpc('thread/goal/set', {'threadId': session, 'status': 'paused',
                                   'objective': 'Infrastructure probe. No model work requested.'})
    observed = rpc('thread/goal/get', {'threadId': session})
    assert observed['goal']['status'] == 'paused'
    assert observed['goal']['tokensUsed'] == 0
    print(json.dumps({'session_id': session, 'goal_status': observed['goal']['status'],
                      'tokens_used': observed['goal']['tokensUsed'], 'rename': True}))
    rpc('thread/unsubscribe', {'threadId': session})
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    errors.close()
