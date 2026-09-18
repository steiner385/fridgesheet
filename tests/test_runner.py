"""The generic runner, with the open-work report but fake refresh, printer and notifier.
The behavioural guards are covered by tests/test_print_sheet.py through the alias; this
file covers what is new: the lock, the configured window time, PrintError, toasts, and a
windowed process with no stderr."""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("reportlab")

from fridgesheet import runner  # noqa: E402
from fridgesheet.config import ReportConfig, Settings  # noqa: E402
from fridgesheet.host.printing import PrintError  # noqa: E402
from tests.test_reports import _snapshot  # noqa: E402

TZ = ZoneInfo("America/New_York")
FRI_2PM = datetime(2026, 9, 11, 14, 5, tzinfo=TZ)


@pytest.fixture
def env(tmp_path):
    s = Settings(home=tmp_path, nicknames={"Alex": "Al"})
    s.cache_dir.mkdir(parents=True)
    (s.cache_dir / "snapshot.json").write_text(json.dumps(_snapshot()))
    calls = {"print": [], "toast": []}

    def print_pdf(pdf, printer, title):
        calls["print"].append((pdf, printer, title))
        return "job-1"

    def toast(title, body):
        calls["toast"].append((title, body))

    def refresh(settings, **kw):
        return _snapshot()

    return s, calls, refresh, print_pdf, toast


def _run(s, opts, **kw):
    return runner.run("open-work", opts, s, now=kw.pop("now", FRI_2PM), **kw)


def test_archive_copy_never_writes_outside_the_archive_root(tmp_path):
    """A report's `archive_name()` is not trusted whole -- the `Report` protocol lets any
    future implementation return any string, so this is the last gate before the filesystem.
    A name with a directory part in it is reduced to its last component (still inside the
    archive root); a name that is empty or `.`/`..` after that is refused outright rather
    than copied anywhere. The reduction uses Windows separator rules on every platform, so
    the backslash and drive forms below answer the same here as they do on Windows."""
    archive = tmp_path / "archive"
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    day = date(2026, 9, 16)

    for bad in ("..", ".", "", "sub/..", "C:"):
        assert runner.archive_copy(pdf, str(archive), day, bad) is None
    assert not any(archive.rglob("*"))    # every refusal above copied nothing at all

    for reduced in ("../../../../tmp/fridgesheet-escaped Report.pdf", "sub/dir.pdf", "sub\\dir.pdf",
                    "C:evil.pdf", "\\\\server\\share\\evil.pdf"):
        dest = runner.archive_copy(pdf, str(archive), day, reduced)
        assert dest is not None and dest.is_file() and dest.resolve().is_relative_to(archive.resolve())

    dest = runner.archive_copy(pdf, str(archive), day, "2026-09-16 Weekly summary.pdf")
    assert dest is not None and dest.is_file() and dest.resolve().is_relative_to(archive.resolve())


def test_a_name_the_filesystem_cannot_take_is_a_warning_not_a_crash(env, monkeypatch):
    """`shutil.copyfile` raises `ValueError`, not `OSError`, on a name carrying a raw NUL byte --
    and a view report's `archive_name` is built from the parent's own text. The archive copy is
    a courtesy, so the run warns and still prints instead of failing on it."""
    from fridgesheet import reports as registry
    s, calls, refresh, print_pdf, toast = env
    s.sheets_archive = str(s.home / "archive")
    real = registry.REPORTS["open-work"]

    class Hostile:
        key, title, output_dir, default_time = real.key, real.title, real.output_dir, real.default_time

        def archive_name(self, day: date) -> str:
            return f"{day.isoformat()} bad\x00name.pdf"

        def build(self, snap, ctx):
            return real.build(snap, ctx)

    monkeypatch.setitem(registry.REPORTS, "open-work", Hostile())
    assert _run(s, runner.RunOptions(), refresh=refresh, print_pdf=print_pdf, toast=toast) == 0
    log = (s.home / runner.LOG_NAME).read_text()
    assert "WARN" in log and "could not copy the sheet to the archive" in log
    assert calls["print"] and " OK " in log          # the sheet itself still printed


def test_prints_toasts_and_records(env):
    s, calls, refresh, print_pdf, toast = env
    assert _run(s, runner.RunOptions(printer="Office"), refresh=refresh, print_pdf=print_pdf, toast=toast) == 0
    (pdf, printer, title) = calls["print"][0]
    assert printer == "Office" and pdf == s.home / "sheets" / "2026-09-11" / "sheet.pdf" and "2026-09-11" in title
    assert "job-1" in (s.home / "sheets" / "2026-09-11" / "printed.txt").read_text()
    assert calls["toast"] == [("Open Work Sheet", "Printed Fri 9/11: 1p Al=1 Sam=0 data=9/11 14:05")]
    log = (s.home / runner.LOG_NAME).read_text()
    assert " OK " in log and "open-work" in log


def test_printer_falls_back_to_settings_then_none(env):
    s, calls, refresh, print_pdf, toast = env
    s.printer = "FromConfig"
    _run(s, runner.RunOptions(), refresh=refresh, print_pdf=print_pdf, toast=toast)
    assert calls["print"][0][1] == "FromConfig"
    s.printer = ""
    _run(s, runner.RunOptions(reprint=True), refresh=refresh, print_pdf=print_pdf, toast=toast)
    assert calls["print"][1][1] is None


def test_a_reports_own_printer_beats_the_shared_one(env):
    """Precedence: --printer, then the report's own, then [print].printer, then the default.
    The middle one is new: a schedule that prints somewhere else does not make every other
    report print there too."""
    s, calls, refresh, print_pdf, toast = env
    s.printer = "FromConfig"
    s.reports["open-work"] = ReportConfig(enabled=True, printer="Brother")
    _run(s, runner.RunOptions(), refresh=refresh, print_pdf=print_pdf, toast=toast)
    assert calls["print"][0][1] == "Brother"


def test_the_command_line_still_beats_the_reports_own_printer(env):
    s, calls, refresh, print_pdf, toast = env
    s.reports["open-work"] = ReportConfig(enabled=True, printer="Brother")
    _run(s, runner.RunOptions(printer="Office"), refresh=refresh, print_pdf=print_pdf, toast=toast)
    assert calls["print"][0][1] == "Office"


def test_a_pdf_only_report_builds_and_archives_but_never_prints(env):
    """PDF-only is a report's own setting, not `--dry-run`: a dry run also switches off the
    print-window and already-printed guards, and a scheduled PDF-only run wants both.

    The test name has claimed "archives" since before this assertion existed; with
    `sheets_archive` configured, `runner.run` must actually copy the PDF there
    (`archive_copy`, covered on its own in `test_archive_copy_never_writes_outside_the_archive_root`)
    -- not merely build the sheet under `sheets/`."""
    s, calls, refresh, print_pdf, toast = env
    s.sheets_archive = str(s.home / "archive")
    s.reports["open-work"] = ReportConfig(enabled=True, prints=False)
    assert _run(s, runner.RunOptions(), refresh=refresh, print_pdf=print_pdf, toast=toast) == 0
    assert calls["print"] == []
    day_dir = s.home / "sheets" / "2026-09-11"
    assert (day_dir / "sheet.pdf").is_file() and (day_dir / "rows.json").is_file()
    assert not (day_dir / "printed.txt").exists()      # nothing printed, so nothing recorded as printed
    archived = s.home / "archive" / runner.school_year(FRI_2PM.date()) / "2026-09-11 Open Work.pdf"
    assert archived.is_file()
    log = (s.home / runner.LOG_NAME).read_text()
    assert " OK " in log and "PDF only" in log
    (title, body), = calls["toast"]
    assert title == "Open Work Sheet"
    assert body.startswith("Built (not printed) Fri 9/11: 1p Al=1 Sam=0 data=9/11 14:05")
    assert f"saved={archived}" in body


def test_an_interactive_print_beats_the_reports_pdf_only_setting(env):
    """"Print now" on the Reports page is a parent standing at the printer asking for paper.
    Every other guard in this runner yields to something -- the skip list to --force,
    already-printed to --reprint, the window to --force/--date -- and this one had no
    override at all, so the button built a PDF, printed nothing, and recorded the job OK."""
    s, calls, refresh, print_pdf, toast = env
    s.reports["open-work"] = ReportConfig(enabled=True, prints=False, printer="Brother")
    rc = _run(s, runner.RunOptions(force=True, reprint=True, force_print=True, trigger="web"),
              refresh=refresh, print_pdf=print_pdf, toast=toast)
    assert rc == 0 and [p[1] for p in calls["print"]] == ["Brother"]
    assert (s.home / "sheets" / "2026-09-11" / "printed.txt").is_file()
    assert "PDF only" not in (s.home / runner.LOG_NAME).read_text()


def test_a_pdf_only_run_still_obeys_the_print_window(env):
    """The guard that stops a catch-up the next morning from standing in for yesterday's run
    applies whether or not the result reaches a printer."""
    s, calls, refresh, print_pdf, toast = env
    s.reports["open-work"] = ReportConfig(enabled=True, time="14:00", prints=False)
    rc = _run(s, runner.RunOptions(), now=FRI_2PM.replace(hour=9),
              refresh=refresh, print_pdf=print_pdf, toast=toast)
    assert rc == 0 and calls["print"] == []
    assert "outside print window" in (s.home / runner.LOG_NAME).read_text()


def test_print_error_is_a_fail_with_toast_and_pdf_kept(env):
    s, calls, refresh, _, toast = env

    def bad(pdf, printer, title):
        raise PrintError("printer 'Gone' is not installed")

    assert _run(s, runner.RunOptions(), refresh=refresh, print_pdf=bad, toast=toast) == 1
    assert (s.home / "sheets" / "2026-09-11" / "sheet.pdf").is_file()
    assert not (s.home / "sheets" / "2026-09-11" / "printed.txt").exists()
    assert calls["toast"][0][1].startswith("Not printed: printer 'Gone'")
    assert "FAIL" in (s.home / runner.LOG_NAME).read_text()


def test_login_failure_toast_tells_them_where_to_look(env):
    s, calls, _, print_pdf, toast = env
    old = FRI_2PM - timedelta(hours=30)
    snap = _snapshot()
    snap["fetched_at_epoch"] = old.timestamp()
    (s.cache_dir / "snapshot.json").write_text(json.dumps(snap))

    def refresh(settings, **kw):
        raise RuntimeError("LoginRequired: OneLogin did not redirect")

    assert _run(s, runner.RunOptions(), refresh=refresh, print_pdf=print_pdf, toast=toast) == 1
    assert "check your password" in calls["toast"][0][1]


def test_dry_run_and_notify_off_never_toast(env):
    s, calls, refresh, print_pdf, toast = env
    _run(s, runner.RunOptions(dry_run=True), refresh=refresh, print_pdf=print_pdf, toast=toast)
    _run(s, runner.RunOptions(notify=False), refresh=refresh, print_pdf=print_pdf, toast=toast)
    assert calls["toast"] == [] and len(calls["print"]) == 1


def test_skip_reasons_are_toasted(env):
    s, calls, refresh, print_pdf, toast = env
    _run(s, runner.RunOptions(), now=FRI_2PM.replace(hour=9), refresh=refresh, print_pdf=print_pdf, toast=toast)
    assert calls["toast"][0][1].startswith("Skipped: outside print window")


def test_window_uses_the_configured_report_time(env):
    s, calls, refresh, print_pdf, toast = env
    s.reports["open-work"] = ReportConfig(enabled=True, time="18:00")
    _run(s, runner.RunOptions(), refresh=refresh, print_pdf=print_pdf, toast=toast)      # 14:05 < 18:00
    assert calls["print"] == [] and "before 18:00" in (s.home / runner.LOG_NAME).read_text()
    _run(s, runner.RunOptions(), now=FRI_2PM.replace(hour=18, minute=1), refresh=refresh, print_pdf=print_pdf, toast=toast)
    assert len(calls["print"]) == 1


def test_config_options_feed_the_report_and_cli_overrides_win(env):
    s, calls, refresh, print_pdf, toast = env
    s.reports["open-work"] = ReportConfig(options={"days_ahead": 1})
    _run(s, runner.RunOptions(dry_run=True), refresh=refresh, print_pdf=print_pdf, toast=toast)
    assert json.loads((s.home / "sheets" / "2026-09-11" / "rows.json").read_text())["Alex"] == []
    _run(s, runner.RunOptions(dry_run=True, options={"days_ahead": 14, "overdue_days": None}), refresh=refresh, print_pdf=print_pdf, toast=toast)
    assert len(json.loads((s.home / "sheets" / "2026-09-11" / "rows.json").read_text())["Alex"]) == 1


def test_lock_file_prevents_overlap_and_a_stale_lock_is_ignored(env):
    from fridgesheet.web import db
    s, calls, refresh, print_pdf, toast = env
    lock = s.home / runner.LOCK_NAME
    lock.write_text(str(os.getpid()))
    assert _run(s, runner.RunOptions(), refresh=refresh, print_pdf=print_pdf, toast=toast) == 0
    assert calls["print"] == [] and "already running" in (s.home / runner.LOG_NAME).read_text()
    os.utime(lock, (time.time() - 3600, time.time() - 3600))
    assert _run(s, runner.RunOptions(), refresh=refresh, print_pdf=print_pdf, toast=toast) == 0
    assert len(calls["print"]) == 1 and not lock.exists()
    conn = db.open_db(s.home)                            # every run is on record, the skipped one too
    runs = conn.execute("SELECT outcome, message FROM runs ORDER BY id").fetchall()
    assert [r["outcome"] for r in runs] == ["SKIP", "OK"] and "already running" in runs[0]["message"]
    conn.close()


def test_a_stale_takeover_cannot_have_its_lock_deleted_by_the_job_it_displaced(tmp_path):
    """`acquire` deletes a lock older than LOCK_STALE_SECONDS, so a long-hung job's lock is
    taken over while that job still believes it holds it. Its `release()` must then not unlink
    the lock now held by someone else -- that is what lets two runs print at once."""
    path = tmp_path / "run.lock"
    first = runner.Lock(path)
    assert first.acquire()
    os.utime(path, (0, 0))                      # age it past the stale threshold
    second = runner.Lock(path)
    assert second.acquire()                     # the takeover this test is about
    first.release()                             # the displaced job, finishing late
    assert path.is_file(), "the displaced job deleted the live job's lock"
    second.release()
    assert not path.is_file()


def test_log_survives_a_windowed_process_with_no_stderr(env, monkeypatch):
    s, calls, refresh, print_pdf, toast = env
    monkeypatch.setattr(sys, "stderr", None)
    assert _run(s, runner.RunOptions(dry_run=True), refresh=refresh, print_pdf=print_pdf, toast=toast) == 0
    assert "dry-run" in (s.home / runner.LOG_NAME).read_text()


def test_unexpected_exception_is_a_logged_fail(env):
    s, calls, refresh, _, toast = env

    def bad(pdf, printer, title):
        raise OSError("disk full")

    assert _run(s, runner.RunOptions(), refresh=refresh, print_pdf=bad, toast=toast) == 1
    log = (s.home / runner.LOG_NAME).read_text()
    assert "unexpected error: OSError: disk full" in log
    assert calls["toast"][0][1].startswith("Not printed: unexpected error")
    assert not (s.home / runner.LOCK_NAME).exists()


def test_unknown_report_is_a_logged_failure(env):
    s, calls, refresh, print_pdf, toast = env
    assert runner.run("nope", runner.RunOptions(), s, now=FRI_2PM, refresh=refresh, print_pdf=print_pdf, toast=toast) == 2
    assert "unknown report" in (s.home / runner.LOG_NAME).read_text()


def test_cli_run_maps_flags_to_run_options(monkeypatch, tmp_path):
    from fridgesheet import cli

    captured = {}

    def fake_run(report_key, opts, settings):
        captured["report_key"], captured["opts"] = report_key, opts
        return 0

    monkeypatch.setattr(runner, "run", fake_run)
    monkeypatch.setattr(cli, "load_settings", lambda: Settings(home=tmp_path))

    with pytest.raises(SystemExit) as e:
        cli.main(["run", "open-work", "--dry-run", "--kid", "Al", "--date", "2026-09-09",
                  "--days", "7", "--overdue-days", "5", "--force", "--printer", "X",
                  "--no-refresh", "--reprint"])
    assert e.value.code == 0
    assert captured["report_key"] == "open-work"
    assert captured["opts"] == runner.RunOptions(dry_run=True, force=True, reprint=True, date="2026-09-09",
                                                  kid="Al", no_refresh=True, printer="X",
                                                  options={"days_ahead": 7, "overdue_days": 5})

    with pytest.raises(SystemExit) as e:
        cli.main(["run", "open-work"])
    assert e.value.code == 0
    assert captured["opts"].options == {"days_ahead": None, "overdue_days": None}


def test_cli_reports_lists_open_work(monkeypatch, capsys, tmp_path):
    from fridgesheet import cli

    monkeypatch.setattr(cli, "load_settings", lambda: Settings(home=tmp_path))
    with pytest.raises(SystemExit) as e:
        cli.main(["reports"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert "open-work" in out and "Open Work Sheet" in out and "disabled" in out
    assert "14:00" in out and "Mon,Tue,Wed,Thu,Fri" in out


def test_echo_receives_every_log_line_and_stderr_is_quiet(env, capsys):
    s, calls, refresh, print_pdf, toast = env
    lines = []
    assert _run(s, runner.RunOptions(dry_run=True), refresh=refresh, print_pdf=print_pdf, toast=toast, echo=lines.append) == 0
    # the refresh still runs on a dry run, so it is ingested first and logged: INFO, then OK.
    assert len(lines) == 2 and "INFO" in lines[0] and "ingested" in lines[0]
    assert " OK " in lines[1] and "dry-run" in lines[1]
    assert "".join(line + "\n" for line in lines) == (s.home / runner.LOG_NAME).read_text()
    assert capsys.readouterr().err == ""


def test_runner_loads_flags_from_the_database(env):
    """A flag set in the browser reaches the scheduled sheet: the flagged item is not in rows.json."""
    from fridgesheet.web import db, ingest
    from fridgesheet.web.stores import flags as flagstore
    s, calls, refresh, print_pdf, toast = env
    conn = db.open_db(s.home)
    ingest.record(conn, _snapshot(), tz=TZ, now=FRI_2PM)
    item_id = conn.execute("SELECT id FROM items WHERE key = 'canvas:1'").fetchone()[0]
    flagstore.set_flag(conn, item_id, "done", now=FRI_2PM.isoformat())
    conn.close()
    assert _run(s, runner.RunOptions(dry_run=True), refresh=refresh, print_pdf=print_pdf, toast=toast) == 0
    rows = json.loads((s.home / "sheets" / "2026-09-11" / "rows.json").read_text())
    assert rows["Alex"] == []
    log = (s.home / runner.LOG_NAME).read_text()
    assert "Al=0" in log


def test_runner_survives_a_broken_database(env):
    s, calls, refresh, print_pdf, toast = env
    (s.home / "fridgesheet.db").mkdir()                                  # a directory where the file should be
    assert _run(s, runner.RunOptions(dry_run=True), refresh=refresh, print_pdf=print_pdf, toast=toast) == 0
    assert "WARN" in (s.home / runner.LOG_NAME).read_text()


def test_run_ingests_after_refresh_and_records_the_run(env):
    from fridgesheet.web import db
    s, calls, refresh, print_pdf, toast = env
    assert _run(s, runner.RunOptions(printer="Office"), refresh=refresh, print_pdf=print_pdf, toast=toast) == 0
    conn = db.open_db(s.home)
    assert conn.execute("SELECT count(*) FROM refreshes").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM items").fetchone()[0] == 1          # the fixture's one assignment
    run = conn.execute("SELECT * FROM runs").fetchone()
    assert (run["report_key"], run["trigger"], run["outcome"], run["job_ref"]) == ("open-work", "cli", "OK", "job-1")
    assert run["pdf_path"].endswith("sheet.pdf") and run["finished_at"] and "printed" in run["message"]


def test_no_refresh_and_skips_still_record_but_do_not_ingest(env):
    from fridgesheet.web import db
    s, calls, refresh, print_pdf, toast = env
    _run(s, runner.RunOptions(dry_run=True, no_refresh=True, trigger="web"), refresh=refresh, print_pdf=print_pdf, toast=toast)
    _run(s, runner.RunOptions(), now=FRI_2PM.replace(hour=9), refresh=refresh, print_pdf=print_pdf, toast=toast)   # window skip
    conn = db.open_db(s.home)
    assert conn.execute("SELECT count(*) FROM refreshes").fetchone()[0] == 0
    rows = conn.execute("SELECT trigger, outcome FROM runs ORDER BY id").fetchall()
    assert [tuple(r) for r in rows] == [("web", "OK"), ("cli", "SKIP")]


def test_run_recording_failure_is_a_warning(env):
    """The database is a passenger even when it opened cleanly. Here the `runs` table
    disappears under a healthy connection mid-run (another process, a bad migration), which
    only `_record_run` touches: the sheet still builds and the run still succeeds."""
    from fridgesheet.web import db
    s, calls, refresh, print_pdf, toast = env

    def refresh_then_drop_runs(settings, **kw):
        other = db.connect(db.db_path(s.home))          # a second connection, the run's is already open
        other.execute("DROP TABLE runs")
        other.close()
        return _snapshot()

    assert _run(s, runner.RunOptions(dry_run=True), refresh=refresh_then_drop_runs, print_pdf=print_pdf, toast=toast) == 0
    log = (s.home / runner.LOG_NAME).read_text()
    assert "WARN" in log and "could not record the run" in log
    assert " OK " in log and "dry-run" in log            # the outcome line is still logged
    conn = db.open_db(s.home)                            # the ingest in the same run did commit
    assert conn.execute("SELECT count(*) FROM refreshes").fetchone()[0] == 1
    conn.close()
