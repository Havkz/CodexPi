"""Read-only account telemetry; never decides whether a goal may execute."""
import math


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def windows(account):
    result = {}
    limits = account.get('rateLimits') or {}
    if not isinstance(limits, dict) or limits.get('limitId') not in (None, 'codex'):
        return result
    for key in ('primary', 'secondary'):
        window = limits.get(key) or {}
        if not isinstance(window, dict):
            continue
        duration, used = window.get('windowDurationMins'), window.get('usedPercent')
        if not number(duration) or duration not in (300, 1440, 10080):
            continue
        if not number(used) or not 0 <= used <= 100:
            continue
        reset = window.get('resetsAt')
        result['weekly' if duration == 10080 else 'daily'] = {
            'remaining': 100 - used, 'duration': duration,
            'reset_at': reset if number(reset) and reset > 0 else None}
    return result
