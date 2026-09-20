# Graph Report - CodexPi  (2026-09-20)

## Corpus Check
- 41 files · ~52,756 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 225 nodes · 489 edges · 25 communities (18 shown, 7 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 43 edges (avg confidence: 0.65)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `6558ad86`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- common.py
- Controller
- windows_worker.py
- main.py
- Native
- Database
- web.py
- dashboard.js
- CodexPi installation progress
- build_audit.py
- connect-github.py
- discord-token.py
- install-base.sh
- verify-dashboard.py
- __init__.py
- AGENTS.md
- main.py
- test-live-queue.py
- verify-design.py
- Design verification — 2026-09-20

## God Nodes (most connected - your core abstractions)
1. `Controller` - 31 edges
2. `Database` - 27 edges
3. `Redactor` - 17 edges
4. `atomic_write()` - 15 edges
5. `command()` - 15 edges
6. `SignedChannel` - 13 edges
7. `Native` - 13 edges
8. `Bot` - 12 edges
9. `make_app()` - 11 edges
10. `node()` - 11 edges

## Surprising Connections (you probably didn't know these)
- `SchedulerTests` --uses--> `Redactor`  [INFERRED]
  tests/test_scheduler.py → app/common.py
- `WebTests` --uses--> `Redactor`  [INFERRED]
  tests/test_web.py → app/common.py
- `SchedulerTests` --uses--> `Controller`  [INFERRED]
  tests/test_scheduler.py → app/controller.py
- `DiscordTests` --uses--> `Database`  [INFERRED]
  tests/test_discord.py → app/db.py
- `main()` --calls--> `atomic_write()`  [EXTRACTED]
  Setup/build_audit.py → app/common.py

## Import Cycles
- None detected.

## Communities (25 total, 7 thin omitted)

### Community 0 - "common.py"
Cohesion: 0.43
Nodes (4): main(), Create a lossless, line-addressed audit from the user's specification.  Every no, reconcile(), AuditTests

### Community 1 - "Controller"
Cohesion: 0.17
Nodes (6): command(), Controller, project_thread_config(), RuntimeError, Probe the installed native protocol without requesting any model work., rpc()

### Community 2 - "windows_worker.py"
Cohesion: 0.19
Nodes (12): atomic_write(), execute(), main(), protect_secret(), Outbound-only native Windows executor. This process never starts an AI agent., Windows DPAPI CurrentUser; no machine-wide or plaintext key file., relative_path(), validate_job() (+4 more)

### Community 3 - "main.py"
Cohesion: 0.18
Nodes (7): Redactor, Bot, CloseView, One compact text hierarchy: vertical indentation, not a grid of fields., status_embed(), button, DiscordTests

### Community 4 - "Native"
Cohesion: 0.18
Nodes (8): GoalSource, Native, NativeError, Native Codex 0.155.1 RPC and the scheduler's local TUI admission gate., Reuse upstream parsing and event comparison; never retain objective text., tui_proxy(), main(), Trust only the seven reviewed hook definitions, through Codex's native API.

### Community 5 - "Database"
Cohesion: 0.09
Nodes (11): canonical(), password_hash(), password_valid(), Per-connection random challenge + directional MAC + monotonic sequence., SignedChannel, slugify(), Database, Generate only a password hash from the user-owned specification. (+3 more)

### Community 6 - "web.py"
Cohesion: 0.29
Nodes (12): action(), authorize(), index(), login(), make_app(), project_detail(), safe_json(), security() (+4 more)

### Community 7 - "dashboard.js"
Cohesion: 0.46
Nodes (15): act(), actions(), badge(), block(), button(), date(), link(), metadata() (+7 more)

### Community 8 - "CodexPi installation progress"
Cohesion: 0.33
Nodes (5): CodexPi installation progress, Source references, Verified 2026-09-19, Verified 2026-09-20 (incremental, not final acceptance), Work still required

### Community 9 - "build_audit.py"
Cohesion: 0.40
Nodes (4): Installation and autostart, Protocol and jobs, Verification status, Windows worker

### Community 21 - "main.py"
Cohesion: 0.24
Nodes (9): read_env(), main(), dispatch_pending(), send(), submit_job(), unblock_windows(), worker_socket(), Run on Pi after copying reviewed sources; preserve and back up user config. (+1 more)

### Community 23 - "verify-design.py"
Cohesion: 0.67
Nodes (3): main(), no_overflow(), Live, non-destructive browser checks; isolated headless Edge, no saved credentia

### Community 24 - "Design verification — 2026-09-20"
Cohesion: 0.40
Nodes (4): Design verification — 2026-09-20, Implemented and deployed to the Pi, Still open — not waived, Verified evidence

## Knowledge Gaps
- **13 isolated node(s):** `install-base.sh script`, `PATH`, `Implemented and deployed to the Pi`, `Verified evidence`, `Still open — not waived` (+8 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Controller` connect `Controller` to `main.py`, `main.py`, `Native`, `Database`?**
  _High betweenness centrality (0.097) - this node is a cross-community bridge._
- **Why does `Database` connect `Database` to `Controller`, `main.py`, `Native`?**
  _High betweenness centrality (0.084) - this node is a cross-community bridge._
- **Why does `atomic_write()` connect `windows_worker.py` to `common.py`, `Controller`, `main.py`, `Database`, `main.py`?**
  _High betweenness centrality (0.045) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `Controller` (e.g. with `Redactor` and `Database`) actually correct?**
  _`Controller` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `Database` (e.g. with `Controller` and `CoreTests`) actually correct?**
  _`Database` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `Redactor` (e.g. with `Controller` and `DiscordTests`) actually correct?**
  _`Redactor` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `RuntimeError` (e.g. with `command()` and `.finish_creation()`) actually correct?**
  _`RuntimeError` has 15 INFERRED edges - model-reasoned connections that need verification._