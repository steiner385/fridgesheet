# fridgesheet/reports/__init__.py
"""Registry. Adding a report = a new module here plus one entry in REPORTS."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from .base import Built, BuildContext, Report, ReportError
from .open_work import OpenWorkReport

log = logging.getLogger("fridgesheet.reports")

REPORTS: dict[str, Report] = {
    "open-work": OpenWorkReport(),
}

#: The one spelling of a saved report's key: `view:` and the report id as plain ASCII digits
#: with no leading zero. `resolve` checks it before it opens anything, and
#: `is_schedulable_key` answers the same question with no database at all -- one pattern, so
#: the two cannot drift into disagreeing about what this app's own keys look like.
_VIEW_KEY_RE = re.compile(r"^view:(0|[1-9][0-9]*)\Z")


def get(key: str) -> Report:
    try:
        return REPORTS[key]
    except KeyError:
        raise ReportError(f"unknown report {key!r}; known: {', '.join(REPORTS)}") from None


def resolve(key: str, home: Path | None = None) -> Report:
    """A report key to a report: a code report from the registry, or `view:<id>` from the database.

    The runner calls this; `get` stays the registry's own lookup so a code report never depends
    on a database being present.
    """
    if not key.startswith("view:"):
        return get(key)
    if home is None:
        raise ReportError(f"{key} needs a home directory to load from")
    # Plain ASCII digits only, in their canonical spelling. `int()` would also take "+7",
    # " 7 ", "7_0" and "٧": each resolves to the same report and renders to the same
    # `fridgesheet-view-7` unit, while `[reports.<key>]` keeps one table per spelling -- several
    # keys for one timer, and only the canonical one ever has a row on the Schedules page to
    # turn it off with. `"007".isdigit()` is true too, and resolves to the same report as "7"
    # while rendering to a *different* unit (`safe_key` does not normalize numerals) and
    # storing a second `[reports."view:007"]` table the Schedules page can never show or
    # remove -- so `_VIEW_KEY_RE` refuses a leading zero outright.
    m = _VIEW_KEY_RE.match(key)
    if not m:
        raise ReportError(f"malformed report key {key!r}")
    report_id = int(m.group(1))
    from ..web import db
    from ..web.stores import reports as store
    from .view import ViewReport
    conn = db.open_db(home)
    try:
        row = store.by_id(conn, report_id)
    finally:
        conn.close()
    if row is None:
        raise ReportError(f"no saved report {key!r}")
    return ViewReport(report_id, row["name"], row["definition"])


def is_schedulable_key(key: str) -> bool:
    """True when `key` is one this app installs a schedule under: a code report, or a saved
    view report in its canonical `view:<id>` spelling.

    Decided by spelling alone -- no database is opened, and a `view:<id>` whose report has
    since been deleted still answers True. `schedule remove --all` needs exactly that: it must
    keep working when the database is gone or unreadable (that is why it reads config.toml's
    `[reports.<key>]` tables at all), while still refusing a key it never wrote a schedule for.
    The single-key CLI path gets that refusal from `resolve`, which `--all` cannot call without
    creating the database it goes to such trouble not to create -- so this is that gate, and it
    accepts the same spellings `resolve` does and no others.

    It matters most for one key: `[reports.web]` (or `[reports.Web]`) hand-edited into
    config.toml renders to the web server's own always-on logon task, whose namespace on
    Windows is case-insensitive.
    """
    return key in REPORTS or bool(_VIEW_KEY_RE.match(key))


def available(home: Path | None = None) -> list[Report]:
    """Every report a parent can run or schedule: the code reports first, then the saved views.

    A missing or unreadable database costs the saved reports and nothing else -- this is what
    a page calls before it can render anything, so it must not be the thing that fails.
    """
    out: list[Report] = list(REPORTS.values())
    if home is None:
        return out
    try:
        from ..web import db
        from ..web.stores import reports as store
        from .view import ViewReport
        conn = db.open_db(home)
        try:
            rows = list(store.all(conn))
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001  a listing is never worth a 500
        # A newer build's on-disk schema (db.migrate) is one thing that lands here, and going
        # quiet about it would leave a parent on an old build looking at an empty saved-reports
        # list forever with nothing anywhere saying why.
        log.warning("saved reports unavailable at %s (%s): %s", home, type(e).__name__, e)
        return out
    out.extend(ViewReport(r["id"], r["name"], r["definition"]) for r in rows)
    return out


__all__ = ["REPORTS", "get", "resolve", "is_schedulable_key", "available",
           "Built", "BuildContext", "Report", "ReportError"]
