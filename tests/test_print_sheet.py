"""The print-sheet command: guards (skip list, already printed, time window), refresh
and staleness, build, print, record. Refresh and lp are injected so nothing here
touches the network or CUPS."""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("reportlab")

from lakota_grades import print_sheet  # noqa: E402
from lakota_grades.config import Settings  # noqa: E402
from tests.conftest import needs_pdftotext  # noqa: E402

TZ = ZoneInfo("America/New_York")
FRI_2PM = datetime(2026, 9, 11, 14, 5, tzinfo=TZ)


def test_parse_skip_days_handles_comments_ranges_and_blank_lines():
    text = "# comment\n2026-11-26 Thanksgiving\n\n2026-12-21..2026-12-23  Holiday break\n2027-01-18\nnot a date\n"
    days = print_sheet.parse_skip_days(text)
    assert days[date(2026, 11, 26)] == "Thanksgiving"
    assert days[date(2026, 12, 22)] == "Holiday break"
    assert days[date(2027, 1, 18)] == ""
    assert date(2026, 12, 24) not in days and len(days) == 5


def _snapshot(fetched: datetime, stale: dict | None = None) -> dict:
    a = {"id": 1, "name": "WS 1", "due_at": (FRI_2PM + timedelta(days=2)).isoformat(), "unlock_at": None, "created_at": None,
         "points_possible": 10.0, "submission_types": ["online_upload"], "group": "Homework", "published": True, "score": None,
         "grade": None, "state": "unsubmitted", "late": False, "missing": False, "excused": False}
    return {
        "fetched_at": fetched.isoformat(), "fetched_at_epoch": fetched.timestamp(),
        "sources": {"canvas": "ok" if not stale else "login_required: x", "hac": "ok"}, "stale": stale or {},
        "students": {
            "Alex": {"name": "Alex Example", "canvas": {"courses": [{"id": 5, "name": "Honors Biology S1-2027-Nance", "assignments": [a]}]}, "hac": {"classes": []}},
            "Sam": {"name": "Sam Example", "canvas": {"courses": []}, "hac": {"classes": []}},
        },
    }


@pytest.fixture
def env(tmp_path):
    s = Settings(home=tmp_path)
    s.nicknames = {"Alex": "Al"}
    s.cache_dir.mkdir(parents=True)
    (s.cache_dir / "snapshot.json").write_text(json.dumps(_snapshot(FRI_2PM - timedelta(hours=1))))
    calls = {"refresh": 0, "lp": []}

    def refresh_ok(settings, **kw):
        calls["refresh"] += 1
        snap = _snapshot(FRI_2PM)
        (settings.cache_dir / "snapshot.json").write_text(json.dumps(snap))
        return snap

    def lp(cmd, **kw):
        calls["lp"].append(cmd)
        class R:
            returncode, stdout, stderr = 0, "request id is Brother_MFC_J4335DW-42 (1 file(s))\n", ""
        return R()

    return s, calls, refresh_ok, lp


def _args(**over):
    d = dict(dry_run=False, kid=None, date=None, days=14, overdue_days=14, force=False, printer="Brother_MFC_J4335DW", no_refresh=False)
    d.update(over)
    return print_sheet.Options(**d)


def test_happy_path_prints_records_and_logs(env):
    s, calls, refresh, lp = env
    rc = print_sheet.run(_args(), s, now=FRI_2PM, refresh=refresh, lp=lp)
    assert rc == 0 and calls["refresh"] == 1
    day = s.home / "sheets" / "2026-09-11"
    assert (day / "sheet.pdf").is_file() and (day / "rows.json").is_file()
    assert "Brother_MFC_J4335DW-42" in (day / "printed.txt").read_text()
    (cmd,) = calls["lp"]
    assert cmd[:3] == ["lp", "-d", "Brother_MFC_J4335DW"] and "sides=two-sided-long-edge" in cmd
    log = (s.home / "print-sheet.log").read_text().strip().splitlines()
    # the refresh is ingested into the database first (INFO), then the print is logged (OK).
    assert len(log) == 2 and "INFO" in log[0] and "ingested" in log[0]
    assert " OK " in log[1] and "Al=1" in log[1]


def test_dry_run_builds_but_neither_prints_nor_records(env):
    s, calls, refresh, lp = env
    assert print_sheet.run(_args(dry_run=True), s, now=FRI_2PM, refresh=refresh, lp=lp) == 0
    day = s.home / "sheets" / "2026-09-11"
    assert (day / "sheet.pdf").is_file() and not (day / "printed.txt").exists() and calls["lp"] == []


def test_skip_list_is_honoured_and_force_overrides(env):
    s, calls, refresh, lp = env
    (s.home / "no-print-days.txt").write_text("2026-09-11 Test day\n")
    assert print_sheet.run(_args(), s, now=FRI_2PM, refresh=refresh, lp=lp) == 0
    assert calls["lp"] == [] and calls["refresh"] == 0
    assert "skip" in (s.home / "print-sheet.log").read_text().lower()
    assert print_sheet.run(_args(force=True), s, now=FRI_2PM, refresh=refresh, lp=lp) == 0
    assert len(calls["lp"]) == 1


def test_same_day_is_never_printed_twice_even_with_force(env):
    s, calls, refresh, lp = env
    assert print_sheet.run(_args(), s, now=FRI_2PM, refresh=refresh, lp=lp) == 0
    assert print_sheet.run(_args(force=True), s, now=FRI_2PM + timedelta(hours=1), refresh=refresh, lp=lp) == 0
    assert len(calls["lp"]) == 1
    assert "already printed" in (s.home / "print-sheet.log").read_text()


def test_catch_up_run_before_two_pm_does_not_print(env):
    s, calls, refresh, lp = env
    nine_am = FRI_2PM.replace(hour=9)
    assert print_sheet.run(_args(), s, now=nine_am, refresh=refresh, lp=lp) == 0
    assert calls["lp"] == [] and "window" in (s.home / "print-sheet.log").read_text()
    assert print_sheet.run(_args(force=True), s, now=nine_am, refresh=refresh, lp=lp) == 0
    assert len(calls["lp"]) == 1


@needs_pdftotext
def test_failed_refresh_with_fresh_snapshot_prints_with_a_footer_note(env):
    s, calls, _, lp = env

    def refresh_fail(settings, **kw):
        raise RuntimeError("browser exploded")

    assert print_sheet.run(_args(), s, now=FRI_2PM, refresh=refresh_fail, lp=lp) == 0
    assert len(calls["lp"]) == 1
    from lakota_grades import sheet
    assert "refresh failed" in sheet.pdf_text(s.home / "sheets" / "2026-09-11" / "sheet.pdf")


def test_failed_refresh_with_stale_snapshot_prints_nothing_and_exits_nonzero(env):
    s, calls, _, lp = env
    old = FRI_2PM - timedelta(hours=30)
    (s.cache_dir / "snapshot.json").write_text(json.dumps(_snapshot(old)))

    def refresh_fail(settings, **kw):
        raise RuntimeError("browser exploded")

    assert print_sheet.run(_args(), s, now=FRI_2PM, refresh=refresh_fail, lp=lp) == 1
    assert calls["lp"] == [] and not (s.home / "sheets" / "2026-09-11").exists()
    log = (s.home / "print-sheet.log").read_text()
    assert "stale" in log.lower() and "browser exploded" in log


def test_stale_source_inside_a_successful_write_counts_as_data_age(env):
    """collect() writes a new snapshot even when a source failed; the carried-forward
    source's own fetch time is the data age, not the file's."""
    s, calls, _, lp = env
    old = FRI_2PM - timedelta(hours=30)

    def refresh_partial(settings, **kw):
        snap = _snapshot(FRI_2PM, stale={"canvas": {"fetched_at": old.isoformat(), "fetched_at_epoch": old.timestamp(), "reason": "login_required"}})
        (settings.cache_dir / "snapshot.json").write_text(json.dumps(snap))
        return snap

    assert print_sheet.run(_args(), s, now=FRI_2PM, refresh=refresh_partial, lp=lp) == 1
    assert calls["lp"] == []


def test_kid_filter_and_explicit_date(env):
    s, calls, refresh, lp = env
    rc = print_sheet.run(_args(dry_run=True, kid="al", date="2026-09-09"), s, now=FRI_2PM, refresh=refresh, lp=lp)
    assert rc == 0
    rows = json.loads((s.home / "sheets" / "2026-09-09" / "rows.json").read_text())
    assert set(rows) == {"Alex"}


@needs_pdftotext
def test_second_run_diffs_against_the_previous_sheet(env):
    s, calls, refresh, lp = env
    assert print_sheet.run(_args(dry_run=True, date="2026-09-10"), s, now=FRI_2PM, refresh=refresh, lp=lp) == 0
    assert print_sheet.run(_args(), s, now=FRI_2PM, refresh=refresh, lp=lp) == 0
    from lakota_grades import sheet
    text = sheet.pdf_text(s.home / "sheets" / "2026-09-11" / "sheet.pdf")
    assert "0 new" in text and "since last sheet" in text


def test_cli_maps_flags_to_options(monkeypatch, tmp_path):
    from lakota_grades import cli
    seen = {}

    def fake_run(opts, settings, **kw):
        seen["opts"] = opts
        return 0

    monkeypatch.setattr(print_sheet, "run", fake_run)
    monkeypatch.setattr(cli, "load_settings", lambda: Settings(home=tmp_path))
    with pytest.raises(SystemExit) as e:
        cli.main(["print-sheet", "--dry-run", "--kid", "Al", "--date", "2026-09-09", "--days", "7", "--overdue-days", "5", "--force", "--printer", "X", "--no-refresh", "--reprint"])
    assert e.value.code == 0
    assert seen["opts"] == print_sheet.Options(dry_run=True, kid="Al", date="2026-09-09", days=7, overdue_days=5, force=True, printer="X", no_refresh=True, reprint=True)


def test_reprint_flag_prints_an_already_printed_day_again(env):
    """A deliberate second print from the desktop shortcut. --reprint is separate from
    --force so that the timer's retries and a reflexive --force still cannot double-print."""
    s, calls, refresh, lp = env
    assert print_sheet.run(_args(), s, now=FRI_2PM, refresh=refresh, lp=lp) == 0
    assert print_sheet.run(_args(reprint=True), s, now=FRI_2PM + timedelta(hours=1), refresh=refresh, lp=lp) == 0
    assert len(calls["lp"]) == 2
    assert (s.home / "sheets" / "2026-09-11" / "printed.txt").read_text().count("\n") == 2  # both runs recorded


def test_pdf_is_also_saved_to_the_archive_folder_by_school_year(env):
    """The hidden ~/.lakota-grades/sheets/ tree is for the machine; people look in Drive."""
    s, calls, refresh, lp = env
    s.sheets_archive = str(s.home / "drive" / "Open Work Sheets")
    assert print_sheet.run(_args(dry_run=True), s, now=FRI_2PM, refresh=refresh, lp=lp) == 0
    saved = s.home / "drive" / "Open Work Sheets" / "2026-27" / "2026-09-11 Open Work.pdf"
    assert saved.is_file() and saved.read_bytes()[:4] == b"%PDF"
    assert f"saved={saved}" in (s.home / "print-sheet.log").read_text()


def test_unreachable_archive_is_a_warning_not_a_failure(env):
    s, calls, refresh, lp = env
    (s.home / "blocker").write_text("a file where a directory should be")
    s.sheets_archive = str(s.home / "blocker" / "sheets")
    assert print_sheet.run(_args(), s, now=FRI_2PM, refresh=refresh, lp=lp) == 0
    assert len(calls["lp"]) == 1
    log = (s.home / "print-sheet.log").read_text()
    assert "WARN" in log and "archive" in log.lower()


def test_school_year_label():
    assert print_sheet.school_year(date(2026, 9, 11)) == "2026-27"
    assert print_sheet.school_year(date(2027, 3, 1)) == "2026-27"
    assert print_sheet.school_year(date(2027, 8, 20)) == "2027-28"
