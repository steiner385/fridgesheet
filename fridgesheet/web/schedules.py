"""The Schedules page's work: config.toml's `[reports.<key>]` and the OS timer or task,
changed together.

One editor for both halves of a schedule. When two pages could write the same keys, one of
them eventually shows a schedule the scheduler does not have.

Every side effect is injectable (`scheduling=`), so the tests never go near systemctl.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .. import config, host, refresh_schedule, reports as registry, runner
from .actions import LOGIN_STAMP, _settings_for, _table, login_passed   # one copy of each (#7, #154)

log = logging.getLogger("fridgesheet.web.schedules")

CONFIG_NAME = "config.toml"
REFRESH_TITLE = "Data refresh"
#: The line a save that could not install answers with. `fridgesheet check` passes the same
#: gate as the button (#154), so a parent at a terminal is told so too.
NO_LOGIN_YET = ("Saved, but nothing is installed yet: run Test login on the Settings page (or "
                "`fridgesheet check` in a terminal) first, then save this schedule again.")


@dataclass(frozen=True)
class Row:
    """One report's line on the page: what config.toml says, and what the host says."""
    key: str
    title: str
    enabled: bool
    time: str
    days: list[str]
    printer: str
    prints: bool
    info: host.ScheduleInfo | None = None   # None when this host does not schedule anything
    unsupported: str = ""                   # host.NotSupported's message, shown in place of the state


@dataclass
class Outcome:
    ok: bool
    messages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def rows(home: Path, *, scheduling=None) -> list[Row]:
    if scheduling is None:
        from ..host import scheduling
    s = _settings_for(home)
    out: list[Row] = []
    for report in registry.available(home):
        rc = s.report_config(report.key, report.default_time)
        info, unsupported = None, ""
        try:
            info = scheduling.describe(report.key)
        except host.NotSupported as e:
            # Nothing under `fridgesheet/host/` raises this for scheduling today -- both
            # platforms have a real implementation -- so this is a line for a third platform
            # (and for an injected scheduler in tests), not a state a parent currently sees.
            unsupported = str(e)
        except Exception as e:          # noqa: BLE001  a scheduler that will not answer is a line of text, not a 500
            # A genuine bug in describe() must not vanish behind this line -- it is the same
            # swallow reports.available() used to do silently, before it hid a real
            # db.migrate() failure (fixed in c695198).
            log.warning("could not describe the schedule for %s (%s): %s", report.key, type(e).__name__, e)
            unsupported = f"the scheduler could not be read: {str(e)[:200]}"
        out.append(Row(key=report.key, title=report.title, enabled=rc.enabled, time=rc.time or report.default_time,
                       days=list(rc.days), printer=rc.printer, prints=rc.prints, info=info, unsupported=unsupported))
    return out


def _describe_once(key: str, scheduling):
    """`(info, error)` from one `describe` call, so `forget` asks the host once (#8) and both of
    its checks read the same answer. A failure other than `NotSupported` is logged here, once."""
    try:
        return scheduling.describe(key), None
    except host.NotSupported as e:
        return None, e
    except Exception as e:              # noqa: BLE001  same swallow, and the same warning, as rows()
        log.warning("could not describe the schedule for %s (%s): %s", key, type(e).__name__, e)
        return None, e


def _unmanageable(key: str, title: str, scheduling, described=None) -> str | None:
    """The error to refuse a write with, or None when this app may manage this report's schedule.

    The template disables the controls on an unmanageable row; this is the same rule on the
    server, where it actually binds. Without it a POST that simply omits `enabled` walks
    straight through the `not enabled` branch: the hand-written `fridgesheet-print-sheet.timer`
    stays enabled and keeps printing at 2 PM, while the page answers "not scheduled".

    A scheduler that cannot answer is not a reason to refuse a save: `describe` already
    degrades to a line of text on the page (`rows`), and `install`/`remove` do their own
    ownership check before touching anything.
    """
    info, _ = described or _describe_once(key, scheduling)
    if info is None:
        return None                     # nothing here schedules anything, or it cannot say
    if info.manageable:
        return None
    name = scheduling.blocking_name(key)
    return (f"{title} is already scheduled by {info.managed_by}, which this app did not write, so it "
            f"will not change or remove it. That schedule is still running"
            + (f" (next run {info.next_run})" if info.next_run else "") +
            f". Turn it off yourself first -- on Linux: systemctl --user disable --now "
            f"{name} -- then save here.")


def _installed_or_unknown(key: str, scheduling, described=None) -> bool:
    """False when nothing is installed for `key`, or when nothing here could have installed it.

    `forget` uses this to decide whether `remove()` is worth calling at all, and the two
    failure modes it can meet are opposites:

    - `NotSupported` -- this host schedules nothing at all, so there is certainly nothing
      installed and nothing for `remove()` to do: False, exactly like a clean
      `installed=False`. (No shipped `host` module raises it for scheduling today; see
      `rows()` above.)
    - Any *other* failure (`describe` raised for a reason nobody anticipated -- the same
      swallow-with-a-warning `rows()`/`_unmanageable` do) -- this says nothing about what is
      installed, so it must not read as "nothing there" and skip a `remove()` that might have
      real work: True.

    A clean `installed=False` is the ordinary answer, and `describe` gives one even when
    systemd cannot reach the bus, since `_is_enabled` treats a non-zero `is-enabled` as "no"
    rather than raising.
    """
    info, error = described or _describe_once(key, scheduling)
    if info is not None:
        return info.installed
    return not isinstance(error, host.NotSupported)


def forget(key: str, *, home: Path, log: Callable[[str], None], title: str = "", scheduling=None) -> Outcome:
    """Remove this report's schedule entirely: the host's unit or task *and* `[reports.<key>]`.

    `save(enabled=False)` is the off switch, and it deliberately keeps the settings so turning
    the schedule back on remembers them. This is the other thing: the key itself is about to
    stop resolving (a saved report is being deleted), so the table has to go with it.
    `reports.id` is an `INTEGER PRIMARY KEY` without `AUTOINCREMENT`, so sqlite reissues a
    deleted id -- a left-behind `[reports."view:3"]` would become the *next* report's schedule.

    The unit goes first and `ok` is False if it will not: the caller must refuse the delete,
    because an orphaned timer with no row to point at has no row on the Schedules page either,
    and so no way for a parent to ever turn it off.

    `remove()` itself is skipped -- not just tolerated when it fails -- for a report that
    `describe` already says is not installed *and* that has no `[reports.<key>]` table either:
    a brand-new report that was never scheduled has nothing for the host to remove, and a
    server started outside a user D-Bus session would otherwise turn "nothing to do" into a
    refused delete for a schedule that never existed (#36).
    """
    if scheduling is None:
        from ..host import scheduling
    described = _describe_once(key, scheduling)
    refusal = _unmanageable(key, title or key, scheduling, described)
    if refusal:
        return Outcome(False, errors=[refusal])

    path = home / CONFIG_NAME
    doc = config.load_config_doc(path)
    reports = doc.get("reports")
    has_table = isinstance(reports, dict) and key in reports

    if has_table or _installed_or_unknown(key, scheduling, described):
        try:
            scheduling.remove(key)
        except host.NotSupported:
            pass                        # this host installed nothing, so nothing is left behind
        except host.SchedulingError as e:
            return Outcome(False, errors=[f"The schedule could not be removed: {e}"])

    if has_table:
        del reports[key]
        config.save_config_doc(path, doc)
        log(f"Removed the schedule for {key}.")
        return Outcome(True, ["Its schedule was removed too."])
    return Outcome(True)


def save(key: str, *, enabled: bool, time: str, days: list[str], printer: str, prints: bool,
         home: Path, log: Callable[[str], None], scheduling=None) -> Outcome:
    """Write this report's schedule, then make the host agree with it.

    Ownership first: a schedule this app did not write is refused before the file is touched,
    because writing `enabled = false` for a timer this app will not disable is the page telling
    the parent something that is not true. Validation next, so a bad time never reaches either
    the file or the scheduler. The file is written before the scheduler is called, so a
    scheduler that refuses costs the install and never the parent's typing -- the message says
    exactly that.
    """
    if host.is_reserved(key):
        return Outcome(False, errors=[
            f"{key!r} is a reserved name Fridge Sheet uses for its own data-refresh schedule; "
            "a report cannot be scheduled under it. Rename the report and save again."])
    if scheduling is None:
        from ..host import scheduling
    try:
        report = registry.resolve(key, home)
    except registry.ReportError as e:
        return Outcome(False, errors=[str(e)])
    refusal = _unmanageable(key, report.title, scheduling)
    if refusal:
        return Outcome(False, errors=[refusal])
    try:
        # Turning a schedule off never needs a day ticked (#146): unticking the switch along
        # with every day used to be refused, and the OS task stayed.
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
        try:
            scheduling.remove(key)
        except host.NotSupported as e:
            return Outcome(True, messages + [str(e)])
        except host.SchedulingError as e:
            return Outcome(False, messages, [f"Saved, but the schedule could not be removed: {e}"])
        messages.append(f"{report.title} is not scheduled.")
        log(messages[-1])
        return Outcome(True, messages)

    if not login_passed(home):
        messages.append(NO_LOGIN_YET)
        log(messages[-1])
        return Outcome(True, messages)

    s = _settings_for(home)
    exe, args, workdir = scheduling.command_for(key)
    try:
        scheduling.install(key, [time], days, exe, args, workdir, title=report.title,
                           home=str(home), timezone=s.timezone)
    except host.NotSupported as e:
        return Outcome(True, messages + [str(e)])
    except host.SchedulingError as e:
        return Outcome(False, messages, [f"Saved, but the schedule could not be installed: {e}"])
    messages.append(f"Scheduled: {', '.join(days)} at {time}" + ("" if prints else ", PDF only") + ".")
    log(messages[-1])
    # A scheduled report runs `--no-refresh` (host/scheduling.command_for) and refuses a
    # snapshot older than a day, so with the refresh off it prints once and then FAILs every
    # day (#120). Turning a report on turns the refresh on with it; the report is already
    # installed, so a refresh that will not install is an error beside the success, not
    # instead of it.
    if not s.refresh.enabled:
        turned_on = ensure_refresh(home=home, log=log, scheduling=scheduling)
        messages += turned_on.messages
        return Outcome(True, messages, turned_on.errors)
    return Outcome(True, messages)


def ensure_refresh(*, home: Path, log: Callable[[str], None], scheduling=None) -> Outcome:
    """Turn the data refresh on if it is off, keeping whatever `[refresh]` already says about
    the interval, window and days (the defaults for a household that never saved it; the
    parent's own values if they saved it and later switched it off).

    Called after a report schedule is installed, so the login stamp is known to exist and
    `save_refresh`'s "nothing is installed yet" branch cannot be reached from here.
    """
    if scheduling is None:
        from ..host import scheduling
    rc = _settings_for(home).refresh
    if rc.enabled:
        return Outcome(True)
    out = save_refresh(enabled=True, every_hours=rc.every_hours, start=rc.start, end=rc.end,
                       days=list(rc.days), home=home, log=log, scheduling=scheduling)
    if not out.ok:
        return Outcome(False, errors=[
            "The data refresh, which a scheduled report needs, is on in config.toml but its task "
            f"could not be installed ({'; '.join(out.errors)}). Save Refresh the data again."])
    days = "every day" if set(rc.days) >= set(host.DAY_NAMES) else ", ".join(rc.days)
    every = "hour" if rc.every_hours == 1 else f"{rc.every_hours} hours"
    message = (f"Turned on the data refresh too (every {every}, {rc.start}–{rc.end}, {days}): "
               "a scheduled report prints from the last refresh, and refuses one older than "
               f"{runner.MAX_DATA_AGE_HOURS} hours.")
    log(message)
    return Outcome(True, [message] + [m for m in out.messages if not m.startswith(("Saved", "Refreshing at"))])


def refresh_warning(rows: list[Row], refresh: "RefreshRow | None") -> str:
    """The banner for a page that has a report scheduled and the refresh off (#120): the
    state that prints once and then fails every day. Empty when there is nothing to say."""
    if refresh is None or refresh.enabled:
        return ""
    on = [r.title for r in rows if r.enabled]
    if not on:
        return ""
    return (f"{', '.join(on)} {'is' if len(on) == 1 else 'are'} scheduled but the data refresh is off. "
            "A scheduled report prints from the last refresh and refuses once that is more than "
            f"{runner.MAX_DATA_AGE_HOURS} hours old, so tick Refresh on a schedule below and Save.")


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
    info: host.ScheduleInfo | None = None
    unsupported: str = ""


def refresh_row(home: Path, *, scheduling=None) -> RefreshRow:
    if scheduling is None:
        from ..host import scheduling
    rc = _settings_for(home).refresh
    times, problem = [], ""
    try:
        times = refresh_schedule.refresh_times(rc.start, rc.end, rc.every_hours)
    except config.ConfigError as e:
        problem = str(e)
    info, unsupported = None, ""
    try:
        info = scheduling.describe(host.DATA_REFRESH_KEY)
    except host.NotSupported as e:
        unsupported = str(e)
    except Exception as e:                  # noqa: BLE001  same swallow as rows()
        log.warning("could not describe the data-refresh schedule (%s): %s", type(e).__name__, e)
        unsupported = f"the scheduler could not be read: {str(e)[:200]}"
    return RefreshRow(enabled=rc.enabled, every_hours=rc.every_hours, start=rc.start, end=rc.end,
                      days=list(rc.days), times=times, problem=problem, info=info, unsupported=unsupported)


def save_refresh(*, enabled: bool, every_hours: int, start: str, end: str, days: list[str],
                 home: Path, log: Callable[[str], None], scheduling=None) -> Outcome:
    """Write `[refresh]`, then make the host agree with it.

    Same order as `save`: validate before writing, write the file before calling the
    scheduler, so a scheduler that refuses costs the install and never the parent's typing.
    There is no ownership check: `data-refresh` is this app's own key and nothing else
    installs it -- the hand-written refresh pair lives at a different name and stays
    protected by `_HAND_WRITTEN_REFRESH`.
    """
    if scheduling is None:
        from ..host import scheduling
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
        try:
            scheduling.remove(host.DATA_REFRESH_KEY)
        except host.NotSupported as e:
            return Outcome(True, messages + [str(e)])
        except host.SchedulingError as e:
            return Outcome(False, messages, [f"Saved, but the schedule could not be removed: {e}"])
        messages.append("The data is not refreshed on a schedule.")
        log(messages[-1])
        return Outcome(True, messages)

    if not login_passed(home):
        messages.append(NO_LOGIN_YET)
        log(messages[-1])
        return Outcome(True, messages)

    try:
        install_refresh(times, days, home=home, timezone=_settings_for(home).timezone, scheduling=scheduling)
    except host.NotSupported as e:
        return Outcome(True, messages + [str(e)])
    except host.SchedulingError as e:
        return Outcome(False, messages, [f"Saved, but the schedule could not be installed: {e}"])
    messages.append(f"Refreshing at {', '.join(times)} on {', '.join(days)}.")
    log(messages[-1])
    return Outcome(True, messages)


def install_refresh(times: list[str], days: list[str], *, home: Path, timezone: str, scheduling) -> None:
    """Install the data-refresh task. The one call both this page and `fridgesheet schedule
    install data-refresh` make, so the CLI's task cannot differ from the page's (#146)."""
    exe, args, workdir = scheduling.command_for(host.DATA_REFRESH_KEY)
    scheduling.install(host.DATA_REFRESH_KEY, times, days, exe, args, workdir,
                       title=REFRESH_TITLE, home=str(home), timezone=timezone)


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
