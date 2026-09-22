"""The interval and window a parent sets, expanded into the clock times a scheduler takes."""
from __future__ import annotations

import pytest

from fridgesheet.config import ConfigError
from fridgesheet.refresh_schedule import MAX_PER_DAY, refresh_times


def test_a_window_that_lands_on_a_step_includes_the_end():
    assert refresh_times("06:00", "21:00", 3) == ["06:00", "09:00", "12:00", "15:00", "18:00", "21:00"]


def test_a_window_that_ends_mid_step_stops_before_it():
    """Never fire outside the window the parent set: 20:00 is the end, so 21:00 is not a time."""
    assert refresh_times("06:00", "20:00", 3) == ["06:00", "09:00", "12:00", "15:00", "18:00"]


def test_start_equal_to_end_is_one_refresh():
    assert refresh_times("06:00", "06:00", 3) == ["06:00"]


def test_an_interval_wider_than_the_window_is_one_refresh_not_none():
    assert refresh_times("06:00", "09:00", 5) == ["06:00"]


def test_an_end_before_the_start_is_refused():
    with pytest.raises(ConfigError, match="overnight"):
        refresh_times("21:00", "06:00", 3)


@pytest.mark.parametrize("every", [0, -1])
def test_a_non_positive_interval_is_refused(every):
    with pytest.raises(ConfigError, match="every_hours"):
        refresh_times("06:00", "21:00", every)


def test_more_than_twelve_a_day_is_refused():
    """A refresh drives a browser through OneLogin; 24 of them is a self-inflicted
    denial of service on the school, not a setting."""
    with pytest.raises(ConfigError, match="12"):
        refresh_times("00:00", "23:00", 1)
    assert len(refresh_times("06:00", "17:00", 1)) == MAX_PER_DAY


@pytest.mark.parametrize("bad", ["6:00", "25:00", "06:60", "noon", ""])
def test_a_time_that_is_not_a_time_is_refused(bad):
    with pytest.raises(ConfigError):
        refresh_times(bad, "21:00", 3)
    with pytest.raises(ConfigError):
        refresh_times("06:00", bad, 3)


def test_minutes_are_kept():
    assert refresh_times("06:30", "12:30", 2) == ["06:30", "08:30", "10:30", "12:30"]
