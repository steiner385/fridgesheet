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

from .. import config, host, reports as registry

log = logging.getLogger("fridgesheet.web.schedules")

CONFIG_NAME = "config.toml"
LOGIN_STAMP = "login-ok.txt"


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


def _settings_for(home: Path) -> config.Settings:
    s = config.Settings(home=home)
    config.settings_from_doc(config.load_config_doc(home / CONFIG_NAME), s)
    return s


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


def _table(doc: dict, key: str) -> dict:
    if not isinstance(doc.get(key), dict):
        doc[key] = {}
    return doc[key]


def _unmanageable(key: str, title: str, scheduling) -> str | None:
    """The error to refuse a write with, or None when this app may manage this report's schedule.

    The template disables the controls on an unmanageable row; this is the same rule on the
    server, where it actually binds. Without it a POST that simply omits `enabled` walks
    straight through the `not enabled` branch: the hand-written `fridgesheet-print-sheet.timer`
    stays enabled and keeps printing at 2 PM, while the page answers "not scheduled".

    A scheduler that cannot answer is not a reason to refuse a save: `describe` already
    degrades to a line of text on the page (`rows`), and `install`/`remove` do their own
    ownership check before touching anything.
    """
    try:
        info = scheduling.describe(key)
    except host.NotSupported:
        return None                     # nothing here schedules anything; nothing to protect
    except Exception as e:              # noqa: BLE001  same swallow, and the same warning, as rows()
        log.warning("could not describe the schedule for %s (%s): %s", key, type(e).__name__, e)
        return None
    if info.manageable:
        return None
    name = scheduling.blocking_name(key)
    return (f"{title} is already scheduled by {info.managed_by}, which this app did not write, so it "
            f"will not change or remove it. That schedule is still running"
            + (f" (next run {info.next_run})" if info.next_run else "") +
            f". Turn it off yourself first -- on Linux: systemctl --user disable --now "
            f"{name} -- then save here.")


def _installed_or_unknown(key: str, scheduling) -> bool:
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
    try:
        return scheduling.describe(key).installed
    except host.NotSupported:
        return False
    except Exception:                   # noqa: BLE001  same swallow as rows()/_unmanageable
        return True


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
    refusal = _unmanageable(key, title or key, scheduling)
    if refusal:
        return Outcome(False, errors=[refusal])

    path = home / CONFIG_NAME
    doc = config.load_config_doc(path)
    reports = doc.get("reports")
    has_table = isinstance(reports, dict) and key in reports

    if has_table or _installed_or_unknown(key, scheduling):
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
        host.check_schedule(time, days)
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

    if not (home / LOGIN_STAMP).exists():
        messages.append("Saved, but nothing is installed yet: run Test login on the Settings page first, "
                        "then save this schedule again.")
        log(messages[-1])
        return Outcome(True, messages)

    s = _settings_for(home)
    exe, args, workdir = scheduling.command_for(key)
    try:
        scheduling.install(key, time, days, exe, args, workdir, title=report.title,
                           home=str(home), timezone=s.timezone)
    except host.NotSupported as e:
        return Outcome(True, messages + [str(e)])
    except host.SchedulingError as e:
        return Outcome(False, messages, [f"Saved, but the schedule could not be installed: {e}"])
    messages.append(f"Scheduled: {', '.join(days)} at {time}" + ("" if prints else ", PDF only") + ".")
    log(messages[-1])
    return Outcome(True, messages)
