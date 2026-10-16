# CodexPi

> Persistent AI development workflows. One queue. Two machines.

CodexPi coordinates long-running Codex projects on a Raspberry Pi, with a Windows
worker for native builds and tests. A browser dashboard and Discord notifications
keep project status visible without keeping a terminal open.

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-0284C7?style=flat)
![Platforms: Linux and Windows](https://img.shields.io/badge/Platforms-Linux%20%2F%20Windows-0284C7?style=flat)
![Status: active development](https://img.shields.io/badge/Status-Active%20development-0284C7?style=flat)

[Architecture](docs/architecture.md) · [Operations & recovery](docs/recovery.md) · [Windows worker](docs/windows-worker.md)

---

## What it does

- **Persistent project queue** — prioritize projects, pause work across restarts,
  and resume the original Codex session without replacing its goal or history.
- **Browser dashboard** — manage the queue, inspect infrastructure and job status,
  switch saved accounts, and view account-specific usage history.
- **Background automation** — configurable queue continuation, usage-reset
  recovery and account switching, while respecting manual pauses and user blockers.
- **Discord updates** — project channels, status notifications and questions,
  backed by a persistent delivery outbox.
- **Windows execution** — run jobs against an exact Git commit, collect results
  and artifacts, and reconcile interrupted or disconnected workers.
- **Local CI coordination** — coordinate self-hosted GitHub Actions runners,
  including Linux tests through WSL, with a shared Windows execution slot.

CodexPi orchestrates the official Codex runtime; it is not a model, a replacement
for Codex, or a second AI agent on the Windows PC.

## How it works

The Raspberry Pi hosts one native Codex app-server. A single asynchronous Python
controller connects the dashboard, scheduler, Discord bot and Windows worker.
Native Codex owns session history and goals; SQLite stores infrastructure state,
queue mappings, job results and recovery journals.

**Stack:** Python · asyncio · aiohttp · SQLite · discord.py · JavaScript/CSS/SVG ·
systemd · tmux · PowerShell · GitHub Actions · Playwright (UI checks).

The Windows worker connects outbound to the Pi. Authenticated messages and
durable job IDs support reconnects without blindly repeating side effects.
See the [architecture](docs/architecture.md) for process boundaries and recovery.

## Getting started

### Development

Clone the repository using an account with access. In a Python 3.11+ virtual
environment, install the runtime dependencies and run the regression suite:

```sh
git clone https://github.com/Havkz/CodexPi.git
cd CodexPi
python -m pip install -r requirements.txt
python -m unittest discover -s tests
```

Optional Chromium layout checks use a separate development dependency set:

```sh
python -m pip install -r requirements-ui.txt
python -m playwright install chromium
python Setup/verify-mobile-ui.py
```

### Deployment

A running installation additionally needs a Linux host with systemd, tmux, SSH,
Git, GitHub CLI, an authenticated Codex CLI with app-server support, the upstream
goal hooks and Unsnooze, plus Discord bot credentials. Windows jobs require a
configured Windows 11 worker; local Linux CI also requires WSL.

The deployment scripts target `/home/raspberry/CodexPi` and `C:\CodexPi` and
contain installation-specific assumptions. They are **not a portable one-click
installer**. Review the [architecture](docs/architecture.md),
[recovery guide](docs/recovery.md) and [worker setup](docs/windows-worker.md)
before configuring another machine. Keep secrets and runtime state out of Git.

## Usage

With the controller and terminal entrypoint configured:

```text
codexpi
/rename My Project
/goal Describe the task
```

Reusing a project name opens its saved native session. `codexpi --all` opens the
session browser. Detach with **Ctrl+B, then D**; work continues in tmux.

Use the configured private-LAN dashboard for queue management. **Resume** does
not preempt another running project; **Run now** changes priority. A successful
resume requires native confirmation, not just an accepted browser request.
New projects are created through the terminal entrypoint.

## Status & boundaries

**Active development, with deployment-specific acceptance checks still open.**
Regression tests and targeted UI verifiers live in `tests/` and `Setup/`;
[verification records](docs/requirement-audit.json) distinguish implemented work
from hardware-dependent acceptance.

- Wake-on-LAN and boot-ownership checks are implemented, but physical wake from
  full shutdown and the complete unattended shutdown cycle remain unverified.
- The current LAN HTTP/WebSocket deployment is not encrypted. Worker message
  authentication is not transport encryption. Do not expose the dashboard port
  directly to the internet.
- GitHub Actions is manually dispatched. Runner selection is configurable;
  confirm the self-hosted configuration before dispatching to avoid hosted usage.

For operational detail, see [manual pauses](docs/manual-pause.md),
[session lifecycle](docs/lifecycle.md), [usage history](docs/usage-history.md) and
[reset recovery](docs/unsnooze.md).
