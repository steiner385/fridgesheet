# tests/test_os_leftovers.py
"""Removing what earlier versions registered with the OS -- and nothing else."""
from __future__ import annotations

import subprocess

from fridgesheet.host import scheduling_linux as lin, scheduling_windows as win


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
    _, run = _run({("/Delete", "/TN"): (1, "", "ERROR: The system cannot find the file specified.")})
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
