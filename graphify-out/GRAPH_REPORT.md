# Graph Report - CodexPi  (2026-09-20)

## Corpus Check
- 38 files · ~48,695 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 197 nodes · 403 edges · 23 communities (16 shown, 7 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 40 edges (avg confidence: 0.66)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `c2f0b9d1`
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

## God Nodes (most connected - your core abstractions)
1. `Controller` - 31 edges
2. `Database` - 24 edges
3. `Redactor` - 14 edges
4. `atomic_write()` - 13 edges
5. `SignedChannel` - 13 edges
6. `command()` - 13 edges
7. `Native` - 13 edges
8. `Worker` - 11 edges
9. `make_app()` - 10 edges
10. `Bot` - 9 edges

## Surprising Connections (you probably didn't know these)
- `CoreTests` --uses--> `SignedChannel`  [INFERRED]
  tests/test_core.py → app/common.py
- `SchedulerTests` --uses--> `Controller`  [INFERRED]
  tests/test_scheduler.py → app/controller.py
- `SchedulerTests` --uses--> `Redactor`  [INFERRED]
  tests/test_scheduler.py → app/common.py
- `WebTests` --uses--> `Redactor`  [INFERRED]
  tests/test_web.py → app/common.py
- `CoreTests` --uses--> `Database`  [INFERRED]
  tests/test_core.py → app/db.py

## Import Cycles
- None detected.

## Communities (23 total, 7 thin omitted)

### Community 0 - "common.py"
Cohesion: 0.25
Nodes (6): atomic_write(), main(), Create a lossless, line-addressed audit from the user's specification.  Every no, reconcile(), Run on Pi after copying reviewed sources; preserve and back up user config., AuditTests

### Community 1 - "Controller"
Cohesion: 0.16
Nodes (5): command(), Controller, RuntimeError, Probe the installed native protocol without requesting any model work., rpc()

### Community 2 - "windows_worker.py"
Cohesion: 0.19
Nodes (11): execute(), main(), protect_secret(), Outbound-only native Windows executor. This process never starts an AI agent., Windows DPAPI CurrentUser; no machine-wide or plaintext key file., relative_path(), validate_job(), Worker (+3 more)

### Community 3 - "main.py"
Cohesion: 0.27
Nodes (3): Bot, CloseView, button

### Community 4 - "Native"
Cohesion: 0.17
Nodes (8): GoalSource, Native, NativeError, Native Codex 0.155.1 RPC and the scheduler's local TUI admission gate., Reuse upstream parsing and event comparison; never retain objective text., tui_proxy(), main(), Trust only the seven reviewed hook definitions, through Codex's native API.

### Community 5 - "Database"
Cohesion: 0.12
Nodes (9): password_hash(), password_valid(), Redactor, slugify(), Database, Generate only a password hash from the user-owned specification., CoreTests, SchedulerTests (+1 more)

### Community 6 - "web.py"
Cohesion: 0.36
Nodes (10): action(), authorize(), index(), login(), make_app(), security(), session(), state() (+2 more)

### Community 7 - "dashboard.js"
Cohesion: 0.90
Nodes (4): act(), node(), projectCard(), refresh()

### Community 8 - "CodexPi installation progress"
Cohesion: 0.33
Nodes (5): CodexPi installation progress, Source references, Verified 2026-09-19, Verified 2026-09-20 (incremental, not final acceptance), Work still required

### Community 9 - "build_audit.py"
Cohesion: 0.40
Nodes (4): Installation and autostart, Protocol and jobs, Verification status, Windows worker

### Community 21 - "main.py"
Cohesion: 0.18
Nodes (11): canonical(), Per-connection random challenge + directional MAC + monotonic sequence., read_env(), SignedChannel, main(), dispatch_pending(), send(), submit_job() (+3 more)

## Knowledge Gaps
- **10 isolated node(s):** `install-base.sh script`, `PATH`, `Verified 2026-09-19`, `Verified 2026-09-20 (incremental, not final acceptance)`, `Work still required` (+5 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Controller` connect `Controller` to `main.py`, `Native`, `Database`?**
  _High betweenness centrality (0.131) - this node is a cross-community bridge._
- **Why does `Database` connect `Database` to `Controller`, `Native`?**
  _High betweenness centrality (0.095) - this node is a cross-community bridge._
- **Why does `SignedChannel` connect `main.py` to `windows_worker.py`, `Database`?**
  _High betweenness centrality (0.051) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `Controller` (e.g. with `Redactor` and `Database`) actually correct?**
  _`Controller` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `Database` (e.g. with `Controller` and `CoreTests`) actually correct?**
  _`Database` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `RuntimeError` (e.g. with `command()` and `.finish_creation()`) actually correct?**
  _`RuntimeError` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `Redactor` (e.g. with `Controller` and `SchedulerTests`) actually correct?**
  _`Redactor` has 3 INFERRED edges - model-reasoned connections that need verification._