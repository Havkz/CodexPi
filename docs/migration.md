# Selected Windows session migration

## Scope and source

Only session `01a072f0-df80-7152-aff3-a5e66960c071` was selected.
Its real project is `C:\Users\User\CascadeProjects\donut-order-trader`,
not the user-home cwd in its original session metadata. Windows originals remain
unchanged. Original private repository: `Havkz/donut-order-trader`, HEAD
`1d41449d722bf885a3fe40ae85c36cb2e16b034d`. Four modified tracked files and one
untracked Java source are retained, without committing or normalizing them.

The private full archive is
`backups/migrations/01a072f0-df80-7152-aff3-a5e66960c071-20261004-full.tar.gz`
on the Pi and `state/migrations/` on Windows. SHA-256:
`a1ddf8b955da7ff085525e7e89218185316700acdd2984707b96d13612ec39e0`.
It contains 1,375 members plus its manifest, including the complete original
53,076,997-byte rollout, Git objects/index, ignored research data, explicit
pasted requirements, six PCAP captures and the referenced Minecraft client JAR.
The full archive was checked independently on the Pi, not merely copied.

## Reusable mechanism

1. Pause the selected source goal. Run `Setup/export-migration.py --project PATH
   --session UUID --output PRIVATE_ARCHIVE`, adding explicit `--reference FILE`
   arguments for external inputs. No other project or global credentials are
   collected. Source changes, active goals, external Git object stores, reparse
   points and unsnapshotted project SQLite databases fail closed.
2. Copy the archive into the Pi's private `backups/migrations/` directory with
   mode 600. Keep source and archive copies; never commit native history to Git.
3. POST `{"name":"PROJECT","archive":"ABSOLUTE_ARCHIVE","sha256":"SHA256"}`
   to `/projects/import` through `state/local.sock`. This is a mode-600 local
   controller endpoint, not a public admission-gate bypass. The controller lock,
   SQLite lifecycle journal and durable manual pause cover the whole import.
   A repeated request identifies the original import; it does not create another
   project/session. Inspect its actual journal after a timeout before retrying.
4. Verify the imported project and open it through the ordinary mapped TUI.
   Importing never calls `turn/start`, sets a goal active or sends `/goal resume`.
   Only a later explicit Resume may authorize execution through the usual queue.

The existing private repository is linked by immutable GitHub repository ID;
its previous description is journaled before applying the normal CodexPi
ownership marker. Git history and dirty working state are not pushed/rewritten
by import. The normal Discord channel ownership and lifecycle recovery apply.

## Fidelity and compatibility

- **Original, not reconstructed:** raw native rollout; selected-thread history
  snapshot (56 turns, 2,762 items); original goal ID, prompt, budgets, usage counters
  and timestamps; project/Git bytes; explicit external inputs and instructions.
- **Explicit adaptations:** Linux cwd/workspace sandbox; private path mapping and
  CodexPi operating instructions appended as a new developer context item;
  original goal deliberately paused on the Pi. Its historical `usage_limited`
  status remains in the manifest and is not presented as a new quota observation.
- Git-for-Windows inherited `core.autocrlf` globally. The importer accepts a local
  setting only when it reproduces the exact source Git status, without modifying
  worktree bytes. Global Pi configuration is untouched.
- Windows history has `started_at_ms` and `completed_at_ms` columns absent from
  the installed Pi index schema. Both remain verbatim in the private snapshot;
  only those two known display-timing columns are omitted from the live index.
  All `item_json` entries and raw records are retained. No upstream schema is
  altered and no session-ID fallback has been needed.
- **Not transferable:** running processes/PTY state, provider-side caches,
  unexported OS credential vaults and Windows virtual environments/build caches.
  Cache omissions are enumerated. Native history can contain sensitive material:
  archives/snapshots stay private and are excluded from Git.

## Current evidence and unfinished verification

The actual project was registered as `2e58d341-7597-4876-a6c2-fb4264f144b9`,
at `/home/raspberry/CodexPi/projects/donut-order-trader`, with the original native
session ID and Discord channel `1556677535914397726`. Native goal lookup verified
the original objective, paused state, and all other original goal-row fields.
The original rollout is an identical prefix of the live rollout; migration adds
context without replacing history. Controller state reached ready/paused.

However, the final independent file audit found four damaged/incomplete copies:
the private server JAR, two PCAP references and the client JAR. The original
archive remains intact. The Pi restarted during import and again during the
attempted repair (not initiated by Codex). Repair completion is **unproven**.
The importer now fsyncs extracted files/directories and rechecks every non-Git
file before releasing the lifecycle. Damaged copies are retained separately
when repaired; originals on Windows are untouched.

Do not call this migration fully verified yet. Finish all-file checksum repair,
open the real mapped TUI, verify its paused goal/session identity and dashboard
mapping, and record Discord ownership. No trading/model turn was started.

The single combined regression check in `tests/test_migration.py` covers export
fidelity, unsafe/corrupt archives, target collisions, native-row preservation,
the two-column compatibility case, manual hold and idempotent recovery after a
Discord interruption. It does not replace the outstanding real TUI/file checks.
