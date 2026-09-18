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


def wd_md_time(d: datetime) -> str:
    return f"{wd_md(d)} {time12(d)}"


def long_date(d: date) -> str:
    return f"{d:%A}, {d:%B} {d.day}, {d.year}"
