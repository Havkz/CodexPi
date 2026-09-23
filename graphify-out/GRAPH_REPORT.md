# Graph Report - CodexPi  (2026-09-23)

## Corpus Check
- 54 files · ~66,128 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 313 nodes · 669 edges · 30 communities (21 shown, 9 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 66 edges (avg confidence: 0.67)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `8aabd594`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- common.py
- Controller
- windows_worker.py
- Native
- Database
- web.py
- dashboard.js
- CodexPi installation progress
- build_audit.py
- connect-github.py
- install-base.sh
- verify-dashboard.py
- __init__.py
- AGENTS.md
- main.py
- test-live-queue.py
- verify-design.py
- Design verification — 2026-09-20
- test-live-lifecycle.py
- Unsnooze integration
- Bot
- GoalSource
- Pi infrastructure resource measurements
- verify-sandbox.py
- main

## God Nodes (most connected - your core abstractions)
1. `Controller` - 40 edges
2. `Database` - 37 edges
3. `command()` - 23 edges
4. `Redactor` - 22 edges
5. `SchedulerTests` - 21 edges
6. `atomic_write()` - 17 edges
7. `Bot` - 14 edges
8. `Native` - 14 edges
9. `SignedChannel` - 13 edges
10. `finish()` - 13 edges

## Surprising Connections (you probably didn't know these)
- `main()` --indirect_call--> `action()`  [INFERRED]
  Setup/verify-lifecycle-fixes.py → app/web.py
- `Crash` --uses--> `Controller`  [INFERRED]
  tests/test_lifecycle.py → app/controller.py
- `LifecycleTests` --uses--> `Controller`  [INFERRED]
  tests/test_lifecycle.py → app/controller.py
- `SchedulerTests` --uses--> `Controller`  [INFERRED]
  tests/test_scheduler.py → app/controller.py
- `CoreTests` --uses--> `Database`  [INFERRED]
  tests/test_core.py → app/db.py

## Import Cycles
- None detected.

## Communities (30 total, 9 thin omitted)

### Community 0 - "common.py"
Cohesion: 0.29
Nodes (6): Changes, Completion gate follow-up, Lifecycle repair evidence, 2026-09-23, Reproduction and exact causes, Verification boundaries and remaining work, Verified live

### Community 1 - "Controller"
Cohesion: 0.17
Nodes (5): command(), Controller, RuntimeError, Probe the installed native protocol without requesting any model work., rpc()

### Community 2 - "windows_worker.py"
Cohesion: 0.19
Nodes (11): execute(), main(), protect_secret(), Outbound-only native Windows executor. This process never starts an AI agent., Windows DPAPI CurrentUser; no machine-wide or plaintext key file., relative_path(), validate_job(), Worker (+3 more)

### Community 4 - "Native"
Cohesion: 0.08
Nodes (26): slugify(), CloseView, begin(), channel(), finish(), move_owned(), owned_path(), Durable, idempotent project lifecycle steps. SQLite is the operation journal. (+18 more)

### Community 5 - "Database"
Cohesion: 0.33
Nodes (5): Delete, Interrupted operation recovery, Project lifecycle, Rename, Verified on 2026-09-20

### Community 6 - "web.py"
Cohesion: 0.11
Nodes (21): canonical(), password_hash(), password_valid(), Per-connection random challenge + directional MAC + monotonic sequence., SignedChannel, action(), authorize(), index() (+13 more)

### Community 7 - "dashboard.js"
Cohesion: 0.42
Nodes (16): act(), actions(), badge(), block(), button(), date(), link(), metadata() (+8 more)

### Community 8 - "CodexPi installation progress"
Cohesion: 0.29
Nodes (6): CodexPi installation progress, Source references, Verified 2026-09-19, Verified 2026-09-20 (incremental, not final acceptance), Verified 2026-09-21 (incremental, not final acceptance), Work still required

### Community 9 - "build_audit.py"
Cohesion: 0.40
Nodes (4): Installation and autostart, Protocol and jobs, Verification status, Windows worker

### Community 21 - "main.py"
Cohesion: 0.06
Nodes (11): Redactor, Database, Bot, One compact text hierarchy: vertical indentation, not a grid of fields., status_embed(), BaseException, DiscordTests, Crash (+3 more)

### Community 23 - "verify-design.py"
Cohesion: 0.67
Nodes (3): main(), no_overflow(), Live, non-destructive browser checks; isolated headless Edge, no saved credentia

### Community 24 - "Design verification — 2026-09-20"
Cohesion: 0.40
Nodes (4): Design verification — 2026-09-20, Implemented and deployed to the Pi, Still open — not waived, Verified evidence

### Community 25 - "test-live-lifecycle.py"
Cohesion: 0.67
Nodes (5): main(), open_project(), Create, rename and delete ONLY a dedicated lifecycle E2E project via real UI.  P, remote(), verify_deleted()

### Community 26 - "Unsnooze integration"
Cohesion: 0.50
Nodes (3): Unsnooze integration, Verification boundaries, Why the manual CLI wake cannot be used safely here

### Community 27 - "Bot"
Cohesion: 0.16
Nodes (14): atomic_write(), read_env(), main(), dispatch_pending(), send(), submit_job(), unblock_windows(), worker_socket() (+6 more)

### Community 32 - "main"
Cohesion: 0.33
Nodes (4): Exercise the two explicitly named E2E projects through the authenticated dashboa, state(), main(), Resume only the existing queue E2E goal; never create or replace an objective.

## Knowledge Gaps
- **26 isolated node(s):** `install-base.sh script`, `PATH`, `Implemented and deployed to the Pi`, `Verified evidence`, `Still open — not waived` (+21 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Controller` connect `Controller` to `Bot`, `Native`, `main.py`?**
  _High betweenness centrality (0.089) - this node is a cross-community bridge._
- **Why does `Database` connect `main.py` to `Controller`, `Native`, `web.py`?**
  _High betweenness centrality (0.082) - this node is a cross-community bridge._
- **Why does `command()` connect `Controller` to `Bot`, `Native`, `main.py`, `web.py`?**
  _High betweenness centrality (0.048) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `Controller` (e.g. with `Redactor` and `Database`) actually correct?**
  _`Controller` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `Database` (e.g. with `Controller` and `CoreTests`) actually correct?**
  _`Database` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `command()` (e.g. with `RuntimeError` and `.make_controller()`) actually correct?**
  _`command()` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `Redactor` (e.g. with `Controller` and `DiscordTests`) actually correct?**
  _`Redactor` has 6 INFERRED edges - model-reasoned connections that need verification._