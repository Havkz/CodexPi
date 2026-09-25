# Graph Report - CodexPi  (2026-09-25)

## Corpus Check
- 67 files · ~75,698 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 394 nodes · 840 edges · 41 communities (27 shown, 14 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 76 edges (avg confidence: 0.67)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `a20ff604`
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
- Durable manual pause and real quota evidence, 2026-09-24
- main
- verify-deployment.py
- Explicit Pi deployment
- Bot
- usage.js
- build_audit.py
- main
- verify-usage-ui.py
- build-favicon.py

## God Nodes (most connected - your core abstractions)
1. `Database` - 46 edges
2. `Controller` - 43 edges
3. `command()` - 28 edges
4. `SchedulerTests` - 27 edges
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
- `LifecycleTests` --uses--> `Redactor`  [INFERRED]
  tests/test_lifecycle.py → app/common.py
- `SchedulerTests` --uses--> `Redactor`  [INFERRED]
  tests/test_scheduler.py → app/common.py
- `WebTests` --uses--> `Redactor`  [INFERRED]
  tests/test_web.py → app/common.py

## Import Cycles
- None detected.

## Communities (41 total, 14 thin omitted)

### Community 0 - "common.py"
Cohesion: 0.29
Nodes (6): Changes, Completion gate follow-up, Lifecycle repair evidence, 2026-09-23, Reproduction and exact causes, Verification boundaries and remaining work, Verified live

### Community 2 - "windows_worker.py"
Cohesion: 0.21
Nodes (10): execute(), main(), protect_secret(), Outbound-only native Windows executor. This process never starts an AI agent., Windows DPAPI CurrentUser; no machine-wide or plaintext key file., relative_path(), validate_job(), Worker (+2 more)

### Community 3 - "deployment.py"
Cohesion: 0.16
Nodes (28): slugify(), complete(), finish(), key(), quote(), Explicit 24/7 Pi delivery, completed through the existing lifecycle journal., Called under the controller lock, after final Git/CI checks., relocate_session() (+20 more)

### Community 4 - "Native"
Cohesion: 0.29
Nodes (4): GoalSource, Reuse upstream parsing and event comparison; never retain objective text., Read-only Pi resource sample; refuse to label an active-goal run as idle., sample()

### Community 5 - "Database"
Cohesion: 0.33
Nodes (5): Delete, Interrupted operation recovery, Project lifecycle, Rename, Verified on 2026-09-20

### Community 6 - "web.py"
Cohesion: 0.15
Nodes (20): action(), authorize(), favicon(), index(), login(), make_app(), project_detail(), safe_json() (+12 more)

### Community 7 - "dashboard.js"
Cohesion: 0.42
Nodes (16): act(), actions(), badge(), block(), button(), date(), link(), metadata() (+8 more)

### Community 8 - "CodexPi installation progress"
Cohesion: 0.25
Nodes (7): 2026-09-25 usage-history implementation and live verification, CodexPi installation progress, Source references, Verified 2026-09-19, Verified 2026-09-20 (incremental, not final acceptance), Verified 2026-09-21 (incremental, not final acceptance), Work still required

### Community 9 - "build_audit.py"
Cohesion: 0.40
Nodes (4): Installation and autostart, Protocol and jobs, Verification status, Windows worker

### Community 11 - "Bot"
Cohesion: 0.10
Nodes (20): atomic_write(), read_env(), Redactor, Bot, CloseView, One compact text hierarchy: vertical indentation, not a grid of fields., status_embed(), main() (+12 more)

### Community 21 - "main.py"
Cohesion: 0.06
Nodes (13): Native, NativeError, tui_proxy(), RuntimeError, Probe the installed native protocol without requesting any model work., rpc(), Exercise the two explicitly named E2E projects through the authenticated dashboa, state() (+5 more)

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
Cohesion: 0.11
Nodes (8): Database, number(), Read-only account telemetry; never decides whether a goal may execute., windows(), DeploymentTests, LifecycleTests, account(), UsageTests

### Community 31 - "Durable manual pause and real quota evidence, 2026-09-24"
Cohesion: 0.50
Nodes (3): Durable manual pause and real quota evidence, 2026-09-24, Pause authority, Real usage-limit history

### Community 33 - "verify-deployment.py"
Cohesion: 0.67
Nodes (3): main(), observe(), Start/observe one real deployment goal; never replace an existing objective.  De

### Community 35 - "Bot"
Cohesion: 0.33
Nodes (5): Data and boundaries, Existing-logo favicon, Presentation, Usage / Limits history, Verification as of 2026-09-25

### Community 36 - "usage.js"
Cohesion: 0.57
Nodes (6): refreshUsage(), renderUsage(), usageDate(), usageElement(), usagePercent(), usageSvg()

### Community 37 - "build_audit.py"
Cohesion: 0.43
Nodes (4): main(), Create a lossless, line-addressed audit from the user's specification.  Every no, reconcile(), AuditTests

### Community 38 - "main"
Cohesion: 0.19
Nodes (7): canonical(), password_hash(), password_valid(), Per-connection random challenge + directional MAC + monotonic sequence., SignedChannel, Generate only a password hash from the user-owned specification., CoreTests

## Knowledge Gaps
- **34 isolated node(s):** `install-base.sh script`, `PATH`, `Evidence, 2026-09-24`, `Implemented and deployed to the Pi`, `Verified evidence` (+29 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **14 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Database` connect `Bot` to `Controller`, `Native`, `main`, `web.py`, `Bot`, `main.py`?**
  _High betweenness centrality (0.099) - this node is a cross-community bridge._
- **Why does `Controller` connect `Controller` to `Bot`, `Bot`, `Native`, `main.py`?**
  _High betweenness centrality (0.073) - this node is a cross-community bridge._
- **Why does `command()` connect `Controller` to `deployment.py`, `web.py`, `Bot`, `main.py`, `Bot`?**
  _High betweenness centrality (0.056) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `Database` (e.g. with `Controller` and `CoreTests`) actually correct?**
  _`Database` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `Controller` (e.g. with `Redactor` and `Database`) actually correct?**
  _`Controller` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `command()` (e.g. with `RuntimeError` and `.fixture()`) actually correct?**
  _`command()` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `SchedulerTests` (e.g. with `Redactor` and `Controller`) actually correct?**
  _`SchedulerTests` has 3 INFERRED edges - model-reasoned connections that need verification._