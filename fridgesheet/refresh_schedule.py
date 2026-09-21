"""An interval and a window, as the clock times a scheduler actually takes.

A parent sets "every 3 hours between 06:00 and 21:00"; Task Scheduler and systemd both want
the individual times. Expanding here -- rather than leaning on Task Scheduler's `<Repetition>`
or systemd's `OnUnitActiveSec` -- keeps one meaning on both platforms: systemd has no way to
bound a repetition to a window, and `OnUnitActiveSec` counts from the last activation, so a
refresh that takes eight minutes would push every later run of the day eight minutes further
out, by a different amount on every machine.
"""
from __future__ import annotations

import re

from .config import ConfigError

#: The most refreshes a day this will install. A refresh drives a real browser through
#: OneLogin into Canvas and HAC -- one to three minutes on a fast box, eight to ten on a
#: slow one -- so an hourly pull around the clock is a great many logins against the
#: district's systems. Hourly inside a twelve-hour window is still available.
MAX_PER_DAY = 12

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _minutes(label: str, value: str) -> int:
    if not _TIME_RE.match(str(value)):
        raise ConfigError(f"[refresh] {label} must be HH:MM (24-hour), got {value!r}")
    h, m = (int(x) for x in str(value).split(":"))
    return h * 60 + m


def refresh_times(start: str, end: str, every_hours: int) -> list[str]:
    """The clock times to refresh at, inclusive of both ends where the step lands on them.

    `06:00`, `21:00`, every 3 -> `["06:00","09:00","12:00","15:00","18:00","21:00"]`.
    """
    first, last = _minutes("start", start), _minutes("end", end)
    if isinstance(every_hours, bool) or not isinstance(every_hours, int) or every_hours <= 0:
        raise ConfigError(f"[refresh] every_hours must be a whole number of hours above zero, got {every_hours!r}")
    if last < first:
        raise ConfigError(f"[refresh] end ({end}) is before start ({start}); overnight windows are not supported")
    step = every_hours * 60
    times = []
    at = first
    while at <= last:
        times.append(f"{at // 60:02d}:{at % 60:02d}")
        at += step
    if len(times) > MAX_PER_DAY:
        raise ConfigError(
            f"[refresh] every {every_hours} h from {start} to {end} is {len(times)} refreshes a day; "
            f"the most this will install is {MAX_PER_DAY}")
    return times
