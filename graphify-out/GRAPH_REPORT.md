# Graph Report - CodexPi  (2026-10-12)

## Corpus Check
- 101 files · ~136,983 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 749 nodes · 2020 edges · 57 communities (39 shown, 18 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 238 edges (avg confidence: 0.71)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `e27a5c79`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- common.py
- Controller
- windows_worker.py
- deployment.py
- Native
- Database
- DeploymentTests
- dashboard.js
- CodexPi installation progress
- build_audit.py
- connect-github.py
- install-base.sh
- verify-dashboard.py
- __init__.py
- codexpi-tool
- AGENTS.md
- worker_server.py
- test-live-queue.py
- verify-design.py
- Design verification — 2026-09-20
- test-live-lifecycle.py
- Unsnooze integration
- Database
- GoalSource
- Pi infrastructure resource measurements
- verify-sandbox.py
- Durable manual pause and real quota evidence, 2026-09-24
- main
- verify-deployment.py
- migration.py
- Bot
- usage.js
- controller.py
- Native
- Bot
- build-favicon.py
- Recovery and operator runbook
- Architecture and data ownership
- CodexPi
- DeploymentTests
- Selected Windows session migration
- Durable manual pause and real quota evidence, 2026-09-24
- verify-account-ui.py
- export
- test-live-lifecycle.py
- .rpc
- GoalSource
- NativeError
- Bot
- build_audit.py
- verify-pause-policy.py

## God Nodes (most connected - your core abstractions)
1. `Database` - 86 edges
2. `SchedulerTests` - 65 edges
3. `Controller` - 63 edges
4. `command()` - 45 edges
5. `atomic_write()` - 43 edges
6. `Native` - 31 edges
7. `tick()` - 28 edges
8. `Worker` - 28 edges
9. `Redactor` - 27 edges
10. `NativeError` - 24 edges

## Surprising Connections (you probably didn't know these)
- `main()` --indirect_call--> `save()`  [INFERRED]
  Setup/discord-token.py → app/lifecycle.py
- `main()` --indirect_call--> `action()`  [INFERRED]
  Setup/verify-lifecycle-fixes.py → app/web.py
- `state()` --indirect_call--> `native()`  [INFERRED]
  app/web.py → Setup/verify-pause-policy.py
- `CoreTests` --uses--> `SignedChannel`  [INFERRED]
  tests/test_core.py → app/common.py
- `Crash` --uses--> `Redactor`  [INFERRED]
  tests/test_lifecycle.py → app/common.py

## Import Cycles
- None detected.

## Communities (57 total, 18 thin omitted)

### Community 0 - "common.py"
Cohesion: 0.29
Nodes (6): Changes, Completion gate follow-up, Lifecycle repair evidence, 2026-09-23, Reproduction and exact causes, Verification boundaries and remaining work, Verified live

### Community 2 - "windows_worker.py"
Cohesion: 0.06
Nodes (32): check(), install(), Reject paid-runner workflows before a managed Git push can trigger them., validate(), codex_login_url(), Only the native managed OAuth ceremony, never an arbitrary worker/browser URL., ExecutionSlot, identity() (+24 more)

### Community 3 - "deployment.py"
Cohesion: 0.09
Nodes (48): slugify(), complete(), finish(), key(), quote(), Explicit 24/7 Pi delivery, completed through the existing lifecycle journal., Called under the controller lock, after final Git/CI checks., relocate_session() (+40 more)

### Community 4 - "Native"
Cohesion: 0.22
Nodes (8): Checks and measurements, Disabling Ponytail when explicitly requested, Hook coexistence and trust, Native execution on 2026-10-01, Optimization: installed state and acceptance limits, Pinned installation and recovery, Ponytail installation and mode, Token Optimizer: installed; native execution verified

### Community 5 - "Database"
Cohesion: 0.33
Nodes (5): Delete, Interrupted operation recovery, Project lifecycle, Rename, Verified on 2026-09-20

### Community 7 - "dashboard.js"
Cohesion: 0.30
Nodes (22): accountAct(), accountPending(), act(), actions(), badge(), block(), button(), date() (+14 more)

### Community 8 - "CodexPi installation progress"
Cohesion: 0.12
Nodes (16): 2026-09-25 controller-crash verification and runbooks, 2026-09-25 usage-history implementation and live verification, 2026-09-27/28 worker admission and top-of-dashboard usage, 2026-09-28 Windows heartbeat and worker recovery, 2026-09-29 active-goal recovery evidence closure, 2026-09-29 optimization inventory and installer defects, 2026-09-30 Token Optimizer compatibility patch and installation, 2026-10-01 native Optimizer execution and migration priority (+8 more)

### Community 9 - "build_audit.py"
Cohesion: 0.50
Nodes (4): Installation and autostart, Protocol and jobs, Verification status, Windows worker

### Community 21 - "worker_server.py"
Cohesion: 0.10
Nodes (27): busy(), poll(), Observe real local GitHub jobs before admitting lower-priority Windows work., register(), registrations(), setup_inventory(), setup_result(), canonical() (+19 more)

### Community 23 - "verify-design.py"
Cohesion: 0.67
Nodes (3): main(), no_overflow(), Live, non-destructive browser checks; isolated headless Edge, no saved credentia

### Community 24 - "Design verification — 2026-09-20"
Cohesion: 0.40
Nodes (4): Design verification — 2026-09-20, Implemented and deployed to the Pi, Still open — not waived, Verified evidence

### Community 26 - "Unsnooze integration"
Cohesion: 0.40
Nodes (5): Auto Continue, Overnight missed wake, 2026-10-06, Unsnooze integration, Verification boundaries, Why the manual CLI wake cannot be used safely here

### Community 29 - "Pi infrastructure resource measurements"
Cohesion: 0.33
Nodes (5): 2026-10-05 redundant idle writes (local reproduction), Incremental 2026-09-29 sample, Incremental 2026-10-01 post-Optimizer sample, Pi infrastructure resource measurements, Warm idle sample (60.10 seconds)

### Community 33 - "verify-deployment.py"
Cohesion: 0.67
Nodes (3): main(), observe(), Start/observe one real deployment goal; never replace an existing objective.  De

### Community 34 - "migration.py"
Cohesion: 0.11
Nodes (43): AccountVault, auth_identity(), automatic_change(), bind_legacy_limits(), choose_account(), failed_resume(), finish_switch(), fresh_usage() (+35 more)

### Community 35 - "Bot"
Cohesion: 0.33
Nodes (5): Data and boundaries, Existing-logo favicon, Presentation, Usage / Limits history, Verification as of 2026-09-25

### Community 36 - "usage.js"
Cohesion: 0.44
Nodes (9): hideUsageTooltip(), refreshUsage(), renderUsage(), showUsageTooltip(), usageChart, usageDate(), usageElement(), usagePercent() (+1 more)

### Community 37 - "controller.py"
Cohesion: 0.21
Nodes (16): daily_update(), idle(), Daily official CLI update, only at a proven idle single-runtime boundary., idle_thread(), process_in_pane(), project_thread_config(), Native Codex RPC and the scheduler's local TUI admission gate., Bind a Unix TUI peer to the current pane, including launcher children. (+8 more)

### Community 38 - "Native"
Cohesion: 0.18
Nodes (8): Native, main(), Trust only the reviewed goal/Ponytail and optional Token Optimizer definitions., main(), Pi hook inventory and isolated Ponytail checks; no model turn or live config wri, main(), Read-only live check on the Pi: real --all picker, wheel, pager and unsent draft, tmux()

### Community 39 - "Bot"
Cohesion: 0.07
Nodes (38): public_state(), Explicit allowlist: never serialize an auth file, OAuth URL or raw RPC error., block_summary(), capacity_wait(), password_hash(), password_valid(), Presentation only: never change native status or resume authorization., read_env() (+30 more)

### Community 41 - "Recovery and operator runbook"
Cohesion: 0.20
Nodes (9): Backups, Isolated SQLite restore, 2026-10-06, Live active-goal controller crash, 2026-09-28, Live controller crash, 2026-09-25, Normal process recovery, Recovery and operator runbook, Restore procedure and stop conditions, Safe diagnosis (+1 more)

### Community 42 - "Architecture and data ownership"
Cohesion: 0.40
Nodes (5): Architecture and data ownership, Modules and files, Process and trust boundaries, Queue, acknowledgement and recovery, Source of truth

### Community 43 - "CodexPi"
Cohesion: 0.40
Nodes (5): Alltag, CodexPi, Dokumentation, Entwicklung und Prüfung, Installation und Betrieb

### Community 44 - "DeploymentTests"
Cohesion: 0.33
Nodes (5): Conclusion and safe next evidence, Existing non-CodexPi services, Observed, not inferred, Separate reproducible CodexPi write-load defect, Unexpected Pi restarts — 2026-10-05

### Community 45 - "Selected Windows session migration"
Cohesion: 0.33
Nodes (5): Current evidence and unfinished verification, Fidelity and compatibility, Reusable mechanism, Scope and source, Selected Windows session migration

### Community 47 - "Durable manual pause and real quota evidence, 2026-09-24"
Cohesion: 0.50
Nodes (3): Durable manual pause and real quota evidence, 2026-09-24, Pause authority, Real usage-limit history

### Community 49 - "export"
Cohesion: 0.14
Nodes (7): notification(), One journaled restart, then bounded observations; never replay a model request., reload_native(), dispatch_ci(), One durable submission per commit; an uncertain POST is never retried., command(), Controller

### Community 50 - "test-live-lifecycle.py"
Cohesion: 0.09
Nodes (25): RuntimeError, configure_hooks(), gh(), install(), main(), Register the official Windows services for explicitly selected private CodexPi r, validate_repository(), Probe the installed native protocol without requesting any model work. (+17 more)

### Community 52 - "GoalSource"
Cohesion: 0.25
Nodes (4): GoalSource, Reuse upstream parsing and event comparison; never retain objective text., Read-only Pi resource sample; refuse to label an active-goal run as idle., sample()

### Community 53 - "NativeError"
Cohesion: 0.32
Nodes (4): LoginRequired, Explicit native auth rejection, never a timeout or identity mismatch., NativeError, WebTests

### Community 54 - "Bot"
Cohesion: 0.07
Nodes (15): Database, Only after confirming the original single-account identity; never guess on switc, BaseException, identities(), main(), Isolated infrastructure-DB restore drill on Pi; never starts or restores live se, readonly(), services() (+7 more)

### Community 55 - "build_audit.py"
Cohesion: 0.43
Nodes (4): main(), Create a lossless, line-addressed audit from the user's specification.  Every no, reconcile(), AuditTests

### Community 56 - "verify-pause-policy.py"
Cohesion: 0.67
Nodes (3): main(), native(), Live manual pause/restart/queued-resume test on one dedicated native goal.  Neve

## Knowledge Gaps
- **77 isolated node(s):** `install-base.sh script`, `PATH`, `usageChart`, `Alltag`, `Installation und Betrieb` (+72 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **18 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Database` connect `Bot` to `Controller`, `migration.py`, `deployment.py`, `windows_worker.py`, `controller.py`, `Bot`, `export`, `test-live-lifecycle.py`, `.rpc`, `GoalSource`, `worker_server.py`, `NativeError`?**
  _High betweenness centrality (0.089) - this node is a cross-community bridge._
- **Why does `SchedulerTests` connect `Controller` to `migration.py`, `controller.py`, `Native`, `Bot`, `export`, `test-live-lifecycle.py`, `.rpc`, `NativeError`, `Bot`, `worker_server.py`?**
  _High betweenness centrality (0.053) - this node is a cross-community bridge._
- **Why does `Controller` connect `export` to `Controller`, `windows_worker.py`, `deployment.py`, `controller.py`, `Native`, `Bot`, `GoalSource`, `NativeError`, `Bot`, `worker_server.py`?**
  _High betweenness centrality (0.053) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `Database` (e.g. with `Controller` and `AccountObservationTests`) actually correct?**
  _`Database` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 66 inferred relationships involving `ValueError` (e.g. with `check()` and `install()`) actually correct?**
  _`ValueError` has 66 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `SchedulerTests` (e.g. with `AccountObservationTests` and `AccountSwitchTests`) actually correct?**
  _`SchedulerTests` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 11 inferred relationships involving `Controller` (e.g. with `Redactor` and `Database`) actually correct?**
  _`Controller` has 11 INFERRED edges - model-reasoned connections that need verification._