"""Short date text for the sheet and the log, built from fields rather than strftime.

The 'no leading zero' strftime codes (percent-dash-m and friends) are a glibc extension;
Python on Windows raises ValueError on them. %a %A %B %p are portable and stay.
"""
from __future__ import annotations

from datetime import date, datetime


def md(d: date) -> str:
    return f"{d.month}/{d.day}"


def wd_md(d: date) -> str:
    return f"{d:%a} {d.month}/{d.day}"


def time12(d: datetime) -> str:
    return f"{d.hour % 12 or 12}:{d.minute:02d} {d:%p}"


def due_time(d: datetime | None, *, from_canvas: bool) -> str:
    """The compact time an assignment is due -- "7:20am", "3pm", "11:59pm" -- or "" when
    nobody told us one.

    "Due first thing in the morning" and "due by the end of the day" are different problems
    for a kid, and the date alone hides which one it is. So the time is shown wherever a due
    date is.

    It is shown only for work Canvas knows, because only Canvas gives a time. HAC hands over
    a bare date, and both ingest paths store that as 23:59 so it sorts and prints as the end
    of its day (`web/ingest.py`, `open_items.py`). That 23:59 is the app's, not the school's,
    and rendering it as "11:59pm" would state a precision nobody has. A Canvas item at 23:59
    really was set to 11:59 PM by a teacher, and says so.
    """
    if d is None or not from_canvas:
        return ""
    return time12(d).replace(" ", "").lower().replace(":00", "")


def day_part(d: datetime | None, *, from_canvas: bool) -> str:
    """"morning", "afternoon", "evening" -- or "" when nobody told us an hour.

    The same timestamp `due_time` formats, said in a word a reader who does not yet read a
    clock at a glance can act on. It adds nothing: 7:20am *is* the morning. A HAC-only item
    has no hour to name, for the same reason it has no time to show.
    """
    if d is None or not from_canvas:
        return ""
    if d.hour < 12:
        return "morning"
    return "afternoon" if d.hour < 17 else "evening"


def wd_md_time(d: datetime) -> str:
    return f"{wd_md(d)} {time12(d)}"


def long_date(d: date) -> str:
    return f"{d:%A}, {d:%B} {d.day}, {d.year}"


def parse_iso(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None
