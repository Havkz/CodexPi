# Graph Report - CodexPi  (2026-09-21)

## Corpus Check
- 47 files · ~57,633 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 267 nodes · 602 edges · 27 communities (21 shown, 6 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 61 edges (avg confidence: 0.66)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `839f111a`
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
- test-live-lifecycle.py
- Unsnooze integration

## God Nodes (most connected - your core abstractions)
1. `Controller` - 36 edges
2. `Database` - 33 edges
3. `command()` - 22 edges
4. `Redactor` - 21 edges
5. `atomic_write()` - 17 edges
6. `Native` - 14 edges
7. `SignedChannel` - 13 edges
8. `Bot` - 13 edges
9. `finish()` - 13 edges
10. `begin()` - 12 edges

## Surprising Connections (you probably didn't know these)
- `DiscordTests` --uses--> `Redactor`  [INFERRED]
  tests/test_discord.py → app/common.py
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

## Communities (27 total, 6 thin omitted)

### Community 0 - "common.py"
Cohesion: 0.13
Nodes (17): canonical(), password_hash(), password_valid(), Per-connection random challenge + directional MAC + monotonic sequence., read_env(), SignedChannel, slugify(), main() (+9 more)

### Community 2 - "windows_worker.py"
Cohesion: 0.19
Nodes (11): execute(), main(), protect_secret(), Outbound-only native Windows executor. This process never starts an AI agent., Windows DPAPI CurrentUser; no machine-wide or plaintext key file., relative_path(), validate_job(), Worker (+3 more)

### Community 3 - "main.py"
Cohesion: 0.23
Nodes (5): Bot, CloseView, One compact text hierarchy: vertical indentation, not a grid of fields., status_embed(), DiscordTests

### Community 4 - "Native"
Cohesion: 0.09
Nodes (26): atomic_write(), begin(), channel(), finish(), move_owned(), owned_path(), Durable, idempotent project lifecycle steps. SQLite is the operation journal., Same-filesystem atomic move; never overwrite a preexisting unrelated target. (+18 more)

### Community 5 - "Database"
Cohesion: 0.33
Nodes (5): Delete, Interrupted operation recovery, Project lifecycle, Rename, Verified on 2026-09-20

### Community 6 - "web.py"
Cohesion: 0.33
Nodes (12): action(), authorize(), index(), login(), make_app(), project_detail(), safe_json(), security() (+4 more)

### Community 7 - "dashboard.js"
Cohesion: 0.42
Nodes (16): act(), actions(), badge(), block(), button(), date(), link(), metadata() (+8 more)

### Community 8 - "CodexPi installation progress"
Cohesion: 0.33
Nodes (5): CodexPi installation progress, Source references, Verified 2026-09-19, Verified 2026-09-20 (incremental, not final acceptance), Work still required

### Community 9 - "build_audit.py"
Cohesion: 0.40
Nodes (4): Installation and autostart, Protocol and jobs, Verification status, Windows worker

### Community 11 - "discord-token.py"
Cohesion: 0.43
Nodes (4): main(), Create a lossless, line-addressed audit from the user's specification.  Every no, reconcile(), AuditTests

### Community 21 - "main.py"
Cohesion: 0.11
Nodes (7): Redactor, Database, BaseException, Crash, LifecycleTests, SchedulerTests, WebTests

### Community 22 - "test-live-queue.py"
Cohesion: 0.33
Nodes (4): Exercise the two explicitly named E2E projects through the authenticated dashboa, state(), main(), Resume only the existing queue E2E goal; never create or replace an objective.

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

## Knowledge Gaps
- **19 isolated node(s):** `install-base.sh script`, `PATH`, `Implemented and deployed to the Pi`, `Verified evidence`, `Still open — not waived` (+14 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Controller` connect `Controller` to `common.py`, `Native`, `main.py`?**
  _High betweenness centrality (0.086) - this node is a cross-community bridge._
- **Why does `Database` connect `main.py` to `common.py`, `Controller`, `main.py`, `Native`?**
  _High betweenness centrality (0.081) - this node is a cross-community bridge._
- **Why does `command()` connect `Controller` to `common.py`, `Native`, `main.py`, `web.py`?**
  _High betweenness centrality (0.055) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `Controller` (e.g. with `Redactor` and `Database`) actually correct?**
  _`Controller` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `Database` (e.g. with `Controller` and `CoreTests`) actually correct?**
  _`Database` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `command()` (e.g. with `RuntimeError` and `.make_controller()`) actually correct?**
  _`command()` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `Redactor` (e.g. with `Controller` and `DiscordTests`) actually correct?**
  _`Redactor` has 6 INFERRED edges - model-reasoned connections that need verification._