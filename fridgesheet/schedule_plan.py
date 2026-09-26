"""Which schedule is due, and when each one runs next.

Pure functions over settings, a moment and the last slot each schedule fired: no clock of
its own, no files, no threads. `web/clock.py` is what calls this once a minute and acts on it.

A schedule's *slots* are every configured time on every configured day, as wall-clock times
in the settings' time zone. Only the latest slot at or before now is ever due, so a machine
asleep for a weekend catches up once, not once per missed slot.

Every comparison is made in UTC. Python compares two aware datetimes that share a `tzinfo`
by wall time and ignores `fold`, so the two 01:30s of a fall-back night would compare equal;
in UTC they are an hour apart, which is what they are.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from . import host, refresh_schedule
from .config import ConfigError

REFRESH_TITLE = "Data refresh"
#: How far back `latest_slot` and forward `next_run` look. A week covers every day a
#: schedule can name.
HORIZON_DAYS = 7


@dataclass(frozen=True)
class Schedule:
    key: str                      # a report key, or host.DATA_REFRESH_KEY
    title: str
    times: tuple[str, ...]        # HH:MM
    days: tuple[str, ...]         # host.DAY_NAMES entries


@dataclass(frozen=True)
class Due:
    slot: datetime
    fire: bool                    # False: first sight -- record the slot, run nothing


def _utc(d: datetime) -> datetime:
    return d.astimezone(timezone.utc)


def _slot(day: date, hhmm: str, tz) -> datetime | None:
    """`hhmm` on `day` in `tz`, or None when that wall time does not exist that day (the
    spring-forward gap). A repeated wall time (fall back) is its first occurrence."""
    h, m = (int(x) for x in hhmm.split(":"))
    naive = datetime.combine(day, time(h, m))
    local = naive.replace(tzinfo=tz, fold=0)
    if _utc(local).astimezone(tz).replace(tzinfo=None) != naive:
        return None
    return local


def _slots_on(schedule: Schedule, day: date, tz) -> list[datetime]:
    if host.DAY_NAMES[day.weekday()] not in schedule.days:
        return []
    return sorted((s for t in schedule.times if (s := _slot(day, t, tz)) is not None), key=_utc)


def latest_slot(schedule: Schedule, now: datetime) -> datetime | None:
    tz = now.tzinfo
    for back in range(HORIZON_DAYS + 1):
        passed = [s for s in _slots_on(schedule, now.date() - timedelta(days=back), tz) if _utc(s) <= _utc(now)]
        if passed:
            return passed[-1]
    return None


def next_run(schedule: Schedule, now: datetime) -> datetime | None:
    tz = now.tzinfo
    for ahead in range(HORIZON_DAYS + 1):
        later = [s for s in _slots_on(schedule, now.date() + timedelta(days=ahead), tz) if _utc(s) > _utc(now)]
        if later:
            return later[0]
    return None


def due(schedule: Schedule, now: datetime, last_fired: datetime | None) -> Due | None:
    latest = latest_slot(schedule, now)
    if latest is None:
        return None
    if last_fired is None:
        return Due(latest, fire=False)
    if _utc(latest) > _utc(last_fired):
        return Due(latest, fire=True)
    return None


def schedules_from(settings, reports: list[tuple[str, str, str]]) -> tuple[list[Schedule], dict[str, str]]:
    """The enabled schedules, the refresh first and then reports by key, and a problem per key
    that is on but cannot run. `reports` is `(key, title, default_time)` for every report
    that exists: a `[reports.<key>]` table whose key no longer resolves is ignored."""
    out: list[Schedule] = []
    problems: dict[str, str] = {}
    rc = settings.refresh
    if rc.enabled and rc.days:
        try:
            times = refresh_schedule.refresh_times(rc.start, rc.end, rc.every_hours)
            out.append(Schedule(host.DATA_REFRESH_KEY, REFRESH_TITLE, tuple(times), tuple(rc.days)))
        except ConfigError as e:
            problems[host.DATA_REFRESH_KEY] = str(e)
    for key, title, default_time in sorted(reports):
        r = settings.report_config(key, default_time)
        if not (r.enabled and r.days):
            continue
        if not host.TIME_RE.match(str(r.time)):
            problems[key] = f"[reports.{key}] time must be HH:MM (24-hour), got {r.time!r}"
            continue
        out.append(Schedule(key, title, (r.time,), tuple(r.days)))
    return out, problems
