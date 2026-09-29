"""Pi hook inventory and isolated Ponytail checks; no model turn or live config write.

Measures the installed hooks, not total Codex startup latency. Temporary plugin
data prevents mode-switch checks from changing any real session's mode.
"""
import asyncio
import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.common import atomic_write
from app.native import Native


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--token-preflight', action='store_true', help='Check staged upstream installer in memory only')
    args = parser.parse_args()
    if args.token_preflight:
        upstream = ROOT / 'Setup/upstream/token-optimizer'
        sys.path.insert(0, str(upstream / 'skills/token-optimizer/scripts'))
        import codex_install
        import codex_compact_prompt
        hooks_path = Path.home() / '.codex/hooks.json'
        existing = json.loads(hooks_path.read_text())
        first = codex_install._merge_hooks(existing, enable_prompt_hooks=True)
        second = codex_install._merge_hooks(first, enable_prompt_hooks=True)
        removed = codex_install._remove_hooks(first)
        config = (Path.home() / '.codex/config.toml').read_text()
        proposed, _ = codex_compact_prompt._replace_or_append_config(
            config, Path.home() / '.codex/token-optimizer/codex-compact-prompt.md', force=False)
        count = lambda value: sum(len(g.get('hooks', [])) for groups in value['hooks'].values() for g in groups)
        result = {'upstream_commit': subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip(),
            'original_handlers': count(existing), 'first_install_handlers': count(first),
            'second_install_handlers': count(second), 'uninstall_handlers': count(removed),
            'idempotent': first == second, 'uninstall_preserves_original': removed == existing,
            'compact_setting_at_root': 'experimental_compact_prompt_file' in tomllib.loads(proposed),
            'live_files_changed': False}
        record = ROOT / 'state/token-optimizer-preflight.json'
        atomic_write(record, json.dumps(result, indent=2) + '\n')
        print(json.dumps({'record': str(record), **result}, indent=2))
        if not all(result[k] for k in ('idempotent', 'uninstall_preserves_original', 'compact_setting_at_root')):
            raise SystemExit(1)
        return
    native = await Native(ROOT / 'state/native.sock').connect()
    try:
        listing = await native.rpc('hooks/list', {'cwds': [str(ROOT)]})
    finally:
        await native.close()
    assert not any(g['errors'] or g['warnings'] for g in listing['data']), 'Hook loading problem'
    hooks = [h for g in listing['data'] for h in g['hooks']]
    assert len(hooks) == 7 and all(h['enabled'] and h['trustStatus'] == 'trusted' for h in hooks)
    assert len({h['key'] for h in hooks}) == len(hooks), 'Duplicate hook definition'
    ponytail = [h for h in hooks if h['pluginId'] == 'ponytail@ponytail']
    assert {h['eventName'] for h in ponytail} == {'sessionStart', 'userPromptSubmit', 'subagentStart'}
    plugin = Path(ponytail[0]['sourcePath']).parent.parent
    manifest = json.loads((plugin / '.codex-plugin/plugin.json').read_text())
    config = json.loads((Path.home() / '.config/ponytail/config.json').read_text())
    assert config['defaultMode'] == 'full'
    pid = subprocess.check_output(['systemctl', '--user', 'show', 'codexpi-native',
                                   '-p', 'MainPID', '--value'], text=True).strip()
    service_env = dict(item.split(b'=', 1) for item in Path(f'/proc/{pid}/environ').read_bytes().split(b'\0') if b'=' in item)
    assert service_env.get(b'PONYTAIL_DEFAULT_MODE') == b'full'

    measurements = {}
    with tempfile.TemporaryDirectory(prefix='codexpi-ponytail-') as scratch:
        env = dict(os.environ, PLUGIN_DATA=scratch, CLAUDE_PLUGIN_ROOT=str(plugin),
                   PLUGIN_ROOT=str(plugin), PONYTAIL_DEFAULT_MODE='full')

        def invoke(script, event, prompt=None):
            payload = {'hook_event_name': event, 'source': 'startup', 'session_id': 'isolated-hook-check'}
            if prompt is not None:
                payload['prompt'] = prompt
            started = time.perf_counter()
            output = subprocess.run(['node', str(plugin / 'hooks' / script)], input=json.dumps(payload),
                env=env, text=True, capture_output=True, check=True, timeout=5)
            elapsed = (time.perf_counter() - started) * 1000
            assert not output.stderr, 'Unexpected hook stderr'
            return (json.loads(output.stdout) if output.stdout.strip() else {}), elapsed

        for _ in range(3):
            result, elapsed = invoke('ponytail-activate.js', 'SessionStart')
            assert result['systemMessage'] == 'PONYTAIL:FULL'
            context = result['hookSpecificOutput']['additionalContext']
            assert 'YAGNI' in context and 'full' in context and 'security' in context.lower()
            assert (Path(scratch) / '.ponytail-active').read_text() == 'full'
            measurements.setdefault('session_start_ms', []).append(round(elapsed, 2))
            result, elapsed = invoke('ponytail-mode-tracker.js', 'UserPromptSubmit', 'ordinary project request')
            assert not result, 'Ordinary prompt should not inject duplicate rules'
            measurements.setdefault('ordinary_prompt_ms', []).append(round(elapsed, 2))
        result, _ = invoke('ponytail-mode-tracker.js', 'UserPromptSubmit', '/ponytail off')
        assert result['systemMessage'] == 'PONYTAIL:OFF'
        assert not (Path(scratch) / '.ponytail-active').exists()

    result = {'observed_at': time.time(), 'version': manifest['version'], 'plugin_root': str(plugin),
        'config_default': config['defaultMode'], 'running_service_default': 'full',
        'native_main_pid': int(pid), 'trusted_enabled_hooks': len(hooks),
        'hooks': [{k: h[k] for k in ('eventName', 'sourcePath', 'pluginId', 'timeoutSec', 'currentHash')} for h in hooks],
        'isolated_activation_prompt_off_passed': True, 'measurements': measurements,
        'median_ms': {k: round(statistics.median(v), 2) for k, v in measurements.items()},
        'native_model_turn_started': False, 'full_tui_startup_measured': False,
        'token_optimizer_hook_found': any('token' in h['command'].lower() and 'optim' in h['command'].lower() for h in hooks)}
    record = ROOT / 'state' / ('optimization-' + time.strftime('%Y%m%d-%H%M%S') + '.json')
    atomic_write(record, json.dumps(result, indent=2) + '\n')
    print(json.dumps({'record': str(record), **result}, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
