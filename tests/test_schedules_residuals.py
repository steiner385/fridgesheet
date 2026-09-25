"""#7 residuals: systemd command lines quoted; and the schedule validators `host` still owns."""
from __future__ import annotations

import pytest

from fridgesheet import host
from fridgesheet.host import service_linux


def test_a_python_path_with_a_space_survives_systemd():
    """#7: `ExecStart={exe} {args}` split "/home/x/My Venv/bin/python" at the space."""
    exe = "/home/x/My Venv/bin/python"
    text = service_linux.unit_text(exe, "-m fridgesheet.cli web --no-browser", "/home/x")
    line = next(l for l in text.splitlines() if l.startswith("ExecStart="))
    assert line.startswith('ExecStart="/home/x/My Venv/bin/python" -m fridgesheet.cli'), line
    plain = service_linux.unit_text("/usr/bin/python3", "-m fridgesheet.cli web", "/x")
    assert "ExecStart=/usr/bin/python3 -m fridgesheet.cli web" in plain                     # nothing to quote, nothing added


# --- moved from the deleted tests/test_host_scheduling.py ---------------------------------

def test_check_schedule_speaks_once_for_both_platforms():
    host.check_schedule("14:00", ["Mon", "Sun"])              # no exception
    with pytest.raises(host.SchedulingError, match="Monday"):
        host.check_schedule("14:00", ["Mon", "Monday"])
    with pytest.raises(host.SchedulingError, match="no days"):
        host.check_schedule("14:00", [])
    with pytest.raises(host.SchedulingError, match="HH:MM"):
        host.check_schedule("9:00", ["Mon"])
    with pytest.raises(host.SchedulingError, match="HH:MM"):
        host.check_schedule("24:00", ["Mon"])


def test_check_schedule_times_accepts_a_list():
    host.check_schedule_times(["06:00", "09:00", "12:00"], ["Mon", "Tue"])


def test_check_schedule_times_refuses_an_empty_list():
    with pytest.raises(host.SchedulingError, match="no times"):
        host.check_schedule_times([], ["Mon"])


def test_check_schedule_times_refuses_the_one_bad_time_among_good_ones():
    """Every time is checked before anything is written, so a bad one leaves nothing behind."""
    with pytest.raises(host.SchedulingError, match="HH:MM"):
        host.check_schedule_times(["06:00", "9:00", "12:00"], ["Mon"])


def test_the_data_refresh_key_is_reserved_however_it_is_spelled():
    """A hand-edited [reports.Data-Refresh] must never be taken for the app's own refresh."""
    for spelling in ("data-refresh", "Data-Refresh", "DATA-REFRESH", " data-refresh "):
        assert host.is_reserved(spelling), spelling
    assert not host.is_reserved("open-work")
    assert not host.is_reserved("view:3")
