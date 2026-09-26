# tests/test_os_leftovers.py
"""Removing what earlier versions registered with the OS -- and nothing else."""
from __future__ import annotations

import subprocess

import pytest

from fridgesheet.host import SchedulingError, scheduling_linux as lin, scheduling_windows as win


def _run(answers):
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        rc, out, err = answers.get(tuple(argv[1:3]), (0, "", ""))
        return subprocess.CompletedProcess(argv, rc, out, err)
    return calls, run


CSV = ('"\\Fridge Sheet - data-refresh","9/25/2026 7:00:00 AM","Ready"\n'
       '"\\Fridge Sheet - data-refresh","9/25/2026 9:00:00 AM","Ready"\n'
       '"\\Fridge Sheet - web","N/A","Running"\n'
       '"\\Fridge Sheet - WEB","N/A","Ready"\n'
       '"\\Fridge Sheet - view 7","9/28/2026 2:00:00 PM","Ready"\n'
       '"\\Microsoft\\Windows\\Fridge Sheet - elsewhere","N/A","Ready"\n'
       '"\\OneDrive Reporting Task","N/A","Ready"\n')


def test_windows_leftovers_are_this_apps_root_tasks_once_each():
    _, run = _run({("/Query", "/FO"): (0, CSV, "")})
    assert win.leftovers(run) == ["Fridge Sheet - data-refresh", "Fridge Sheet - view 7"]


def test_windows_leftovers_never_include_the_web_task():
    _, run = _run({("/Query", "/FO"): (0, CSV, "")})
    assert not any(n.strip().casefold() == "fridge sheet - web" for n in win.leftovers(run))


def test_windows_remove_task_tolerates_one_already_gone():
    # Gone is `/Query`'s exit code, not `/Delete`'s words: a German Windows says "Das System
    # kann die angegebene Datei nicht finden." (#151).
    calls, run = _run({("/Delete", "/TN"): (1, "", "FEHLER: Das System kann die angegebene Datei nicht finden."),
                       ("/Query", "/TN"): (1, "", "FEHLER: Das System kann die angegebene Datei nicht finden.")})
    win.remove_task("Fridge Sheet - data-refresh", run)
    assert calls[-1][:4] == ["schtasks", "/Query", "/TN", "Fridge Sheet - data-refresh"]


def test_windows_remove_task_raises_when_the_task_is_still_registered_whatever_the_words():
    # A German-worded failure with the task still there (`/Query` succeeds) is a real failure.
    _, run = _run({("/Delete", "/TN"): (1, "", "FEHLER: Zugriff verweigert."),
                   ("/Query", "/TN"): (0, "", "")})
    with pytest.raises(SchedulingError, match="Zugriff verweigert"):
        win.remove_task("Fridge Sheet - data-refresh", run)


MARK = lin.MARKER


def test_linux_leftovers_are_marked_timers_only(tmp_path):
    (tmp_path / "fridgesheet-open-work.timer").write_text(MARK + "[Timer]\n")
    (tmp_path / "fridgesheet-open-work.service").write_text(MARK + "[Service]\n")
    (tmp_path / "fridgesheet-print-sheet.timer").write_text("[Timer]\n")          # hand-written
    (tmp_path / "fridgesheet-web.service").write_text("[Service]\n")
    assert lin.leftovers(tmp_path) == ["fridgesheet-open-work.timer"]


def test_linux_remove_timer_disables_and_deletes_both_halves(tmp_path):
    (tmp_path / "fridgesheet-open-work.timer").write_text(MARK)
    (tmp_path / "fridgesheet-open-work.service").write_text(MARK)
    calls, run = _run({})
    lin.remove_timer("fridgesheet-open-work.timer", run, tmp_path)
    assert ["systemctl", "--user", "disable", "--now", "fridgesheet-open-work.timer"] in calls
    assert ["systemctl", "--user", "daemon-reload"] in calls
    assert list(tmp_path.iterdir()) == []


def test_linux_leaves_a_hand_edited_service_half(tmp_path):
    (tmp_path / "fridgesheet-open-work.timer").write_text(MARK)
    (tmp_path / "fridgesheet-open-work.service").write_text("[Service]\n# edited by hand\n")
    _, run = _run({})
    lin.remove_timer("fridgesheet-open-work.timer", run, tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == ["fridgesheet-open-work.service"]


def test_remove_os_leftovers_reports_what_it_could_not_remove(tmp_path, monkeypatch):
    from fridgesheet.host import scheduling
    monkeypatch.setattr(scheduling, "IS_WINDOWS", True)
    _, run = _run({("/Query", "/FO"): (0, '"\\Fridge Sheet - data-refresh","N/A","Ready"\n', ""),
                   ("/Delete", "/TN"): (1, "", "ERROR: Access is denied.")})
    got = scheduling.remove_os_leftovers(run)
    assert got.removed == []
    (name, error, command), = got.failed
    assert name == "Fridge Sheet - data-refresh" and "denied" in error
    assert command == 'schtasks /Delete /TN "Fridge Sheet - data-refresh" /F'


# --- what remove_timer / _ours / remove_task still guard -----------------------------------

def _marked_pair(d, stem="fridgesheet-open-work"):
    (d / f"{stem}.timer").write_text(MARK)
    (d / f"{stem}.service").write_text(MARK)


@pytest.mark.parametrize("err", ["Failed to disable unit: Unit fridgesheet-open-work.timer does not exist.",
                                 "Unit fridgesheet-open-work.timer not loaded."])
def test_linux_remove_timer_tolerates_a_unit_systemd_no_longer_knows(tmp_path, err):
    _marked_pair(tmp_path)
    _, run = _run({("--user", "disable"): (1, "", err)})
    lin.remove_timer("fridgesheet-open-work.timer", run, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_linux_remove_timer_raises_on_any_other_refusal_and_keeps_the_files(tmp_path):
    _marked_pair(tmp_path)
    _, run = _run({("--user", "disable"): (1, "", "Failed to connect to bus: No such file or directory")})
    with pytest.raises(SchedulingError, match="Failed to connect to bus"):
        lin.remove_timer("fridgesheet-open-work.timer", run, tmp_path)
    assert len(list(tmp_path.iterdir())) == 2


@pytest.mark.parametrize("exc", [FileNotFoundError("systemctl"), subprocess.TimeoutExpired("systemctl", 60)])
def test_linux_remove_timer_names_a_systemctl_that_is_missing_or_hangs(tmp_path, exc):
    _marked_pair(tmp_path)

    def run(argv, **kw):
        raise exc
    with pytest.raises(SchedulingError, match="systemctl --user disable --now fridgesheet-open-work.timer"):
        lin.remove_timer("fridgesheet-open-work.timer", run, tmp_path)


def test_linux_a_timer_that_is_not_utf8_is_never_ours(tmp_path):
    (tmp_path / "fridgesheet-odd.timer").write_bytes(b"\xff\xfe\x00[Timer]\n")
    assert lin._ours(tmp_path / "fridgesheet-odd.timer") is False
    assert lin.leftovers(tmp_path) == []


def test_linux_remove_timer_refuses_an_unmarked_timer_before_any_systemctl(tmp_path):
    (tmp_path / "fridgesheet-print-sheet.timer").write_text("[Timer]\n")
    calls, run = _run({})
    with pytest.raises(SchedulingError, match="not written by this app"):
        lin.remove_timer("fridgesheet-print-sheet.timer", run, tmp_path)
    assert calls == []
    assert (tmp_path / "fridgesheet-print-sheet.timer").exists()


def test_linux_the_web_servers_unit_is_never_ours_even_marked(tmp_path):
    (tmp_path / "fridgesheet-web.service").write_text(MARK + "[Service]\n")
    (tmp_path / "fridgesheet-web.timer").write_text(MARK + "[Timer]\n")
    assert lin._ours(tmp_path / "fridgesheet-web.service") is False
    _, run = _run({})
    lin.remove_timer("fridgesheet-web.timer", run, tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == ["fridgesheet-web.service"]


@pytest.mark.parametrize("name", ["Fridge Sheet - WEB", "Fridge Sheet - Web", " fridge sheet - web "])
def test_windows_remove_task_refuses_the_web_task_in_any_casing_before_any_schtasks(name):
    calls, run = _run({})
    with pytest.raises(SchedulingError, match="refusing"):
        win.remove_task(name, run)
    assert calls == []
