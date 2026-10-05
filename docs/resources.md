# Pi infrastructure resource measurements

Incremental live measurement on 2026-09-21, **not the final acceptance sample**.
Raspberry Pi 4B, 4 GB, Ubuntu Server 25.10 ARM64. Both managed native goals were
complete. No tmux pane or active native goal was present before or after the
sample. Controller, Discord/dashboard/scheduler, native bridge and Unsnooze were
all running; unrelated Pi services were not stopped or included.

Reproduce on Pi: `.venv/bin/python Setup/measure-idle.py`. The read-only check
samples each service's cgroup and `/proc` process PSS/RSS, including descendants,
over 60 seconds. It refuses active native goals, remaining tmux panes, stopped
services, or a changed main PID. CPU accounting includes short-lived children,
such as the Unsnooze CLI poll, even when they have exited at the final snapshot.

## Warm idle sample (60.10 seconds)

| Component | Process PSS | CPU, percent of one core |
| --- | ---: | ---: |
| Controller + web + Discord + scheduler | 35.72 MiB | 5.42% |
| Native bridge + code-mode host | 232.60 MiB | 0.01% |
| Unsnooze daemon | 96.44 MiB | 0.02% |
| Total | **364.76 MiB** | **5.45%** |

The separately reported sum of systemd `MemoryCurrent` was 255.45 MiB. This is
different kernel accounting from process PSS, not a second interchangeable RAM
figure. The resident native bridge is included as infrastructure; no model turn
or project TUI was running. A preceding post-restart 60.10-second sample reported
364.75 MiB PSS / 255.70 MiB cgroup memory / 6.29% of one core.

The initial ten-second interval showed 22.76% of one core, mostly the repeated
Unsnooze status CLI. A separate timed invocation measured 1.54 wall seconds,
1.99 user CPU seconds and 0.24 system CPU seconds. Reusing the same supported
CLI every 60 seconds while idle, but every 10 seconds for a selected usage-limited
goal, removed most of this avoidable overhead. No custom limit detector or new
background process was introduced. The before/after windows differ, so these
samples are not a controlled whole-system benchmark.

Repeat this measurement after all remaining implementation, reboot/recovery and
design work before recording the final required resource result. Separate
Ponytail measurements are updated below; full startup overhead remains outstanding.

## Incremental 2026-09-29 sample

The same read-only 60.10-second check passed with five mapped projects, no active
native goal, no tmux pane and unchanged main PIDs. Process PSS totaled 370.11 MiB;
cgroup memory totaled 425.71 MiB. CPU was 10.28% of one core: controller 10.04%,
native bridge 0.22%, Unsnooze 0.02%. Four long-lived processes were observed;
no separate Ponytail process remained. This is not an A/B Ponytail measurement.

`optimization.md` records measured Ponytail hook latency and its scope. Total TUI
startup overhead is still pending. The controller CPU increase from the earlier
5.42% sample must be profiled before final resource acceptance; no causal
attribution is made from these differently timed samples. The Token Optimizer
integration is not yet installed, so this is not its final performance baseline.

## Incremental 2026-10-01 post-Optimizer sample

After the real Optimizer E2E goal completed, the existing 60.10-second idle check
measured 411.15 MiB process PSS, 512.06 MiB cgroup memory, and 5.90% of one CPU core.
Controller: 79,292 KiB PSS / 5.68%; native bridge plus Code Mode: 243,636 KiB /
0.20%; Unsnooze: 98,094 KiB / 0.02%. No active goal or tmux pane remained.
Main PIDs were still 680856/1158/1159; no process with a Token Optimizer command
line remained in the separate subsequent process inventory.

The six-project, post-model-run sample is not a controlled plugin A/B comparison.
It does not establish that the PSS increase from September 29 was caused by the
optimizer. CPU is back near the earlier baseline without a controller change;
the earlier 10.28% sample is not proof of a permanent CPU regression. Final
repeatable overhead/resource acceptance remains open.
# 2026-10-05 redundant idle writes (local reproduction)

Three unchanged goal polls across two paused projects previously wrote six rows
and changed project timestamps. The shared SQLite update/upsert now suppresses
identical values: the same reproduction writes zero rows and keeps timestamps.
No sampling interval, queue policy, notification transaction or FULL durability
setting was relaxed. Four focused persistence/lifecycle checks passed.
Pi deployment and an actual I/O before/after measurement remain pending while
unexpected system restarts are investigated; do not claim a measured Pi saving
or that this resolves the reboot cause. See `pi-restart-investigation.md`.
