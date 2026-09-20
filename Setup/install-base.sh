#!/bin/bash
set -euo pipefail
umask 077
export PATH=/home/raspberry/.local/bin:/home/raspberry/.local/node_modules/.bin:/usr/local/bin:/usr/bin:/bin
base=/home/raspberry/CodexPi
mkdir -p "$base"/{app,bin,config,state,logs,backups,templates,windows-worker,projects,docs,Setup/{downloads,upstream,schema}}
snapshot="$base/backups/config-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$snapshot"
for file in /home/raspberry/.codex/config.toml /home/raspberry/.codex/hooks.json /home/raspberry/.unsnooze/config.json /home/raspberry/.config/ponytail/config.json; do
    if [ -f "$file" ]; then cp --parents -a "$file" "$snapshot"; fi
done
if ! command -v gh >/dev/null; then
    cd "$base/Setup/downloads"
    curl -fsSLO https://github.com/cli/cli/releases/download/v2.101.0/gh_2.101.0_linux_arm64.tar.gz
    printf '%s  %s\n' b57e8063f18862647c9d22727c32e9da1b963f8bf9db648fe123a6975695640f gh_2.101.0_linux_arm64.tar.gz | sha256sum -c -
    tar -xzf gh_2.101.0_linux_arm64.tar.gz
    install -m 755 gh_2.101.0_linux_arm64/bin/gh /home/raspberry/.local/bin/gh
fi
if [ ! -e /home/raspberry/.local/bin/unsnooze ]; then
    ln -s /home/raspberry/.local/node_modules/.bin/unsnooze /home/raspberry/.local/bin/unsnooze
fi
codex app-server generate-json-schema --experimental --out "$base/Setup/schema"
if [ ! -d "$base/Setup/upstream/goal-hooks/.git" ]; then
    git clone --depth 1 https://github.com/mhmdibrahimm/codex-goal-hooks.git "$base/Setup/upstream/goal-hooks"
fi
unsnooze config set autoResume false
unsnooze config set multiplexer tmux
unsnooze config set resumeMessages.codex '/goal resume'
unsnooze config set agents.claude false
unsnooze config set agents.codex true
unsnooze config set notifications false
unsnooze config set remoteQueue false
codex plugin marketplace add DietrichGebert/ponytail --ref v4.10.0
codex plugin add ponytail@ponytail
gh --version
codex plugin list
unsnooze doctor
