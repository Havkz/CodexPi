# Design verification — 2026-09-20

Scope: the appended binding design specification in `C:\CODEXPI_GOAL.md`,
sections 1–36. This is incremental evidence, **not final acceptance**.

## Implemented and deployed to the Pi

- Shared dark CSS tokens for page/card/input backgrounds, typography, borders,
  spacing, radii, accents and native goal status colors. No frontend dependency,
  remote font, external stylesheet, social-preview image or public hosting.
- Matching single-password login, top infrastructure indicators, KPI cards,
  current project, horizontally scrollable queue, project cards, six infrastructure
  cards, usage/budget states and native project detail dialog.
- Authenticated detail API: recent Git commits, session/tmux/path, CI, Discord,
  project-specific Windows job stdout/stderr/exit/artifacts and lifecycle events.
  Global logs and native goal prompts are not exposed by this endpoint.
- Unknown and unavailable telemetry is labelled honestly; no fabricated percentages.
- Desktop drag/drop plus keyboard/touch arrow controls; native modal semantics,
  input labels, visible focus, textual status labels and preserved focus on polling.
- Secrets are redacted before JSON serialization, including quotes in secrets.
- Existing Discord embed implementation includes vertical multiline indentation,
  per-message persisted random accent, timestamp and native completion Close button.

## Verified evidence

`py -3.11 Setup/verify-design.py` uses the already-installed test-only Playwright
package and isolated headless Edge. The browser plugin had no available browser;
the normal user browser and profile were not used.

Live checks against `http://192.168.2.105:8787`:

- Actual native form login and logout succeeded.
- Login, dashboard and detail captured at 1920×1080, 1440×1000, 375×812, 430×932.
- No horizontal page/dialog overflow; mobile queue actions can be scrolled into view.
- Four KPI cards, six infrastructure cards, working detail open/close, no JS errors.
- Desktop and mobile screenshots inspected; private captures and machine-readable
  report live under ignored `state/design-checks/`.

Synthetic browser tests (all action requests intercepted, no real project mutation):

- All six status labels render; HTML-like project names remain inert text.
- Drag/drop and arrow reorder send complete project ID lists.
- Run now, Pause, Resume and Pause all send authenticated CSRF-protected actions.
- A normal five-second poll preserves keyboard focus.

`Setup/verify-dashboard.py` passes the live authentication, wrong-password,
HttpOnly/SameSite, CSRF, Origin, Host, secret-state and logout checks.
`python -m unittest discover -s tests -v` passes 13 tests, including extended
detail access control and redaction in commits, nested events and job logs.

The real browser test uncovered an existing login defect: `Referrer-Policy:
no-referrer` makes Chromium send `Origin: null` for the native form POST.
Using `same-origin` preserves login provenance and still suppresses external
referrers; Origin validation remains enforced. HTTP-only checks did not catch it.

## Still open — not waived

Incremental live Discord evidence on 2026-09-21: REST readback of actual message
`1551366894538461298` in the completed queue E2E channel confirmed the native
`CodexPi — Project Complete` embed, color `14048689`, six vertical indentation
characters, zero separate inline fields, footer, timestamp, and one `Close`
button with native danger style 4. This checks delivered structure, not visual
client rendering, repeated-message randomness, or clicking Close. The live
dashboard security check also passed again with Discord and Windows connected.

- Rename/Delete now have live and crash-simulation evidence in `lifecycle.md`;
  deployed-service/Windows-checkout integration and live reboot recovery remain open.
- Complete native account usage data, project controller/Codex log coverage,
  richer lifecycle event recording and refreshed details during actions.
- All Discord embed types verified in real channels, permissions and Close action.
- Full real scheduler/Unsnooze/offline/reconnect/CI/completion/reboot regression.
- Formal contrast coverage and full keyboard/touch acceptance across every state.
- Per-requirement final audit and final documentation/publication.

No chart was added: no time-series source currently justifies one. No mandatory
requirement is removed by that conditional design choice.
