"""Which schedule is due, and when each runs next. Pure: no clock, no files, no threads."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fridgesheet import config, host
from fridgesheet.schedule_plan import Due, Schedule, due, latest_slot, next_run, schedules_from

TZ = ZoneInfo("America/New_York")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")
ALL = host.DAY_NAMES
PRINT = Schedule("open-work", "Open Work Sheet", ("14:00",), WEEKDAYS)
REFRESH = Schedule(host.DATA_REFRESH_KEY, "Data refresh", ("05:00", "07:00", "09:00"), ALL)


def at(y, mo, d, h, mi=0, fold=0):
    return datetime(y, mo, d, h, mi, tzinfo=TZ, fold=fold)


# 2026-09-25 is a Friday.

def test_not_yet_due_before_the_time():
    assert latest_slot(PRINT, at(2026, 9, 25, 13, 59)) == at(2026, 9, 24, 14)


def test_due_exactly_on_the_minute():
    assert latest_slot(PRINT, at(2026, 9, 25, 14, 0)) == at(2026, 9, 25, 14)


def test_the_latest_of_several_times_is_the_slot():
    assert latest_slot(REFRESH, at(2026, 9, 25, 8, 30)) == at(2026, 9, 25, 7)


def test_a_day_not_ticked_is_skipped():
    # Sunday 2026-09-27 at 15:00: the latest weekday slot is Friday's.
    assert latest_slot(PRINT, at(2026, 9, 27, 15)) == at(2026, 9, 25, 14)


def test_no_days_means_no_slot():
    assert latest_slot(Schedule("x", "x", ("14:00",), ()), at(2026, 9, 25, 15)) is None


def test_first_sight_records_without_firing():
    assert due(PRINT, at(2026, 9, 25, 16), None) == Due(at(2026, 9, 25, 14), fire=False)


def test_a_new_slot_fires():
    assert due(PRINT, at(2026, 9, 25, 14, 1), at(2026, 9, 24, 14)) == Due(at(2026, 9, 25, 14), fire=True)


def test_an_already_fired_slot_does_not_fire_again():
    assert due(PRINT, at(2026, 9, 25, 14, 30), at(2026, 9, 25, 14)) is None


def test_a_weekend_asleep_is_one_catch_up_not_many():
    # Last fired Friday 07:00; woken Monday 08:00. Only Monday's 07:00 is due.
    assert due(REFRESH, at(2026, 9, 28, 8), at(2026, 9, 25, 7)) == Due(at(2026, 9, 28, 7), fire=True)


def test_last_fired_in_another_offset_compares_by_instant():
    # Stored as UTC text; read back with a fixed offset. Same instant as 14:00 EDT.
    last = datetime.fromisoformat("2026-09-25T18:00:00+00:00")
    assert due(PRINT, at(2026, 9, 25, 15), last) is None


def test_spring_forward_gap_has_no_slot_that_day():
    # 2026-03-08: 02:00 -> 03:00 in America/New_York. 02:30 does not exist.
    s = Schedule("x", "x", ("02:30",), ALL)
    assert latest_slot(s, at(2026, 3, 8, 4)) == at(2026, 3, 7, 2, 30)


def test_fall_back_repeat_fires_once():
    # 2026-11-01: 01:30 happens twice. The slot is the first (fold=0); the second is not due.
    s = Schedule("x", "x", ("01:30",), ALL)
    first = at(2026, 11, 1, 1, 30, fold=0)
    assert due(s, at(2026, 11, 1, 1, 45, fold=0), at(2026, 10, 31, 1, 30)) == Due(first, fire=True)
    assert due(s, at(2026, 11, 1, 1, 45, fold=1), first) is None


def test_a_clock_moved_backwards_fires_nothing():
    assert due(PRINT, at(2026, 9, 25, 12), at(2026, 9, 25, 14)) is None


def test_next_run_later_today():
    assert next_run(PRINT, at(2026, 9, 25, 9)) == at(2026, 9, 25, 14)


def test_next_run_on_the_minute_is_the_next_one():
    assert next_run(PRINT, at(2026, 9, 24, 14)) == at(2026, 9, 25, 14)


def test_next_run_skips_the_weekend():
    assert next_run(PRINT, at(2026, 9, 25, 15)) == at(2026, 9, 28, 14)


def test_next_run_with_no_days_is_none():
    assert next_run(Schedule("x", "x", ("14:00",), ()), at(2026, 9, 25, 9)) is None


REPORTS = [("open-work", "Open Work Sheet", "14:00"), ("view:3", "Grade trend", "07:00")]


def _settings(doc):
    s = config.Settings()
    config.settings_from_doc(doc, s)
    return s


def test_schedules_from_lists_enabled_ones_refresh_first():
    s = _settings({"refresh": {"enabled": True, "every_hours": 2, "start": "05:00", "end": "09:00"},
                   "reports": {"view:3": {"enabled": True, "time": "07:15", "days": ["Mon"]},
                               "open-work": {"enabled": True}}})
    got, problems = schedules_from(s, REPORTS)
    assert [x.key for x in got] == [host.DATA_REFRESH_KEY, "open-work", "view:3"]
    assert got[0].times == ("05:00", "07:00", "09:00")
    assert got[1].times == ("14:00",) and got[2] == Schedule("view:3", "Grade trend", ("07:15",), ("Mon",))
    assert problems == {}


def test_disabled_and_unknown_keys_are_left_out():
    s = _settings({"reports": {"open-work": {"enabled": False}, "view:99": {"enabled": True}}})
    assert schedules_from(s, REPORTS) == ([], {})


def test_a_refresh_that_does_not_expand_is_a_problem_not_a_schedule():
    s = _settings({"refresh": {"enabled": True, "every_hours": 3, "start": "06:00", "end": "21:00"}})
    s.refresh.end = "05:00"                       # past the loader's own checks: a hand edit
    got, problems = schedules_from(s, REPORTS)
    assert got == [] and "overnight" in problems[host.DATA_REFRESH_KEY]


def test_an_enabled_report_with_no_days_is_not_a_schedule():
    s = _settings({"reports": {"open-work": {"enabled": True, "days": []}}})
    assert schedules_from(s, REPORTS) == ([], {})
