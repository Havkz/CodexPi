# Optimization: installed state and acceptance limits

Observed on the Raspberry Pi on 2026-09-29. This is an incremental audit, not
final acceptance of every optimization, hook or recovery requirement.

## Ponytail installation and mode

Codex CLI is `0.155.1`; Ponytail is `4.10.0`. Its installed manifest is
`~/.codex/plugins/cache/ponytail/ponytail/4.10.0/.codex-plugin/plugin.json`.
`codex plugin list` reports `ponytail@ponytail` installed and enabled.
The latest published upstream release checked on 2026-09-29 is also
[v4.10.0](https://github.com/DietrichGebert/ponytail/releases/tag/v4.10.0).

`Setup/install-base.sh` uses the native marketplace/install commands with a
`v4.10.0` marketplace ref. The current CLI inventory nevertheless reports its
marketplace source as `main`; do not confuse the installed version with a proven
future-update pin. Reproducible update/ref handling remains an installer audit
item. No plugin upgrade was performed during this inspection.

The default is **full**, set both in `~/.config/ponytail/config.json`
(`defaultMode`) and `PONYTAIL_DEFAULT_MODE=full` in `codexpi-native.service`.
The actual running native process environment was checked, not only its unit
file. Environment takes precedence over the JSON setting. The native rollout
for recovery fixture `01a0e97b-6396-7b23-98b8-83c864c0d81a` contains one developer
context record with `PONYTAIL MODE ACTIVE` and `level: full`.
This confirms injection into a real completed goal, not merely an installed file.

`templates/AGENTS.md` explicitly preserves security, persistence, backups,
single-goal scheduling and all required integrations above code minimization.
Ponytail remains a ruleset and short-lived Node hooks, not another AI worker.

## Hook coexistence and trust

The native `hooks/list` response reports seven enabled, trusted definitions,
with no errors or warnings and no duplicate keys:

| Source | Events | Timeout |
| --- | --- | --- |
| `~/.codex/hooks.json`, calling `Setup/goal-hook.py` | SessionStart, UserPromptSubmit, PostToolUse, Stop | 10 seconds each |
| Ponytail `hooks/claude-codex-hooks.json` | SessionStart, UserPromptSubmit, SubagentStart | 5 seconds each |

The goal adapter strips prompt/objective previews and reuses the upstream goal
parser. UserPromptSubmit is snapshot-only. Unsnooze is the existing separate
daemon/controller integration, not a second duplicate native hook. Multi-agent
execution remains disabled; an installed SubagentStart hook does not enable it.

`Setup/configure.py` backs up existing configuration before merging its handlers;
`Setup/trust-hooks.py` approves only the seven reviewed definition hashes, not
arbitrary hooks. It must be deliberately reviewed/extended for any new plugin.
Never bypass hook trust or run the current seven-hook trust script blindly after
adding definitions.

The [official hook contract](https://learn.chatgpt.com/docs/hooks) runs matching
command hooks concurrently. JSON order/display order is therefore **not an
execution-order guarantee**. Goal persistence must remain independent of the
optional optimization hook: its authoritative native goal DB/controller path
does not wait for Ponytail. No artificial sequential wrapper was introduced.
If a future optimizer introduces a real dependency, it needs explicit sequencing
and failure isolation rather than relying on array order.

## Checks and measurements

On the Pi:

```sh
cd /home/raspberry/CodexPi
.venv/bin/python Setup/verify-optimization.py
.venv/bin/python Setup/measure-idle.py
```

The first command inspects native hook trust and actual mode configuration, then
runs the installed Ponytail activation/prompt/off handlers with disposable
plugin data. Three paired samples on ARM64 passed: activation emits full-mode
rules, ordinary prompts do not re-inject them, and off removes only the temporary
mode flag. It starts no Codex goal and changes no real session's mode.
Record: `state/optimization-20260929-212155.json`.

Median SessionStart hook wall time was **94.55 ms** (88.64–95.55 ms), including
Node startup; ordinary UserPromptSubmit was **94.84 ms** (91.89–95.73 ms).
These are hook measurements, **not** total TUI startup time or a controlled
enabled-versus-disabled comparison. Full startup impact remains unverified.

The existing 60.10-second idle check measured **370.11 MiB process PSS**,
**425.71 MiB cgroup memory**, and **10.28% of one CPU core** for the three CodexPi
units. Their four surviving processes were controller Python, native Codex,
code-mode host and Unsnooze Node; no Ponytail process remained. The controller
accounted for 10.04 percentage points, native 0.22 and Unsnooze 0.02.
This is total infrastructure usage, not measured marginal Ponytail overhead.
The controller CPU increase versus the earlier sample needs final profiling;
do not label this sample final or attribute it to Ponytail without evidence.
No unrelated Pi service was stopped or counted. See `resources.md`.

## Disabling Ponytail when explicitly requested

`/ponytail off` (or the standalone `stop ponytail`) turns its current mode off;
the isolated handler check verified that action. A later SessionStart uses the
configured default again. For a persistent, explicitly requested opt-out, back
up the JSON configuration and native user unit, set both the service environment
and JSON default to `off`, and reload/restart the native service **only after
normal pause/quiescence and no unfinished jobs**. Changing JSON alone cannot
override the current environment setting. Do not disable all Codex hooks:
goal persistence/notifier hooks must remain enabled. Restore both defaults to
`full` to return to the specified configuration. No live opt-out was performed.

## Token Optimizer: exact selected repository, installation not yet accepted

The user identified only
[`alexgreensh/token-optimizer`](https://github.com/alexgreensh/token-optimizer).
No replacement is authorized. Its Codex adapter exists; release `v5.13.27`,
commit `9ea1977acab5ab57421068064fc3bf2f0d4b2fdf`, was cloned for inspection under
`Setup/upstream/token-optimizer` on Windows and Pi. It has **not** been activated
or installed into global hooks. The clone is not an installation claim.

The [versioned Codex documentation](https://github.com/alexgreensh/token-optimizer/blob/v5.13.27/docs/codex.md)
describes Python-stdlib hooks. Runtime inspection found that the actual CLI
defaults to `aggressive`, despite its documentation describing `balanced`.
Use an explicit profile when integrating; do not enable command rewriting,
additional subagents or its optional dashboard daemon by accident.

The combined, in-memory installer check is reproducible on the Pi:

```sh
.venv/bin/python Setup/verify-optimization.py --token-preflight
```

It currently exits 1, with `state/token-optimizer-preflight.json` recording:

- Four existing goal handlers become seven on the first proposed installation
  and ten on the second. `_is_token_optimizer_group` does not recognize the new
  POSIX consolidated-runner command shape, so merge repeats it and uninstall
  leaves all seven instead of restoring the original four.
- `_replace_or_append_config` appends the compact-prompt assignment after the
  existing TOML tables. Parsing the proposed configuration confirms that
  `experimental_compact_prompt_file` is not at the root, so the intended global
  setting would not take effect.

No live config was written by this check. These are reproduced installer
compatibility defects, not evidence that every Token Optimizer feature is
incompatible with Codex. Integration remains pending until these defects and
the active hook paths have been safely addressed and tested. Preserve current
goal/Ponytail hashes, validate merged config, and test recovery/Unsnooze afterward.
No alternative tool will be installed without asking the user.
