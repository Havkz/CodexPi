"""Pi hook inventory and isolated Ponytail checks; no model turn or live config write.

Measures the installed hooks, not total Codex startup latency. Temporary plugin
data prevents mode-switch checks from changing any real session's mode.
"""
import asyncio
import argparse
import json
import os
from pathlib import Path
import runpy
import statistics
import shutil
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
    parser.add_argument('--token-preflight', action='store_true', help='Check staged installer in memory and disposable configuration copies')
    parser.add_argument('--token-baseline', type=Path, default=Path.home() / '.codex',
                        help='Directory with original hooks.json/config.toml; use the pre-install backup after activation')
    args = parser.parse_args()
    upstream = ROOT / 'Setup/upstream/token-optimizer'
    sys.path.insert(0, str(upstream / 'skills/token-optimizer/scripts'))
    import codex_install
    import codex_compact_prompt
    if args.token_preflight:
        hooks_path = Path.home() / '.codex/hooks.json'
        baseline_hooks = args.token_baseline / 'hooks.json'
        baseline_config = args.token_baseline / 'config.toml'
        existing = json.loads(baseline_hooks.read_text())
        first = codex_install._merge_hooks(existing, enable_prompt_hooks=True)
        second = codex_install._merge_hooks(first, enable_prompt_hooks=True)
        removed = codex_install._remove_hooks(first)
        config = baseline_config.read_text()
        proposed, _ = codex_compact_prompt._replace_or_append_config(
            config, Path.home() / '.codex/token-optimizer/codex-compact-prompt.md', force=False)
        count = lambda value: sum(len(g.get('hooks', [])) for groups in value['hooks'].values() for g in groups)
        result = {'upstream_commit': subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip(),
            'original_handlers': count(existing), 'first_install_handlers': count(first),
            'second_install_handlers': count(second), 'uninstall_handlers': count(removed),
            'idempotent': first == second, 'uninstall_preserves_original': removed == existing,
            'compact_setting_at_root': 'experimental_compact_prompt_file' in tomllib.loads(proposed),
            'live_files_changed': False}
        checks = ('idempotent', 'uninstall_preserves_original', 'compact_setting_at_root')
        if all(result[k] for k in checks):
            # The real Codex home is never reassigned. Only the three install
            # modules' path resolvers target these disposable copies.
            original_hooks = hooks_path.read_bytes()
            config_path = Path.home() / '.codex/config.toml'
            original_config = config_path.read_bytes()
            with tempfile.TemporaryDirectory(prefix='.codexpi-token-check-', dir=Path.home()) as scratch:
                sandbox = Path(scratch)
                shutil.copy2(baseline_hooks, sandbox / 'hooks.json')
                shutil.copy2(baseline_config, sandbox / 'config.toml')
                codex_install.codex_home = lambda: sandbox
                codex_compact_prompt.codex_home = lambda: sandbox
                codex_install.codex_statusline.codex_home = lambda: sandbox
                codex_install.install(sandbox, is_global=True, enable_prompt_hooks=True)
                installed_hooks = (sandbox / 'hooks.json').read_bytes()
                installed_config = (sandbox / 'config.toml').read_bytes()
                parsed = tomllib.loads(installed_config.decode())
                prompt = Path(parsed.pop('experimental_compact_prompt_file'))
                assert prompt == sandbox / 'token-optimizer/codex-compact-prompt.md'
                assert prompt.read_text() == codex_compact_prompt.COMPACT_PROMPT
                assert parsed == tomllib.loads(config)
                codex_install.install(sandbox, is_global=True, enable_prompt_hooks=True)
                assert (sandbox / 'hooks.json').read_bytes() == installed_hooks
                assert (sandbox / 'config.toml').read_bytes() == installed_config
                codex_install.uninstall(sandbox, is_global=True)
                assert json.loads((sandbox / 'hooks.json').read_text()) == existing
                assert (sandbox / 'config.toml').read_bytes() == baseline_config.read_bytes()
                assert not prompt.exists()
            assert hooks_path.read_bytes() == original_hooks
            assert config_path.read_bytes() == original_config
            foreign = {'hooks': [{'type': 'command', 'command': 'TOKEN_OPTIMIZER_RUNTIME=codex python3 user-hook.py'}]}
            mixed = json.loads(json.dumps(codex_install._managed_hooks()['Stop'][0]))
            mixed['hooks'].extend(foreign['hooks'])
            for group in (foreign, mixed):
                candidate = {'hooks': {'Stop': [group]}}
                merged = codex_install._merge_hooks(candidate, enable_prompt_hooks=True)
                assert codex_install._remove_hooks(merged) == candidate
            result['copied_config_install_reinstall_uninstall_passed'] = True
            result['foreign_and_mixed_groups_preserved'] = True
            # Use the installed sandbox prerequisite: no network, private PID
            # namespace, read-only host and a disposable home at its real path.
            # HOME/CODEX_HOME and the production session databases stay untouched.
            with tempfile.TemporaryDirectory(prefix='codexpi-token-hooks-') as scratch:
                sandbox = Path(scratch)
                (sandbox / '.codex').mkdir()
                (sandbox / 'workspace').mkdir()
                plugin_copy = sandbox / 'plugin-copy'
                shutil.copytree(upstream / 'plugins/token-optimizer', plugin_copy,
                                ignore=shutil.ignore_patterns('__pycache__'))
                measurements = {}
                managed = codex_install._managed_hooks(enable_prompt_hooks=True)
                for event in ('SessionStart', 'UserPromptSubmit', 'Stop'):
                    handler = managed[event][0]['hooks'][0]
                    payload = {'hook_event_name': event, 'source': 'startup',
                        'session_id': 'codexpi-isolated-token-check',
                        'cwd': str(Path.home() / 'workspace'), 'prompt': 'ordinary project request'}
                    started = time.perf_counter()
                    output = subprocess.run(['bwrap', '--unshare-all', '--die-with-parent', '--new-session',
                        '--ro-bind', '/', '/', '--bind', scratch, str(Path.home()),
                        '--bind', str(plugin_copy), str(upstream), '--proc', '/proc', '--dev', '/dev',
                        '--tmpfs', '/tmp', '--chdir', str(Path.home() / 'workspace'),
                        '--setenv', 'TOKEN_OPTIMIZER_SNAPSHOT_DIR', str(Path.home() / 'snapshots'),
                        '/bin/sh', '-c', handler['command']], input=json.dumps(payload),
                        text=True, capture_output=True, check=True, timeout=handler['timeout'])
                    measurements[event] = round((time.perf_counter() - started) * 1000, 2)
                    assert not output.stderr, output.stderr
                    if output.stdout.strip():
                        envelope = json.loads(output.stdout)
                        assert isinstance(envelope, dict)
                        specific = envelope.get('hookSpecificOutput', {})
                        assert specific.get('hookEventName', event) == event
                for log in sandbox.rglob('*diagnostics.log'):
                    content = log.read_text()
                    assert 'Traceback' not in content and 'failed, continuing' not in content, content
                generated = sorted(str(p.relative_to(sandbox)) for p in sandbox.rglob('*')
                                   if p.is_file() and not p.is_relative_to(plugin_copy))
                assert generated, 'Hooks exited without any execution evidence'
                result['sandboxed_generated_files'] = generated
                result['sandboxed_hook_ms'] = measurements
                result['sandboxed_hooks_passed'] = True
            assert hooks_path.read_bytes() == original_hooks
            assert config_path.read_bytes() == original_config
        record = ROOT / 'state/token-optimizer-preflight.json'
        atomic_write(record, json.dumps(result, indent=2) + '\n')
        print(json.dumps({'record': str(record), **result}, indent=2))
        if not all(result[k] for k in checks):
            raise SystemExit(1)
        return
    native = await Native(ROOT / 'state/native.sock').connect()
    try:
        listing = await native.rpc('hooks/list', {'cwds': [str(ROOT)]})
    finally:
        await native.close()
    assert not any(g['errors'] or g['warnings'] for g in listing['data']), 'Hook loading problem'
    hooks = [h for g in listing['data'] for h in g['hooks']]
    reviewed = runpy.run_path(str(ROOT / 'Setup/trust-hooks.py'))
    hashes = {h['currentHash'] for h in hooks}
    assert len(hooks) == len(hashes) == 10 and hashes in (
        reviewed['REVIEWED'] | reviewed['TOKEN_OPTIMIZER_REVIEWED'],
        reviewed['REVIEWED_4_12'] | reviewed['TOKEN_OPTIMIZER_REVIEWED'],
        reviewed['REVIEWED_5_2'] | reviewed['TOKEN_OPTIMIZER_REVIEWED'])
    assert all(h['enabled'] and h['trustStatus'] == 'trusted' for h in hooks)
    assert len({h['key'] for h in hooks}) == len(hooks), 'Duplicate hook definition'
    installed_hooks = json.loads((Path.home() / '.codex/hooks.json').read_text())
    assert codex_install._merge_hooks(installed_hooks, enable_prompt_hooks=True) == installed_hooks
    native_config = tomllib.loads((Path.home() / '.codex/config.toml').read_text())
    compact_prompt = Path(native_config['experimental_compact_prompt_file'])
    assert compact_prompt == Path.home() / '.codex/token-optimizer/codex-compact-prompt.md'
    assert compact_prompt.read_text() == codex_compact_prompt.COMPACT_PROMPT
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
            context = result['hookSpecificOutput']['additionalContext']
            assert 'PONYTAIL MODE ACTIVE' in context and 'level: full' in context
            assert ('YAGNI' in context or 'No abstraction' in context) and 'full' in context and 'security' in context.lower()
            assert (Path(scratch) / '.ponytail-active').read_text() == 'full'
            measurements.setdefault('session_start_ms', []).append(round(elapsed, 2))
            result, elapsed = invoke('ponytail-mode-tracker.js', 'UserPromptSubmit', 'ordinary project request')
            assert not result, 'Ordinary prompt should not inject duplicate rules'
            measurements.setdefault('ordinary_prompt_ms', []).append(round(elapsed, 2))
        result, _ = invoke('ponytail-mode-tracker.js', 'UserPromptSubmit', '/ponytail off')
        assert 'PONYTAIL MODE OFF' in result['hookSpecificOutput']['additionalContext']
        assert not (Path(scratch) / '.ponytail-active').exists()

    result = {'observed_at': time.time(), 'version': manifest['version'], 'plugin_root': str(plugin),
        'config_default': config['defaultMode'], 'running_service_default': 'full',
        'native_main_pid': int(pid), 'trusted_enabled_hooks': len(hooks),
        'hooks': [{k: h[k] for k in ('eventName', 'sourcePath', 'pluginId', 'timeoutSec', 'currentHash')} for h in hooks],
        'isolated_activation_prompt_off_passed': True, 'measurements': measurements,
        'median_ms': {k: round(statistics.median(v), 2) for k, v in measurements.items()},
        'native_model_turn_started': False, 'full_tui_startup_measured': False,
        'optimizer_live_merge_idempotent': True, 'optimizer_root_compact_prompt_valid': True,
        'token_optimizer_hook_found': any('token' in h['command'].lower() and 'optim' in h['command'].lower() for h in hooks)}
    record = ROOT / 'state' / ('optimization-' + time.strftime('%Y%m%d-%H%M%S') + '.json')
    atomic_write(record, json.dumps(result, indent=2) + '\n')
    print(json.dumps({'record': str(record), **result}, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
