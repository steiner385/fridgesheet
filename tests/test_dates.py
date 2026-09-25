"""Date text without glibc-only strftime codes (%-m, %-d, %-I raise on Windows)."""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from fridgesheet import dates

D = datetime(2026, 9, 14, 14, 5)


def test_month_day_has_no_leading_zeros():
    assert dates.md(D) == "9/14"
    assert dates.md(date(2026, 1, 2)) == "1/2"


def test_weekday_month_day():
    assert dates.wd_md(D) == "Mon 9/14"


def test_twelve_hour_time_covers_noon_midnight_and_afternoon():
    assert dates.time12(D) == "2:05 PM"
    assert dates.time12(datetime(2026, 9, 14, 0, 0)) == "12:00 AM"
    assert dates.time12(datetime(2026, 9, 14, 12, 0)) == "12:00 PM"
    assert dates.time12(datetime(2026, 9, 14, 23, 59)) == "11:59 PM"


def test_combined_and_long_forms():
    assert dates.wd_md_time(D) == "Mon 9/14 2:05 PM"
    assert dates.long_date(D) == "Monday, September 14, 2026"


def test_no_glibc_only_strftime_codes_remain_in_the_package():
    pkg = Path(dates.__file__).parent
    offenders = [p.name for p in pkg.rglob("*.py") if re.search(r"%-[a-zA-Z]", p.read_text(encoding="utf-8"))]
    assert offenders == []


def test_week_start_is_the_monday_of_that_week():
    assert dates.week_start(date(2026, 9, 16)) == date(2026, 9, 14)     # a Wednesday
    assert dates.week_start(date(2026, 9, 14)) == date(2026, 9, 14)     # already a Monday


def test_month_start_is_the_first_of_that_month():
    assert dates.month_start(date(2026, 9, 16)) == date(2026, 9, 1)
