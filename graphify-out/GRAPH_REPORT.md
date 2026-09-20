# Graph Report - CodexPi  (2026-09-20)

## Corpus Check
- 34 files · ~35,295 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 183 nodes · 384 edges · 22 communities (14 shown, 8 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 40 edges (avg confidence: 0.66)
- Token cost: 0 input · 0 output

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

## God Nodes (most connected - your core abstractions)
1. `Controller` - 31 edges
2. `Database` - 24 edges
3. `Redactor` - 14 edges
4. `SignedChannel` - 13 edges
5. `command()` - 13 edges
6. `Native` - 13 edges
7. `atomic_write()` - 11 edges
8. `Worker` - 11 edges
9. `make_app()` - 10 edges
10. `Bot` - 9 edges

## Surprising Connections (you probably didn't know these)
- `SchedulerTests` --uses--> `Controller`  [INFERRED]
  tests/test_scheduler.py → app/controller.py
- `CoreTests` --uses--> `Database`  [INFERRED]
  tests/test_core.py → app/db.py
- `CoreTests` --uses--> `SignedChannel`  [INFERRED]
  tests/test_core.py → app/common.py
- `SchedulerTests` --uses--> `Redactor`  [INFERRED]
  tests/test_scheduler.py → app/common.py
- `WebTests` --uses--> `Redactor`  [INFERRED]
  tests/test_web.py → app/common.py

## Import Cycles
- None detected.

## Communities (22 total, 8 thin omitted)

### Community 0 - "common.py"
Cohesion: 0.17
Nodes (10): atomic_write(), canonical(), password_hash(), password_valid(), Per-connection random challenge + directional MAC + monotonic sequence., SignedChannel, slugify(), Run on Pi after copying reviewed sources; preserve and back up user config. (+2 more)

### Community 2 - "windows_worker.py"
Cohesion: 0.19
Nodes (11): execute(), main(), protect_secret(), Outbound-only native Windows executor. This process never starts an AI agent., Windows DPAPI CurrentUser; no machine-wide or plaintext key file., relative_path(), validate_job(), Worker (+3 more)

### Community 3 - "main.py"
Cohesion: 0.15
Nodes (6): Bot, CloseView, button, RuntimeError, Probe the installed native protocol without requesting any model work., rpc()

### Community 4 - "Native"
Cohesion: 0.18
Nodes (8): GoalSource, Native, NativeError, Native Codex 0.155.1 RPC and the scheduler's local TUI admission gate., Reuse upstream parsing and event comparison; never retain objective text., tui_proxy(), main(), Trust only the seven reviewed hook definitions, through Codex's native API.

### Community 5 - "Database"
Cohesion: 0.14
Nodes (4): Redactor, Database, SchedulerTests, WebTests

### Community 6 - "web.py"
Cohesion: 0.36
Nodes (10): action(), authorize(), index(), login(), make_app(), security(), session(), state() (+2 more)

### Community 7 - "dashboard.js"
Cohesion: 0.90
Nodes (4): act(), node(), projectCard(), refresh()

### Community 8 - "CodexPi installation progress"
Cohesion: 0.33
Nodes (5): CodexPi installation progress, Source references, Verified 2026-09-19, Verified 2026-09-20 (incremental, not final acceptance), Work still required

### Community 21 - "main.py"
Cohesion: 0.47
Nodes (7): read_env(), main(), dispatch_pending(), send(), submit_job(), unblock_windows(), worker_socket()

## Knowledge Gaps
- **7 isolated node(s):** `install-base.sh script`, `PATH`, `Verified 2026-09-19`, `Verified 2026-09-20 (incremental, not final acceptance)`, `Work still required` (+2 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Controller` connect `Controller` to `main.py`, `Native`, `Database`?**
  _High betweenness centrality (0.145) - this node is a cross-community bridge._
- **Why does `Database` connect `Database` to `common.py`, `Controller`, `main.py`, `Native`?**
  _High betweenness centrality (0.105) - this node is a cross-community bridge._
- **Why does `SignedChannel` connect `common.py` to `windows_worker.py`, `main.py`?**
  _High betweenness centrality (0.056) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `Controller` (e.g. with `Redactor` and `Database`) actually correct?**
  _`Controller` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `Database` (e.g. with `Controller` and `CoreTests`) actually correct?**
  _`Database` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `RuntimeError` (e.g. with `command()` and `.finish_creation()`) actually correct?**
  _`RuntimeError` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `Redactor` (e.g. with `Controller` and `SchedulerTests`) actually correct?**
  _`Redactor` has 3 INFERRED edges - model-reasoned connections that need verification._