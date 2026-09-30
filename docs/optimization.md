# Optimization: installed state and acceptance limits

Observed on the Raspberry Pi on 2026-09-29/30. This is an incremental audit, not
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

The native `hooks/list` response now reports ten enabled, trusted definitions,
with no errors or warnings and no duplicate keys:

| Source | Events | Timeout |
| --- | --- | --- |
| `~/.codex/hooks.json`, calling `Setup/goal-hook.py` | SessionStart, UserPromptSubmit, PostToolUse, Stop | 10 seconds each |
| Ponytail `hooks/claude-codex-hooks.json` | SessionStart, UserPromptSubmit, SubagentStart | 5 seconds each |
| `~/.codex/hooks.json`, Token Optimizer pinned source runners | SessionStart, UserPromptSubmit, Stop | 20, 20, 15 seconds |

The goal adapter strips prompt/objective previews and reuses the upstream goal
parser. UserPromptSubmit is snapshot-only. Unsnooze is the existing separate
daemon/controller integration, not a second duplicate native hook. Multi-agent
execution remains disabled; an installed SubagentStart hook does not enable it.

`Setup/configure.py` backs up existing configuration before merging its handlers;
`Setup/trust-hooks.py` accepts only the exact original seven reviewed hashes or
those seven plus the three reviewed Optimizer hashes. Unknown, duplicate or
partially changed sets fail closed. Further plugins require another deliberate
review; there is no trust-all path. The existing seven hashes did not change.

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

## Token Optimizer: installed; final native execution acceptance pending

The user identified only
[`alexgreensh/token-optimizer`](https://github.com/alexgreensh/token-optimizer).
No replacement is authorized or installed. The initial inspection used
`v5.13.27`; the installed release is now **v5.13.28**, upstream commit
`0b4f87e411096b4e322bd242d22fc136feac508c`, with the small tracked compatibility
patch `Setup/token-optimizer-codex.patch`. The September 30 release only refreshed
prices: its two affected installer modules were unchanged and retained both
reproduced bugs.

The [versioned Codex documentation](https://github.com/alexgreensh/token-optimizer/blob/v5.13.28/docs/codex.md)
describes Python-stdlib hooks. Runtime inspection found that the actual CLI
defaults to `aggressive`, despite its documentation describing `balanced`.
Use an explicit profile when integrating; do not enable command rewriting,
additional subagents or its optional dashboard daemon by accident.

The defects reproduced before patching were:

- Reinstallation grew four existing goal handlers to seven, then ten; uninstall
  failed to remove the new POSIX consolidated-runner hooks. The patch recognizes
  the exact generated **whole group**, without matching foreign groups merely
  mentioning the runtime variable. Mixed owned/foreign groups are preserved.
- The compact-prompt setting was appended inside the last TOML table rather
  than at the root. The patch puts its managed block before all tables.

The existing combined check now runs install/reinstall/uninstall against
disposable configuration copies, checks foreign/mixed hook preservation, and
executes SessionStart, UserPromptSubmit and Stop in Bubblewrap with no network,
a private PID namespace, read-only host and disposable home/plugin copies.
No live HOME/CODEX_HOME variable is reassigned. Before installation use:

```sh
.venv/bin/python Setup/verify-optimization.py --token-preflight
```

After installation, add `--token-baseline` pointing to the pre-install backup
directory. The successful Pi record is `state/token-optimizer-preflight.json`:
**4 -> 7 -> 7 -> 4**, original configuration restored byte-for-byte after
uninstall, correct TOML root, foreign/mixed groups retained, no live files changed.
The final isolated run took 9633.20/571.13/624.97 ms for the three events.
Its record also lists generated health/restore markers and the Stop checkpoint,
so an empty successful exit alone cannot satisfy the execution check.
This cold-start sandbox sample is not production overhead or token savings.
The initial read-only-plugin sandbox produced the upstream bytecode-cache warning;
using writable disposable plugin copies resolved that test-environment artifact.

### Pinned installation and recovery

The native marketplace points to the reviewed local source checkout at
`/home/raspberry/CodexPi/Setup/upstream/token-optimizer`, not a moving remote main.
The plugin was installed through the native CLI from its packaged plugin,
including the same compatibility patch. Hook commands deliberately use the
pinned checkout's stable absolute path, not a latest-version resolver.
The skill copy is at
`~/.codex/plugins/cache/alexgreensh-token-optimizer/token-optimizer/5.13.28`.
Do not move/remove/update the source checkout while these hooks are installed.

Reproduce in a clean checkout of the exact commit above (check `git status`
first; never overwrite unrelated edits):

```sh
cd /home/raspberry/CodexPi/Setup/upstream/token-optimizer
git apply --check ../../token-optimizer-codex.patch
git apply ../../token-optimizer-codex.patch
git apply --check --directory=plugins/token-optimizer ../../token-optimizer-codex.patch
git apply --directory=plugins/token-optimizer ../../token-optimizer-codex.patch
cd /home/raspberry/CodexPi
.venv/bin/python Setup/verify-optimization.py --token-preflight
```

After verifying no active goals, pending lifecycle operations or Windows jobs,
back up `~/.codex/config.toml` and `hooks.json` into a new private backup directory.
Then the reviewed installation commands are:

```sh
codex plugin marketplace add /home/raspberry/CodexPi/Setup/upstream/token-optimizer
codex plugin add token-optimizer@alexgreensh-token-optimizer
.venv/bin/python Setup/upstream/token-optimizer/skills/token-optimizer/scripts/codex_install.py \
  --global --profile balanced --no-subagent-hooks --json
.venv/bin/python Setup/trust-hooks.py
.venv/bin/python Setup/verify-optimization.py
```

Never use the upstream implicit aggressive default or `--force-compact-prompt`
to overwrite a different user setting. Command rewriting, hot-path tool hooks,
Optimizer subagent hooks, custom statusline, keepwarm scheduling and dashboard
daemon were **not enabled**. No extra AI session or service was started.
The root `experimental_compact_prompt_file` is now correctly installed; all
other parsed config values survived its installation unchanged.

Actual pre-install backup:
`backups/token-optimizer-1790786922461411373/{config.toml,hooks.json}`.
Native registration is recorded in `state/token-optimizer-install.json`;
the separate hook-trust backup is
`backups/hook-trust-1790787005633900782.toml`.
For removal, quiesce normally, run the patched installer with
`--global --uninstall`, then remove this plugin/marketplace through native CLI.
Review the diff and clear only its three stale trust entries if necessary;
never blindly restore an old entire config over later user changes.
Removal preservation is tested on copies, not a claim of live rollback.

Native `hooks/list` verified all ten enabled/trusted definitions without loading
errors. The combined verifier rechecks live merge idempotency and the compact
prompt's path/content. Ponytail full-mode isolated checks still pass (90.94/
95.99 ms medians); native PID 1158 stayed unchanged. Read-only controller
preflight passed with five projects and no active goals. Reopening completed
fixture `01a0e97b-6396-7b23-98b8-83c864c0d81a` through the normal mapped TUI took
6.21 seconds including the check's waits; its complete goal and token count
were unchanged. No fresh SessionStart side effects were observed, so this
**does not prove optimizer execution in a native turn**.

Remaining acceptance: a real native turn/compaction with the installed hooks,
goal persistence and Unsnooze coexistence afterward, measured production startup
and idle overhead, and any claimed token savings. Do not infer these from a
successful installer or from the isolated hooks. The broader goal stays active.

Focused Windows checks passed for the native model-selection gate, blocking a
second executing goal, and lossless audit reconciliation (three existing tests).
The first invocation used system Python without aiohttp; rerunning in the
existing project venv passed without installing dependencies. Ponytail review
found no additional abstractions/dependencies to remove: one existing combined
verifier, the native trust mechanism and a two-function upstream patch suffice.
