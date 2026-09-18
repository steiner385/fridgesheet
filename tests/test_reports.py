"""The report registry and the open-work report's build(), isolated from the runner."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("reportlab")

from lakota_grades import cli, host, reports  # noqa: E402
from lakota_grades.config import Settings  # noqa: E402
from lakota_grades.reports.base import BuildContext, ReportError  # noqa: E402
from lakota_grades.web import db, views  # noqa: E402
from lakota_grades.web.stores import reports as store  # noqa: E402
from tests.conftest import needs_pdftotext  # noqa: E402

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 11, 14, 5, tzinfo=TZ)


def _snapshot() -> dict:
    a = {"id": 1, "name": "WS 1", "due_at": (NOW + timedelta(days=2)).isoformat(), "unlock_at": None, "created_at": None,
         "points_possible": 10.0, "submission_types": ["online_upload"], "group": "Homework", "published": True, "score": None,
         "grade": None, "state": "unsubmitted", "late": False, "missing": False, "excused": False}
    return {"fetched_at": NOW.isoformat(), "fetched_at_epoch": NOW.timestamp(), "sources": {"canvas": "ok", "hac": "ok"}, "stale": {},
            "students": {"Alex": {"name": "Alex S", "canvas": {"courses": [{"id": 5, "name": "Honors Biology", "assignments": [a]}]}, "hac": {"classes": []}},
                         "Sam": {"name": "Sam S", "canvas": {"courses": []}, "hac": {"classes": []}}}}


def _ctx(tmp_path, **over) -> BuildContext:
    d = dict(settings=Settings(home=tmp_path), home=tmp_path, day=NOW.date(), now=NOW, out_dir=tmp_path / "out", kid=None,
             nicknames={"Alex": "Al"}, prev_rows=None, prev_label=None, stale_note=None, options={}, data_as_of=NOW)
    d.update(over)
    (d["out_dir"]).mkdir(parents=True, exist_ok=True)
    return BuildContext(**d)


def test_registry_has_open_work_with_its_metadata():
    r = reports.get("open-work")
    assert r.key == "open-work" and r.title == "Open Work Sheet" and r.output_dir == "sheets" and r.default_time == "14:00"
    assert r.archive_name(NOW.date()) == "2026-09-11 Open Work.pdf"
    with pytest.raises(ReportError, match="open-work"):
        reports.get("nope")


def test_open_work_builds_pdf_rows_and_summary(tmp_path):
    built = reports.get("open-work").build(_snapshot(), _ctx(tmp_path))
    assert built.pdf == tmp_path / "out" / "sheet.pdf" and built.pdf.read_bytes()[:4] == b"%PDF"
    assert set(built.rows) == {"Alex", "Sam"} and len(built.rows["Alex"]) == 1
    assert built.summary.startswith("1p Al=1 Sam=0")


@needs_pdftotext
def test_open_work_honours_kid_filter_options_and_previous_rows(tmp_path):
    r = reports.get("open-work")
    first = r.build(_snapshot(), _ctx(tmp_path, kid="al", options={"days_ahead": 1, "overdue_days": 3}))
    assert set(first.rows) == {"Alex"} and first.rows["Alex"] == []      # due in 2 days, window is 1
    second = r.build(_snapshot(), _ctx(tmp_path, prev_rows=first.rows, prev_label="Thu 9/10"))
    from lakota_grades import sheet
    assert "since last sheet" in sheet.pdf_text(second.pdf)
    with pytest.raises(ReportError, match="no student matches"):
        r.build(_snapshot(), _ctx(tmp_path, kid="zed"))


def test_available_lists_the_code_reports_and_every_saved_one(tmp_path):
    conn = db.open_db(tmp_path)
    store.create(conn, "Weekly summary", views.defaults().to_json(), now="2026-09-16T08:00:00-04:00")
    conn.close()
    got = reports.available(tmp_path)
    assert [r.key for r in got][0] == "open-work"
    assert "view:1" in [r.key for r in got]
    assert [r.title for r in got][-1] == "Weekly summary"


def test_available_without_a_home_is_the_code_reports():
    assert [r.key for r in reports.available()] == ["open-work"]


def test_available_never_fails_because_of_the_database(tmp_path):
    """Listing reports is what a page does before it can say anything at all. A database that
    is missing or unreadable costs the saved reports, not the page."""
    (tmp_path / "lakota.db").write_bytes(b"this is not a database")
    assert [r.key for r in reports.available(tmp_path)] == ["open-work"]


def test_schedule_install_resolves_a_saved_report(tmp_path, monkeypatch):
    """`lakota-grades schedule install view:1` used to fail with "unknown report" because the
    command called the registry's `get` instead of `resolve` (#35).

    The idiom is `tests/test_print_sheet.py:185`: `cli.main` ends in `sys.exit`, so the exit
    code arrives as `SystemExit`, and `load_settings` is patched rather than the environment
    (`config.DEFAULT_HOME` is computed at import, so setting LAKOTA_GRADES_HOME here is too
    late to take effect).
    """
    conn = db.open_db(tmp_path)
    store.create(conn, "Weekly summary", views.defaults().to_json(), now="2026-09-16T08:00:00-04:00")
    conn.close()
    installed = {}

    class FakeScheduling:
        SchedulingError = host.SchedulingError
        @staticmethod
        def command_for(key):
            return ("/py", f"run {key}", "/wd")
        @staticmethod
        def install(key, time, days, exe, args, workdir, **kw):
            installed.update(key=key, time=time, days=list(days), title=kw.get("title"))
        @staticmethod
        def display_name(key):
            return f"lakota-{key}.{{service,timer}}"
        @staticmethod
        def describe(key):
            return host.ScheduleInfo("systemd", True, "Fri 16:00", None)

    monkeypatch.setattr(cli, "load_settings", lambda: Settings(home=tmp_path))
    monkeypatch.setattr("lakota_grades.host.scheduling", FakeScheduling)
    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "install", "view:1"])
    assert e.value.code == 0
    assert installed["key"] == "view:1" and installed["title"] == "Weekly summary"
    assert installed["time"] == "16:00"          # the view report's own default_time
