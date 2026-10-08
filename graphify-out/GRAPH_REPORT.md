# Graph Report - CodexPi  (2026-10-08)

## Corpus Check
- 88 files · ~115,154 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 634 nodes · 1625 edges · 53 communities (36 shown, 17 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 177 edges (avg confidence: 0.69)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `48fbffb1`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- common.py
- Controller
- windows_worker.py
- deployment.py
- Native
- Database
- web.py
- dashboard.js
- CodexPi installation progress
- build_audit.py
- connect-github.py
- Bot
- install-base.sh
- verify-dashboard.py
- __init__.py
- codexpi
- AGENTS.md
- main.py
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
- db.py
- SchedulerTests
- verify-usage-ui.py
- build-favicon.py
- Recovery and operator runbook
- Architecture and data ownership
- CodexPi
- DeploymentTests
- Selected Windows session migration
- SchedulerTests
- Durable manual pause and real quota evidence, 2026-09-24
- verify-account-ui.py
- export
- test-live-lifecycle.py
- tui_proxy

## God Nodes (most connected - your core abstractions)
1. `Database` - 72 edges
2. `Controller` - 55 edges
3. `SchedulerTests` - 47 edges
4. `command()` - 41 edges
5. `atomic_write()` - 37 edges
6. `tick()` - 29 edges
7. `Native` - 28 edges
8. `Redactor` - 27 edges
9. `finish()` - 21 edges
10. `AccountVault` - 20 edges

## Surprising Connections (you probably didn't know these)
- `main()` --indirect_call--> `save()`  [INFERRED]
  Setup/discord-token.py → app/lifecycle.py
- `main()` --indirect_call--> `action()`  [INFERRED]
  Setup/verify-lifecycle-fixes.py → app/web.py
- `CoreTests` --uses--> `SignedChannel`  [INFERRED]
  tests/test_core.py → app/common.py
- `LifecycleTests` --uses--> `Redactor`  [INFERRED]
  tests/test_lifecycle.py → app/common.py
- `SchedulerTests` --uses--> `Redactor`  [INFERRED]
  tests/test_scheduler.py → app/common.py

## Import Cycles
- None detected.

## Communities (53 total, 17 thin omitted)

### Community 0 - "common.py"
Cohesion: 0.29
Nodes (6): Changes, Completion gate follow-up, Lifecycle repair evidence, 2026-09-23, Reproduction and exact causes, Verification boundaries and remaining work, Verified live

### Community 1 - "Controller"
Cohesion: 0.09
Nodes (26): notification(), wake_key(), command(), Controller, daily_update(), idle(), Daily official CLI update, only at a proven idle single-runtime boundary., GoalSource (+18 more)

### Community 2 - "windows_worker.py"
Cohesion: 0.14
Nodes (14): codex_login_url(), Only the native managed OAuth ceremony, never an arbitrary worker/browser URL., execute(), main(), protect_secret(), Outbound-only native Windows executor. This process never starts an AI agent., One owned callback tunnel. No AI, logout, saved tokens or project execution., Windows DPAPI CurrentUser; no machine-wide or plaintext key file. (+6 more)

### Community 3 - "deployment.py"
Cohesion: 0.10
Nodes (44): slugify(), complete(), finish(), key(), quote(), Explicit 24/7 Pi delivery, completed through the existing lifecycle journal., Called under the controller lock, after final Git/CI checks., relocate_session() (+36 more)

### Community 4 - "Native"
Cohesion: 0.22
Nodes (8): Checks and measurements, Disabling Ponytail when explicitly requested, Hook coexistence and trust, Native execution on 2026-10-01, Optimization: installed state and acceptance limits, Pinned installation and recovery, Ponytail installation and mode, Token Optimizer: installed; native execution verified

### Community 5 - "Database"
Cohesion: 0.33
Nodes (5): Delete, Interrupted operation recovery, Project lifecycle, Rename, Verified on 2026-09-20

### Community 6 - "web.py"
Cohesion: 0.07
Nodes (25): block_summary(), canonical(), Per-connection random challenge + directional MAC + monotonic sequence., Presentation only: never change native status or resume authorization., read_env(), Redactor, SignedChannel, Bot (+17 more)

### Community 7 - "dashboard.js"
Cohesion: 0.30
Nodes (21): accountAct(), accountPending(), act(), actions(), badge(), block(), button(), date() (+13 more)

### Community 8 - "CodexPi installation progress"
Cohesion: 0.12
Nodes (16): 2026-09-25 controller-crash verification and runbooks, 2026-09-25 usage-history implementation and live verification, 2026-09-27/28 worker admission and top-of-dashboard usage, 2026-09-28 Windows heartbeat and worker recovery, 2026-09-29 active-goal recovery evidence closure, 2026-09-29 optimization inventory and installer defects, 2026-09-30 Token Optimizer compatibility patch and installation, 2026-10-01 native Optimizer execution and migration priority (+8 more)

### Community 9 - "build_audit.py"
Cohesion: 0.50
Nodes (4): Installation and autostart, Protocol and jobs, Verification status, Windows worker

### Community 11 - "Bot"
Cohesion: 0.19
Nodes (8): Native, main(), Trust only the reviewed goal/Ponytail and optional Token Optimizer definitions., main(), Pi hook inventory and isolated Ponytail checks; no model turn or live config wri, main(), Read-only live check on the Pi: real --all picker, wheel, pager and unsent draft, tmux()

### Community 15 - "codexpi"
Cohesion: 0.22
Nodes (6): Exercise the two explicitly named E2E projects through the authenticated dashboa, state(), main(), Live recovery; explicit --crash or --worker-restart injects a fault.  Never kill, main(), Resume only the existing queue E2E goal; never create or replace an objective.

### Community 21 - "main.py"
Cohesion: 0.10
Nodes (9): Database, Only after confirming the original single-account identity; never guess on switc, identities(), main(), Isolated infrastructure-DB restore drill on Pi; never starts or restores live se, readonly(), services(), DeploymentTests (+1 more)

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
Cohesion: 0.10
Nodes (47): AccountVault, auth_identity(), automatic_change(), bind_legacy_limits(), choose_account(), failed_resume(), finish_switch(), fresh_usage() (+39 more)

### Community 35 - "Bot"
Cohesion: 0.33
Nodes (5): Data and boundaries, Existing-logo favicon, Presentation, Usage / Limits history, Verification as of 2026-09-25

### Community 36 - "usage.js"
Cohesion: 0.57
Nodes (6): refreshUsage(), renderUsage(), usageDate(), usageElement(), usagePercent(), usageSvg()

### Community 37 - "db.py"
Cohesion: 0.10
Nodes (26): public_state(), Explicit allowlist: never serialize an auth file, OAuth URL or raw RPC error., password_hash(), password_valid(), action(), authorize(), favicon(), index() (+18 more)

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

### Community 46 - "SchedulerTests"
Cohesion: 0.43
Nodes (4): main(), Create a lossless, line-addressed audit from the user's specification.  Every no, reconcile(), AuditTests

### Community 47 - "Durable manual pause and real quota evidence, 2026-09-24"
Cohesion: 0.50
Nodes (3): Durable manual pause and real quota evidence, 2026-09-24, Pause authority, Real usage-limit history

### Community 49 - "export"
Cohesion: 0.36
Nodes (8): digest(), export(), git(), main(), native_state(), Export one explicitly selected Windows project/session without changing it.  The, Keep only this thread's indexed history/metadata, never another thread., regular()

### Community 50 - "test-live-lifecycle.py"
Cohesion: 0.67
Nodes (5): main(), open_project(), Create, rename and delete ONLY a dedicated lifecycle E2E project via real UI.  P, remote(), verify_deleted()

## Knowledge Gaps
- **76 isolated node(s):** `install-base.sh script`, `PATH`, `Alltag`, `Installation und Betrieb`, `Dokumentation` (+71 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **17 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Database` connect `main.py` to `Controller`, `migration.py`, `deployment.py`, `db.py`, `web.py`, `SchedulerTests`, `tui_proxy`, `.rpc`?**
  _High betweenness centrality (0.083) - this node is a cross-community bridge._
- **Why does `Controller` connect `Controller` to `deployment.py`, `SchedulerTests`, `web.py`, `Bot`, `main.py`?**
  _High betweenness centrality (0.050) - this node is a cross-community bridge._
- **Why does `SchedulerTests` connect `SchedulerTests` to `Controller`, `migration.py`, `web.py`, `tui_proxy`, `.rpc`, `main.py`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **Are the 14 inferred relationships involving `Database` (e.g. with `Controller` and `AccountObservationTests`) actually correct?**
  _`Database` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Are the 47 inferred relationships involving `ValueError` (e.g. with `codex_login_url()` and `.__init__()`) actually correct?**
  _`ValueError` has 47 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `Controller` (e.g. with `Redactor` and `Database`) actually correct?**
  _`Controller` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `SchedulerTests` (e.g. with `AccountObservationTests` and `AccountSwitchTests`) actually correct?**
  _`SchedulerTests` has 6 INFERRED edges - model-reasoned connections that need verification._