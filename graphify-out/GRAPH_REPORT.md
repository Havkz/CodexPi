# Graph Report - CodexPi  (2026-09-24)

## Corpus Check
- 58 files · ~69,543 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 345 nodes · 758 edges · 34 communities (24 shown, 10 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 71 edges (avg confidence: 0.68)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `81f394b2`
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
- verify-deployment.py
- Explicit Pi deployment

## God Nodes (most connected - your core abstractions)
1. `Controller` - 40 edges
2. `Database` - 40 edges
3. `command()` - 28 edges
4. `SchedulerTests` - 23 edges
5. `Redactor` - 22 edges
6. `atomic_write()` - 19 edges
7. `finish()` - 19 edges
8. `Bot` - 14 edges
9. `Native` - 14 edges
10. `SignedChannel` - 13 edges

## Surprising Connections (you probably didn't know these)
- `main()` --indirect_call--> `save()`  [INFERRED]
  Setup/discord-token.py → app/lifecycle.py
- `main()` --indirect_call--> `action()`  [INFERRED]
  Setup/verify-lifecycle-fixes.py → app/web.py
- `DiscordTests` --uses--> `Redactor`  [INFERRED]
  tests/test_discord.py → app/common.py
- `Crash` --uses--> `Controller`  [INFERRED]
  tests/test_lifecycle.py → app/controller.py
- `LifecycleTests` --uses--> `Controller`  [INFERRED]
  tests/test_lifecycle.py → app/controller.py

## Import Cycles
- None detected.

## Communities (34 total, 10 thin omitted)

### Community 0 - "common.py"
Cohesion: 0.29
Nodes (6): Changes, Completion gate follow-up, Lifecycle repair evidence, 2026-09-23, Reproduction and exact causes, Verification boundaries and remaining work, Verified live

### Community 1 - "Controller"
Cohesion: 0.17
Nodes (5): command(), Controller, RuntimeError, Probe the installed native protocol without requesting any model work., rpc()

### Community 2 - "windows_worker.py"
Cohesion: 0.21
Nodes (10): execute(), main(), protect_secret(), Outbound-only native Windows executor. This process never starts an AI agent., Windows DPAPI CurrentUser; no machine-wide or plaintext key file., relative_path(), validate_job(), Worker (+2 more)

### Community 3 - "deployment.py"
Cohesion: 0.13
Nodes (29): slugify(), complete(), finish(), key(), quote(), Explicit 24/7 Pi delivery, completed through the existing lifecycle journal., Called under the controller lock, after final Git/CI checks., relocate_session() (+21 more)

### Community 4 - "Native"
Cohesion: 0.12
Nodes (10): GoalSource, Native, NativeError, Native Codex 0.155.1 RPC and the scheduler's local TUI admission gate., Reuse upstream parsing and event comparison; never retain objective text., tui_proxy(), Read-only Pi resource sample; refuse to label an active-goal run as idle., sample() (+2 more)

### Community 5 - "Database"
Cohesion: 0.33
Nodes (5): Delete, Interrupted operation recovery, Project lifecycle, Rename, Verified on 2026-09-20

### Community 6 - "web.py"
Cohesion: 0.24
Nodes (14): action(), authorize(), index(), login(), make_app(), project_detail(), safe_json(), security() (+6 more)

### Community 7 - "dashboard.js"
Cohesion: 0.42
Nodes (16): act(), actions(), badge(), block(), button(), date(), link(), metadata() (+8 more)

### Community 8 - "CodexPi installation progress"
Cohesion: 0.29
Nodes (6): CodexPi installation progress, Source references, Verified 2026-09-19, Verified 2026-09-20 (incremental, not final acceptance), Verified 2026-09-21 (incremental, not final acceptance), Work still required

### Community 9 - "build_audit.py"
Cohesion: 0.40
Nodes (4): Installation and autostart, Protocol and jobs, Verification status, Windows worker

### Community 11 - "Bot"
Cohesion: 0.10
Nodes (22): atomic_write(), canonical(), password_hash(), password_valid(), Per-connection random challenge + directional MAC + monotonic sequence., read_env(), SignedChannel, main() (+14 more)

### Community 21 - "main.py"
Cohesion: 0.06
Nodes (8): Redactor, Database, BaseException, DeploymentTests, Crash, LifecycleTests, SchedulerTests, WebTests

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
Cohesion: 0.21
Nodes (4): Bot, One compact text hierarchy: vertical indentation, not a grid of fields., status_embed(), DiscordTests

### Community 32 - "main"
Cohesion: 0.33
Nodes (4): Exercise the two explicitly named E2E projects through the authenticated dashboa, state(), main(), Resume only the existing queue E2E goal; never create or replace an objective.

### Community 33 - "verify-deployment.py"
Cohesion: 0.67
Nodes (3): main(), observe(), Start/observe one real deployment goal; never replace an existing objective.  De

## Knowledge Gaps
- **27 isolated node(s):** `install-base.sh script`, `PATH`, `Evidence, 2026-09-24`, `Implemented and deployed to the Pi`, `Verified evidence` (+22 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Database` connect `main.py` to `Controller`, `deployment.py`, `Native`, `Bot`, `Bot`?**
  _High betweenness centrality (0.092) - this node is a cross-community bridge._
- **Why does `Controller` connect `Controller` to `Bot`, `deployment.py`, `Native`, `main.py`?**
  _High betweenness centrality (0.081) - this node is a cross-community bridge._
- **Why does `command()` connect `Controller` to `Bot`, `deployment.py`, `main.py`, `web.py`?**
  _High betweenness centrality (0.064) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `Controller` (e.g. with `Redactor` and `Database`) actually correct?**
  _`Controller` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `Database` (e.g. with `Controller` and `CoreTests`) actually correct?**
  _`Database` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `command()` (e.g. with `RuntimeError` and `.fixture()`) actually correct?**
  _`command()` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 22 inferred relationships involving `RuntimeError` (e.g. with `command()` and `.finish_creation()`) actually correct?**
  _`RuntimeError` has 22 INFERRED edges - model-reasoned connections that need verification._