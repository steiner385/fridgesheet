"""The systemd user units the app writes for a scheduled report. Nothing here runs systemctl."""
from __future__ import annotations

import subprocess

import pytest

from lakota_grades.host import ScheduleInfo, SchedulingError, scheduling_linux as sl
from lakota_grades.host import service_linux


def test_unit_names_come_from_the_key_alone():
    assert sl.unit_stem("open-work") == "lakota-open-work"
    assert sl.service_unit("open-work") == "lakota-open-work.service"
    assert sl.timer_unit("view:7") == "lakota-view-7.timer"          # no colon: systemd reads one as an instance
    assert sl.unit_stem("view:7") != sl.unit_stem("view:8")


def test_the_service_is_a_oneshot_that_is_given_time_to_finish():
    text = sl.service_text("open-work", "Open Work Sheet", "/venv/bin/lakota-grades", "run open-work",
                           "/home/tony", "/home/tony/.lakota-grades")
    assert text.startswith(sl.MARKER)          # `_check_ownership` reads this back before ever touching a unit
    assert "Description=Lakota Sheet: Open Work Sheet" in text
    assert "Type=oneshot" in text
    assert "ExecStart=/venv/bin/lakota-grades run open-work" in text
    assert "WorkingDirectory=/home/tony" in text
    assert "Environment=LAKOTA_GRADES_HOME=/home/tony/.lakota-grades" in text
    # The refresh inside is 3 kids x 2 sites plus a possible login: 1-3 minutes. systemd's
    # default 90 s start timeout would SIGTERM it partway through every run.
    assert "TimeoutStartSec=900" in text
    assert "[Install]" not in text            # a oneshot pulled by a timer is never enabled itself
    assert "network-online" not in text       # that target does not exist in a user manager's graph


def test_the_timer_lists_its_days_and_catches_up():
    text = sl.timer_text("open-work", "Open Work Sheet", "14:00", ["Mon", "Tue", "Wed", "Thu", "Fri"],
                         "America/New_York")
    assert text.startswith(sl.MARKER)
    assert "OnCalendar=Mon,Tue,Wed,Thu,Fri 14:00 America/New_York" in text
    assert "Mon.." not in text                # a list, not a range: correct for any set of days
    assert "Persistent=true" in text
    assert "Unit=lakota-open-work.service" in text
    assert "WantedBy=timers.target" in text
    assert "Description=Lakota Sheet: Open Work Sheet (Mon, Tue, Wed, Thu, Fri at 14:00)" in text


def test_a_timer_with_no_time_zone_configured_still_writes_a_valid_line():
    text = sl.timer_text("view:7", "Weekly summary", "16:00", ["Fri"], "")
    assert "OnCalendar=Fri 16:00\n" in text


def test_bad_days_or_times_never_become_a_unit():
    with pytest.raises(SchedulingError, match="no days"):
        sl.timer_text("open-work", "t", "14:00", [], "America/New_York")
    with pytest.raises(SchedulingError, match="HH:MM"):
        sl.timer_text("open-work", "t", "2pm", ["Mon"], "America/New_York")


def test_the_hand_written_timer_is_named_but_never_generated():
    """Tony's own lakota-print-sheet.timer runs the old print-sheet command. The app reports it
    and refuses to write over it; the unit it writes has a different name."""
    assert sl.LEGACY_TIMERS["open-work"] == "lakota-print-sheet.timer"
    assert sl.timer_unit("open-work") not in sl.LEGACY_TIMERS.values()


def _recorder(results=None):
    """A fake `run` that records argv and answers from a table keyed by the subcommand and its
    arguments (`argv[2:]`, everything after `systemctl --user`) -- not the last two words,
    which would make `enable --now X` and `disable --now X` collide on `("--now", X)`."""
    calls = []
    results = results or {}
    def run(argv, **kw):
        calls.append(argv)
        rc, out = results.get(tuple(argv[2:]), (0, ""))
        return subprocess.CompletedProcess(argv, rc, stdout=out, stderr="")
    return calls, run


def test_install_writes_both_units_and_enables_only_the_timer(tmp_path):
    calls, run = _recorder({("is-enabled", "lakota-print-sheet.timer"): (1, "disabled\n")})
    sl.install("open-work", "14:00", ["Mon", "Fri"], "/venv/bin/lakota-grades", "run open-work", "/home/tony",
               run=run, title="Open Work Sheet", home="/home/tony/.lakota-grades",
               timezone="America/New_York", unit_dir=tmp_path)

    service = (tmp_path / "lakota-open-work.service").read_text()
    timer = (tmp_path / "lakota-open-work.timer").read_text()
    assert "ExecStart=/venv/bin/lakota-grades run open-work" in service
    assert "OnCalendar=Mon,Fri 14:00 America/New_York" in timer

    assert calls == [
        ["systemctl", "--user", "is-enabled", "lakota-print-sheet.timer"],
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", "lakota-open-work.timer"],
    ]


def test_install_refuses_while_the_hand_written_timer_is_enabled(tmp_path):
    """Installing alongside it would print the sheet twice every afternoon. The message names
    the one command that clears the way."""
    calls, run = _recorder({("is-enabled", "lakota-print-sheet.timer"): (0, "enabled\n")})
    with pytest.raises(SchedulingError, match="systemctl --user disable --now lakota-print-sheet.timer"):
        sl.install("open-work", "14:00", ["Mon"], "x", "run open-work", ".", run=run, unit_dir=tmp_path)
    assert not list(tmp_path.iterdir())          # nothing written before the refusal
    assert calls == [["systemctl", "--user", "is-enabled", "lakota-print-sheet.timer"]]


def test_a_report_with_no_legacy_unit_is_not_asked_about(tmp_path):
    calls, run = _recorder()
    sl.install("view:7", "16:00", ["Fri"], "x", "run view:7", ".", run=run, title="Weekly summary",
               home="/h", timezone="", unit_dir=tmp_path)
    assert (tmp_path / "lakota-view-7.timer").is_file() and (tmp_path / "lakota-view-7.service").is_file()
    assert calls[0] == ["systemctl", "--user", "daemon-reload"]


def test_install_with_bad_days_writes_nothing_and_runs_nothing(tmp_path):
    def run(argv, **kw):
        raise AssertionError("systemctl must not run")
    with pytest.raises(SchedulingError):
        sl.install("view:7", "16:00", ["Funday"], "x", "run view:7", ".", run=run, unit_dir=tmp_path)
    assert not list(tmp_path.iterdir())


def test_install_reports_what_systemctl_refused(tmp_path):
    def failing(argv, **kw):
        rc = 1 if argv[2] == "enable" else 0
        return subprocess.CompletedProcess(argv, rc, stdout="", stderr="Failed to connect to bus\n")
    with pytest.raises(SchedulingError, match="Failed to connect to bus"):
        sl.install("view:7", "16:00", ["Fri"], "x", "run view:7", ".", run=failing, unit_dir=tmp_path)


def test_remove_disables_deletes_both_units_and_reloads(tmp_path):
    (tmp_path / "lakota-view-7.timer").write_text(sl.MARKER + "x")
    (tmp_path / "lakota-view-7.service").write_text(sl.MARKER + "x")
    calls, run = _recorder()
    sl.remove("view:7", run=run, unit_dir=tmp_path)
    assert not (tmp_path / "lakota-view-7.timer").exists()
    assert not (tmp_path / "lakota-view-7.service").exists()
    assert calls == [
        ["systemctl", "--user", "disable", "--now", "lakota-view-7.timer"],
        ["systemctl", "--user", "daemon-reload"],
    ]


def test_remove_is_quiet_about_a_unit_that_is_not_there(tmp_path):
    _, run = _recorder()
    def absent(argv, **kw):
        return subprocess.CompletedProcess(argv, 1, stdout="",
                                           stderr="Failed to disable unit: Unit file lakota-view-9.timer does not exist.\n")
    sl.remove("view:9", run=absent, unit_dir=tmp_path)          # no exception


def test_remove_raises_on_anything_else_systemctl_refuses(tmp_path):
    def busted(argv, **kw):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="Failed to connect to bus: No medium found\n")
    with pytest.raises(SchedulingError, match="No medium found"):
        sl.remove("view:9", run=busted, unit_dir=tmp_path)


def test_remove_never_touches_a_hand_written_unit(tmp_path):
    """`remove("open-work")` deletes the app's own units and leaves Tony's alone."""
    (tmp_path / "lakota-print-sheet.timer").write_text("his")
    (tmp_path / "lakota-print-sheet.service").write_text("his")
    calls, run = _recorder({("is-enabled", "lakota-print-sheet.timer"): (1, "disabled\n")})
    sl.remove("open-work", run=run, unit_dir=tmp_path)
    assert (tmp_path / "lakota-print-sheet.timer").read_text() == "his"
    # The legacy timer may be *asked about* (see below); nothing may act on it.
    assert all(c[2] == "is-enabled" or "print-sheet" not in " ".join(c) for c in calls)


def test_remove_refuses_while_the_hand_written_timer_is_enabled(tmp_path):
    """`install` has refused this since the start; `remove` reported a removal it had not
    performed. Both halves of the off switch answer the same way, or the Schedules page says
    "not scheduled" while lakota-print-sheet.timer keeps printing at 2 PM."""
    calls, run = _recorder({("is-enabled", "lakota-print-sheet.timer"): (0, "enabled\n")})
    with pytest.raises(SchedulingError, match="systemctl --user disable --now lakota-print-sheet.timer"):
        sl.remove("open-work", run=run, unit_dir=tmp_path)
    assert calls == [["systemctl", "--user", "is-enabled", "lakota-print-sheet.timer"]]


def _forbidden_run(argv, **kw):
    raise AssertionError("systemctl must not run")


def test_install_and_remove_refuse_a_key_that_renders_to_a_hand_written_unit_name(tmp_path):
    """A report key is caller-supplied and unconstrained -- `safe_key("print-sheet") ==
    "print-sheet"` -- so a guard keyed on the report key (`LEGACY_TIMERS.get(key)`) would miss
    this. `_check_ownership`'s name check does not, and neither call ever reaches `run`."""
    service, timer = tmp_path / "lakota-print-sheet.service", tmp_path / "lakota-print-sheet.timer"
    service.write_text("his service\n")
    timer.write_text("his timer\n")
    run = _forbidden_run

    with pytest.raises(SchedulingError):
        sl.install("print-sheet", "14:00", ["Mon"], "x", "run print-sheet", ".", run=run, unit_dir=tmp_path)
    with pytest.raises(SchedulingError):
        sl.remove("print-sheet", run=run, unit_dir=tmp_path)

    assert service.read_text() == "his service\n"
    assert timer.read_text() == "his timer\n"


def test_install_and_remove_refuse_the_grades_refresh_pair(tmp_path):
    """`lakota-grades-refresh.{service,timer}` is hand-written and live, same as the print
    sheet timer, even though no report key normally produces this name."""
    run = _forbidden_run
    with pytest.raises(SchedulingError):
        sl.install("grades-refresh", "14:00", ["Mon"], "x", "run grades-refresh", ".", run=run, unit_dir=tmp_path)
    with pytest.raises(SchedulingError):
        sl.remove("grades-refresh", run=run, unit_dir=tmp_path)
    assert not list(tmp_path.iterdir())


def test_install_and_remove_refuse_the_web_servers_own_unit_by_name(tmp_path):
    """`service_linux.UNIT_FILE` ("lakota-web.service") is the always-on server's own unit,
    installed separately by `service install`. A report key of "web" renders to exactly that
    name (`service_unit("web") == service_linux.UNIT_FILE`), and refusing it must not depend
    on a marker already being on disk -- an empty `unit_dir` (a fresh systemd directory, or
    just this test's tmp_path) would let `_ours_pair` wave it through as "nothing here yet,
    free to take", the same gap Windows already closed for its own logon task by importing
    `service_windows.NAME` instead of trusting the marker check alone (#36)."""
    assert sl.service_unit("web") == service_linux.UNIT_FILE
    run = _forbidden_run

    with pytest.raises(SchedulingError, match="refusing"):
        sl.install("web", "14:00", ["Mon"], "x", "run web", ".", run=run, unit_dir=tmp_path)
    with pytest.raises(SchedulingError, match="refusing"):
        sl.remove("web", run=run, unit_dir=tmp_path)

    assert not list(tmp_path.iterdir())          # nothing written before the refusal


def test_install_and_remove_refuse_a_foreign_unit_not_on_any_list(tmp_path):
    """A blocklist only protects the names someone thought to list. A hand-written unit under
    any other name is still not this app's to touch -- caught here by the marker, not by
    name, which is the whole reason the marker exists."""
    timer = tmp_path / "lakota-weekly.timer"
    timer.write_text("his weekly timer\n")
    run = _forbidden_run

    with pytest.raises(SchedulingError):
        sl.install("weekly", "14:00", ["Mon"], "x", "run weekly", ".", run=run, unit_dir=tmp_path)
    with pytest.raises(SchedulingError):
        sl.remove("weekly", run=run, unit_dir=tmp_path)

    assert timer.read_text() == "his weekly timer\n"


def test_a_unit_the_app_wrote_round_trips(tmp_path):
    """The marker that makes `remove` refuse a hand-written unit does not get in its own way:
    installing and then removing the app's own unit leaves nothing behind."""
    calls, run = _recorder()
    sl.install("weekly", "14:00", ["Mon"], "x", "run weekly", ".", run=run, unit_dir=tmp_path)
    assert (tmp_path / "lakota-weekly.timer").is_file() and (tmp_path / "lakota-weekly.service").is_file()

    sl.remove("weekly", run=run, unit_dir=tmp_path)
    assert not list(tmp_path.iterdir())


def test_ownership_check_refuses_a_hand_written_unit_that_is_not_utf8(tmp_path):
    """`_ours` reads the file back looking for `MARKER`. Bytes that are not valid UTF-8 raise
    `UnicodeDecodeError`, a `ValueError`, not the `OSError` the old `except` clause caught --
    which used to escape `_check_ownership` as an unhandled exception instead of the refusal
    every other unreadable hand-written unit gets. `web/schedules.py` (a later task) catches
    only `SchedulingError`, so an uncaught `UnicodeDecodeError` here would show up as a 500
    on the Schedules page instead of the normal refusal message."""
    (tmp_path / "lakota-weekly.timer").write_bytes(b"\xff\xfe not valid utf-8")
    with pytest.raises(SchedulingError):
        sl.install("weekly", "14:00", ["Mon"], "x", "run weekly", ".", run=_forbidden_run, unit_dir=tmp_path)
    with pytest.raises(SchedulingError):
        sl.remove("weekly", run=_forbidden_run, unit_dir=tmp_path)


def _systemctl_fake(answers):
    """answers maps a (verb, unit) pair to (returncode, stdout)."""
    calls = []
    def run(argv, **kw):
        calls.append(argv)
        rc, out = answers.get((argv[2], argv[-1] if argv[2] == "is-enabled" else argv[3]), (1, ""))
        return subprocess.CompletedProcess(argv, rc, stdout=out, stderr="")
    return calls, run


def test_describe_reports_the_apps_own_timer(tmp_path):
    calls, run = _systemctl_fake({
        ("is-enabled", "lakota-view-7.timer"): (0, "enabled\n"),
        ("show", "lakota-view-7.timer"): (0, "Fri 2026-09-18 16:00:00 EDT\n"),
    })
    info = sl.describe("view:7", run=run, unit_dir=tmp_path)
    assert info == ScheduleInfo("systemd", True, "Fri 2026-09-18 16:00:00 EDT", None, True)


def test_describe_falls_back_to_the_hand_written_timer_and_marks_it_unmanageable(tmp_path):
    """Tony's lakota-print-sheet.timer is what actually prints his sheet. Reporting "not
    scheduled" because the app did not write it would be a lie his doctor output would repeat."""
    _, run = _systemctl_fake({
        ("is-enabled", "lakota-open-work.timer"): (1, ""),
        ("is-enabled", "lakota-print-sheet.timer"): (0, "enabled\n"),
        ("show", "lakota-print-sheet.timer"): (0, "Wed 2026-09-16 14:00:00 EDT\n"),
    })
    info = sl.describe("open-work", run=run, unit_dir=tmp_path)
    assert info.installed is True and info.manageable is False
    assert info.managed_by == "systemd (hand-written)"
    assert info.next_run == "Wed 2026-09-16 14:00:00 EDT"


def test_the_apps_own_timer_wins_over_a_legacy_one(tmp_path):
    _, run = _systemctl_fake({
        ("is-enabled", "lakota-open-work.timer"): (0, "enabled\n"),
        ("show", "lakota-open-work.timer"): (0, "Wed 2026-09-16 14:00:00 EDT\n"),
        ("is-enabled", "lakota-print-sheet.timer"): (0, "enabled\n"),
    })
    assert sl.describe("open-work", run=run, unit_dir=tmp_path).manageable is True


def test_describe_says_not_scheduled_when_nothing_is_installed(tmp_path):
    _, run = _systemctl_fake({})
    assert sl.describe("open-work", run=run, unit_dir=tmp_path) == ScheduleInfo("systemd", False, None, None, True)


def test_describe_survives_a_machine_with_no_systemctl(tmp_path):
    def missing(argv, **kw):
        raise FileNotFoundError("systemctl")
    assert sl.describe("view:7", run=missing, unit_dir=tmp_path) == ScheduleInfo("systemd", False, None, None, True)


def test_install_and_remove_name_a_systemctl_that_is_missing_or_hangs(tmp_path):
    """`_is_enabled` and `_next_elapse` have caught these two since the start; `install` and
    `remove` called `_systemctl` bare. `web/schedules.py` catches only NotSupported and
    SchedulingError, so on a Linux host with no systemctl on PATH GET /schedules rendered
    (describe guards it) while POST /schedules was a 500."""
    def missing(argv, **kw):
        raise FileNotFoundError(2, "No such file or directory", "systemctl")

    with pytest.raises(SchedulingError, match="systemctl"):
        sl.install("view:7", "16:00", ["Fri"], "x", "run view:7", ".", run=missing, unit_dir=tmp_path)
    with pytest.raises(SchedulingError, match="systemctl"):
        sl.remove("view:7", run=missing, unit_dir=tmp_path)

    def hangs(argv, **kw):
        raise subprocess.TimeoutExpired(argv, 60)

    with pytest.raises(SchedulingError, match="timed out"):
        sl.install("view:7", "16:00", ["Fri"], "x", "run view:7", ".", run=hangs, unit_dir=tmp_path)
    with pytest.raises(SchedulingError, match="timed out"):
        sl.remove("view:7", run=hangs, unit_dir=tmp_path)


def test_describe_reports_a_hand_written_unit_sitting_in_the_apps_own_namespace(tmp_path):
    """A unit file already sits at the exact name this app would write for "weekly"
    (`lakota-weekly.timer`) but was not written by this app -- the same setup as
    `test_install_and_remove_refuse_a_foreign_unit_not_on_any_list`, where `install`/`remove`
    both refuse it via `_check_ownership`. `describe` must agree, or the Schedules page (Task
    8) offers Save/Remove buttons for a unit the host then refuses."""
    (tmp_path / "lakota-weekly.timer").write_text("his own hand-written timer\n")
    _, run = _systemctl_fake({
        ("is-enabled", "lakota-weekly.timer"): (0, "enabled\n"),
        ("show", "lakota-weekly.timer"): (0, "Wed 2026-09-16 14:00:00 EDT\n"),
    })
    info = sl.describe("weekly", run=run, unit_dir=tmp_path)
    assert info == ScheduleInfo("systemd (hand-written)", True, "Wed 2026-09-16 14:00:00 EDT", None, False)


def test_describe_reports_the_hand_written_own_namespace_unit_even_when_not_enabled(tmp_path):
    """Resolves the ordering question between the two signals `describe` now has for the
    app's own-namespace unit: `_is_enabled` asks systemd, `_ours` reads the file at
    `unit_dir`, and they can disagree. `_check_ownership` -- what `install`/`remove` actually
    obey -- refuses this unit by reading the file, regardless of whether systemd currently has
    it enabled. So `describe` must trust `_ours`, not `is-enabled`, to decide this unit is
    installed-but-foreign: a disabled namesake still blocks this app from writing here."""
    (tmp_path / "lakota-weekly.timer").write_text("his own hand-written timer\n")
    _, run = _systemctl_fake({})          # is-enabled defaults to (1, "") -- disabled
    info = sl.describe("weekly", run=run, unit_dir=tmp_path)
    assert info.installed is True and info.manageable is False
    assert info.managed_by == "systemd (hand-written)"


def test_describe_and_ownership_agree_on_a_mismatched_pair(tmp_path):
    """A pair where only the `.service` half lost its marker -- e.g. a parent hand-edits
    `lakota-weekly.service` and the edit drops line 1, while `lakota-weekly.timer` is
    untouched and still carries `MARKER`. `_check_ownership` refuses this (it checks both
    halves); `describe` must refuse to call it manageable too, or the Schedules page would
    offer Save/Remove for a pair the host then rejects. Checking `describe` and
    `install`/`remove` against the *same* fixture is the point: the two answers must agree."""
    (tmp_path / "lakota-weekly.timer").write_text(sl.MARKER + "still ours\n")
    (tmp_path / "lakota-weekly.service").write_text("hand-edited, marker gone\n")
    _, run = _systemctl_fake({
        ("is-enabled", "lakota-weekly.timer"): (0, "enabled\n"),
        ("show", "lakota-weekly.timer"): (0, "Wed 2026-09-16 14:00:00 EDT\n"),
    })
    info = sl.describe("weekly", run=run, unit_dir=tmp_path)
    assert info.manageable is False
    assert info.managed_by == "systemd (hand-written)"

    with pytest.raises(SchedulingError):
        sl.install("weekly", "14:00", ["Mon"], "x", "run weekly", ".", run=_forbidden_run, unit_dir=tmp_path)
    with pytest.raises(SchedulingError):
        sl.remove("weekly", run=_forbidden_run, unit_dir=tmp_path)
