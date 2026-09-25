"""The Schedules page's work: `config.toml`'s `[reports.<key>]` and `[refresh]`.

Saving writes the file and nothing else -- the server's own clock (web/clock.py) reads it
every minute. What the page shows about a schedule comes from the app's own records: the
plan's next run and the newest run with `trigger = 'schedule'`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from .. import config, dates, host, refresh_schedule, reports as registry, schedule_plan
from . import clock, db
from .actions import _settings_for, _table          # one copy of each (#7)

CONFIG_NAME = "config.toml"
REFRESH_TITLE = schedule_plan.REFRESH_TITLE


@dataclass(frozen=True)
class Row:
    """One report's line on the page: what config.toml says, when the plan runs it next, and
    how its last scheduled run went."""
    key: str
    title: str
    enabled: bool
    time: str
    days: list[str]
    printer: str
    prints: bool
    next_run: datetime | None = None
    last_run: str = ""
    problem: str = ""                       # why an enabled schedule cannot run, from the plan


@dataclass
class Outcome:
    ok: bool
    messages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def last_scheduled(conn, report_key: str) -> str:
    """The newest run this report's schedule made, in words -- "" when there is none."""
    row = conn.execute("SELECT started_at, outcome FROM runs WHERE report_key = ? AND trigger = 'schedule' "
                       "ORDER BY started_at DESC, id DESC LIMIT 1", (report_key,)).fetchone()
    if row is None:
        return ""
    started = datetime.fromisoformat(row["started_at"])
    return f"{dates.wd_md_time(started.replace(second=0, microsecond=0))}, {row['outcome']}"


def _plan(home: Path, now: datetime):
    """`({key: next run}, {key: problem})` from the same reading of the settings the clock makes."""
    schedules, problems = clock.configured(home)
    return {s.key: schedule_plan.next_run(s, now) for s in schedules}, problems


def rows(home: Path, *, now: datetime) -> list[Row]:
    s = _settings_for(home)
    nexts, problems = _plan(home, now)
    conn = db.open_db(home)
    try:
        out = []
        for report in registry.available(home):
            rc = s.report_config(report.key, report.default_time)
            out.append(Row(key=report.key, title=report.title, enabled=rc.enabled, time=rc.time or report.default_time,
                           days=list(rc.days), printer=rc.printer, prints=rc.prints,
                           next_run=nexts.get(report.key), last_run=last_scheduled(conn, report.key),
                           problem=problems.get(report.key, "")))
        return out
    finally:
        conn.close()


def forget(key: str, *, home: Path, log: Callable[[str], None], title: str = "") -> Outcome:
    """Drop `[reports.<key>]` for a report being deleted. `reports.id` is reissued by sqlite, so a
    left-behind `[reports."view:3"]` would become the *next* report's schedule.

    `save(enabled=False)` is the off switch, and it deliberately keeps the settings so turning
    the schedule back on remembers them; this is for a key that is about to stop resolving.
    There is nothing else to remove: the clock reads this file, so no table means no schedule.
    """
    path = home / CONFIG_NAME
    doc = config.load_config_doc(path)
    reports = doc.get("reports")
    if isinstance(reports, dict) and key in reports:
        del reports[key]
        config.save_config_doc(path, doc)
        log(f"Removed the schedule for {key}.")
        return Outcome(True, ["Its schedule was removed too."])
    return Outcome(True)


def save(key: str, *, enabled: bool, time: str, days: list[str], printer: str, prints: bool,
         home: Path, log: Callable[[str], None]) -> Outcome:
    """Write this report's schedule. Validation first, so a bad time never reaches the file;
    the clock picks the new values up on its next tick."""
    if host.is_reserved(key):
        return Outcome(False, errors=[
            f"{key!r} is a reserved name Fridge Sheet uses for its own data-refresh schedule; "
            "a report cannot be scheduled under it. Rename the report and save again."])
    try:
        report = registry.resolve(key, home)
    except registry.ReportError as e:
        return Outcome(False, errors=[str(e)])
    try:
        # Turning a schedule off never needs a day ticked (#146): unticking the switch along
        # with every day used to be refused.
        host.check_schedule(time, days, require_days=bool(enabled))
    except host.SchedulingError as e:
        return Outcome(False, errors=[str(e)])

    path = home / CONFIG_NAME
    doc = config.load_config_doc(path)
    rep = _table(_table(doc, "reports"), key)
    rep.update(enabled=bool(enabled), time=time, days=[str(d) for d in days],
               printer=printer.strip(), print=bool(prints))
    config.save_config_doc(path, doc)
    messages = [f"Saved {report.title}."]
    log(messages[-1])

    if not enabled:
        messages.append(f"{report.title} is not scheduled.")
        log(messages[-1])
        return Outcome(True, messages)
    messages.append(f"Scheduled: {', '.join(days)} at {time}" + ("" if prints else ", PDF only") + ".")
    log(messages[-1])
    return Outcome(True, messages)


@dataclass(frozen=True)
class RefreshRow:
    """The app's own data-refresh schedule, as the page shows it."""
    enabled: bool
    every_hours: int
    start: str
    end: str
    days: list[str]
    times: list[str]                        # the expansion, or [] when it does not expand
    problem: str = ""                       # why it does not expand, shown in place of the times
    next_run: datetime | None = None
    last_run: str = ""


def refresh_row(home: Path, *, now: datetime) -> RefreshRow:
    rc = _settings_for(home).refresh
    times, problem = [], ""
    try:
        times = refresh_schedule.refresh_times(rc.start, rc.end, rc.every_hours)
    except config.ConfigError as e:
        problem = str(e)
    conn = db.open_db(home)
    try:
        last = last_scheduled(conn, "refresh")          # a refresh's runs are recorded as "refresh"
    finally:
        conn.close()
    return RefreshRow(enabled=rc.enabled, every_hours=rc.every_hours, start=rc.start, end=rc.end,
                      days=list(rc.days), times=times, problem=problem,
                      next_run=_plan(home, now)[0].get(host.DATA_REFRESH_KEY), last_run=last)


def save_refresh(*, enabled: bool, every_hours: int, start: str, end: str, days: list[str],
                 home: Path, log: Callable[[str], None]) -> Outcome:
    """Write `[refresh]`. Same order as `save`: validate before writing, so a window that does
    not expand never reaches the file."""
    try:
        times = refresh_schedule.refresh_times(start, end, every_hours)
        host.check_schedule_times(times, days, require_days=bool(enabled))     # off needs no day (#146)
    except (config.ConfigError, host.SchedulingError) as e:
        return Outcome(False, errors=[str(e)])

    path = home / CONFIG_NAME
    doc = config.load_config_doc(path)
    tbl = _table(doc, "refresh")
    tbl.update(enabled=bool(enabled), every_hours=int(every_hours), start=str(start),
               end=str(end), days=[str(d) for d in days])
    config.save_config_doc(path, doc)
    messages = ["Saved the refresh schedule."]
    log(messages[-1])

    if not enabled:
        messages.append("The data is not refreshed on a schedule.")
    else:
        messages.append(f"Refreshing at {', '.join(times)} on {', '.join(days)}.")
    log(messages[-1])
    return Outcome(True, messages)


def record_enabled(home: Path, key: str, enabled: bool, *, create: bool = True) -> None:
    """Write just the `enabled` switch for `key` -- `[refresh]` for the data-refresh key,
    `[reports.<key>]` for a report -- leaving every other value in the table alone.

    For the CLI, which installs and removes schedules without this page (#146): without it
    `fridgesheet reports` said "disabled" while the timer ran, and `doctor` failed after a CLI
    remove because config.toml still said on. `create=False` skips a table that does not
    exist yet, where the absent switch already reads as off."""
    path = home / CONFIG_NAME
    doc = config.load_config_doc(path)
    if key == host.DATA_REFRESH_KEY:
        if not create and not isinstance(doc.get("refresh"), dict):
            return
        tbl = _table(doc, "refresh")
    else:
        reports = doc.get("reports")
        if not create and not (isinstance(reports, dict) and isinstance(reports.get(key), dict)):
            return
        tbl = _table(_table(doc, "reports"), key)
    tbl["enabled"] = bool(enabled)
    config.save_config_doc(path, doc)
