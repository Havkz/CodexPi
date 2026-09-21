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
Ponytail hook latency/startup overhead measurements are still outstanding.
