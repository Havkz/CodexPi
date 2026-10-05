# Unexpected Pi restarts — 2026-10-05

The user confirmed they did not initiate the observed restarts. Codex restarted
only the `codexpi` user service while deploying the importer, never the Pi.
Migration repair and external deletion are held pending stability assessment.

## Observed, not inferred

- Previous boot: `c005374c978240f6b1ec36bdc63275b8`; current boot:
  `5f1207a90d44412ebb19639703f940a7`. Current boot reached NTP-synchronized
  2026-10-05 16:46–16:50 Europe/Berlin after initially reporting June 5.
  Wall-clock boot timestamps before NTP are not trustworthy; use boot ID/uptime.
- Current journal reports both system/user journals were corrupt or uncleanly
  shut down. Boot filesystem check reports an uncleared dirty bit. No orderly
  PID-1 shutdown/reboot sequence was found in the available previous-boot log.
- Four transferred files failed the independent post-reboot SHA-256 check.
  The 56,327,581-byte server JAR was 37,748,736 bytes, two captures were truncated
  to 33,554,432 bytes, and the client JAR had a different hash despite equal
  length. Their original private archive was verified intact on the Pi and is
  also retained on Windows. A repair attempt was interrupted by another reboot;
  do not claim repair complete.
- At approximately 4–6 minutes uptime: CPU 46–47 C, available RAM 2,716 MiB of
  3,780 MiB, no swap, memory PSI averages zero. CodexPi/native/Unsnooze memory
  peaks in this boot were about 150/284/159 MB. These current measurements do
  **not** prove what memory or temperature was immediately before the crash.
- Current `rpi_volt/in0_lcrit_alarm` is 0. No retained undervoltage, OOM, panic
  or SD I/O-error message established a cause. `vcgencmd` cannot open `/dev/vcio`
  on this Ubuntu installation; no device node was fabricated to work around it.
- Root is ext4 on the 16 GB `SS16G` SD card; reported manufacture date 06/2016,
  about 4.1 GB free after the interrupted repair. Card age is a risk indicator,
  not proof of failure. No destructive storage benchmark or mounted fsck run.
- Passive follow-up observed the controller waiting in `jbd2_log_wait_commit`,
  alongside the filesystem journal thread in D state. The controller subsequently
  returned to `ep_poll`; this sample did not establish a 30-second stall.
  Host I/O pressure was elevated (some avg10 up to 25.96%, full up to 15.83%),
  while memory pressure remained zero. Other headless-browser processes were
  active. This supports storage contention, not a proven defective SD card or
  a proven watchdog reset.
- Hardware watchdog is active with a 30-second timeout, configured by existing
  `/etc/systemd/system.conf.d/99-watchdog.conf`. `bootstatus=0` does not establish
  the reset cause: the BCM2835 driver does not advertise reset-cause reporting.
  No panic dump was found in pstore.

## Existing non-CodexPi services

`internet-watchdog.service` runs
`/home/raspberry/Vertretungsplan/Internet-Watchdog.py`. Its `_reboot()` at lines
94–102 calls `os.sync()`, then `os.reboot(os.RB_AUTOBOOT)`, with `reboot -f` as
fallback. Six failed connectivity checks can invoke it. This is an actual
forced-reset path that bypasses normal service shutdown, but the retained log
does **not** show it firing before these crashes. Do not call it the proven cause.
The service and hardware watchdog were not modified or disabled.

`self-bot.service` is separately in an exit-code restart loop every ~12 seconds:
6,160 restarts in the previous boot, 27 by about six minutes in the current boot.
It uses about 47 MB at peak and has `FailureAction=none` and
`StartLimitAction=none`. This is a real unrelated service fault and unnecessary
log/CPU activity, not demonstrated to be the source of the machine reset.
No changes were made to this pre-existing service.

## Conclusion and safe next evidence

An abrupt/unclean system reset is confirmed; exact trigger remains unproven.
Potential paths include power interruption, storage/kernel stall followed by
watchdog reset, and the existing forced Internet-watchdog reboot. Do not select
one merely because it fits the symptom. Ask about PSU/cable/peripherals, preserve
the Windows archive, and collect boot-ID/voltage/memory/I/O telemetry without
stress writes. Any changes to the existing global watchdog/network service need
explicit direction. Passwordless sudo is unavailable; no password was requested
in chat and no privileged configuration was changed.

## Separate reproducible CodexPi write-load defect

Locally, three identical native-goal polls over two paused projects caused six
row updates and changed `updated_at` despite unchanged native observations.
`Database.update` now conditionally writes only changed field values, comparing
inside SQLite (including NULLs and case-sensitive display-name changes).
Identical setting upserts are also suppressed. Repeating the same reproduction
now produces zero row changes and preserves timestamps. FULL synchronous WAL,
real state transitions and transactional notification outbox remain intact.
Four focused checks passed, including rollback/backup, actual native limit
transition/deduplication, Discord late-reset editing and migration recovery.
This patch is not a demonstrated crash fix and has not yet been deployed to the
Pi while the hardware investigation is open.

Relevant primary documentation:
[Pi power/low-voltage behavior](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html),
[kernel watchdog API](https://www.kernel.org/doc/html/latest/watchdog/watchdog-api.html),
[BCM2835 driver capabilities](https://github.com/torvalds/linux/blob/master/drivers/watchdog/bcm2835_wdt.c).
