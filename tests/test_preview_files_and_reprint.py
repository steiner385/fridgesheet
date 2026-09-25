"""#143: a preview, dry run, `--kid` or `--date` build never replaces the day's printed
sheet -- `sheet.pdf`, `rows.json` and the archive copy belong to the real run alone -- and
Runs → Reprint prints the PDF that run stored rather than rebuilding from today's data."""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("reportlab")

from fridgesheet import cli, config, runner  # noqa: E402
from fridgesheet.host.printing import PrintError  # noqa: E402
from fridgesheet.reports.base import BuildContext  # noqa: E402
from fridgesheet.web import actions, db, jobs  # noqa: E402
from fridgesheet.web import app as webapp  # noqa: E402
from fridgesheet.web.stores import runs  # noqa: E402
from tests.test_reports import _snapshot  # noqa: E402
from tests.test_web_jobs import FakeActions  # noqa: E402
from tests.web_fixtures import LOCAL_HOST_HEADERS, app_for, seed  # noqa: E402

TZ = ZoneInfo("America/New_York")
FRI_2PM = datetime(2026, 9, 11, 14, 5, tzinfo=TZ)
DAY = FRI_2PM.date().isoformat()


@pytest.fixture
def env(tmp_path):
    s = config.Settings(home=tmp_path, nicknames={"Alex": "Al"})
    s.sheets_archive = str(tmp_path / "archive")
    s.cache_dir.mkdir(parents=True)
    (s.cache_dir / "snapshot.json").write_text(json.dumps(_snapshot()))
    prints = []

    def print_pdf(pdf, printer, title):
        prints.append((pdf, printer, title))
        return "job-1"

    return s, prints, print_pdf


def _run(s, opts, print_pdf, now=FRI_2PM):
    return runner.run("open-work", opts, s, now=now, refresh=lambda settings, **kw: _snapshot(),
                      print_pdf=print_pdf, toast=lambda *a: None)


def _mark(day_dir: Path, archive: Path):
    """Stamp the real run's three files so a later build that rewrites any of them is caught
    even when the rebuilt bytes would happen to be identical."""
    (day_dir / "sheet.pdf").write_bytes(b"%PDF-1.4 the printed one")
    (day_dir / "rows.json").write_text('{"Alex": [{"name": "the real rows"}]}')
    archived = next(archive.rglob("*.pdf"))
    archived.write_bytes(b"%PDF-1.4 the archived one")
    return archived


def test_a_dry_run_writes_a_preview_pdf_and_leaves_the_days_sheet_alone(env):
    s, prints, print_pdf = env
    assert _run(s, runner.RunOptions(), print_pdf) == 0
    day_dir = s.home / "sheets" / DAY
    archived = _mark(day_dir, Path(s.sheets_archive))

    assert _run(s, runner.RunOptions(dry_run=True, force=True), print_pdf) == 0
    assert (day_dir / "sheet-preview.pdf").is_file()
    assert (day_dir / "sheet.pdf").read_bytes() == b"%PDF-1.4 the printed one"
    assert json.loads((day_dir / "rows.json").read_text()) == {"Alex": [{"name": "the real rows"}]}
    assert archived.read_bytes() == b"%PDF-1.4 the archived one"
    assert [p.name for p in Path(s.sheets_archive).rglob("*.pdf")] == [archived.name]   # no second archive copy
    assert len(prints) == 1                                                          # nothing printed
    # The run row points at the file this run built, so Runs links the preview, not the sheet.
    conn = db.open_db(s.home)
    row = runs.latest_for(conn, "open-work")
    conn.close()
    assert row["outcome"] == "OK" and row["pdf_path"].endswith("sheet-preview.pdf")


def test_a_kid_run_writes_its_own_pdf_and_never_rows_json_or_the_archive(env):
    """A `--kid` run's rows.json held one child, so the next morning's sheet marked every other
    child's items NEW and lost their "cleared" lines."""
    s, prints, print_pdf = env
    assert _run(s, runner.RunOptions(kid="Al"), print_pdf) == 0
    day_dir = s.home / "sheets" / DAY
    assert (day_dir / "sheet-Al.pdf").is_file()
    assert not (day_dir / "sheet.pdf").exists()
    assert not (day_dir / "rows.json").exists()
    assert not Path(s.sheets_archive).exists()
    assert prints[0][0] == day_dir / "sheet-Al.pdf"                        # it did print that file
    assert (day_dir / "printed.txt").is_file()                              # and says so


def test_a_date_run_is_a_side_build_too(env):
    """`--date` is for testing (and was how Reprint rebuilt a past day); it must not replace
    that day's printed sheet or the rows tomorrow's diff is made from."""
    s, prints, print_pdf = env
    assert _run(s, runner.RunOptions(), print_pdf) == 0
    day_dir = s.home / "sheets" / DAY
    archived = _mark(day_dir, Path(s.sheets_archive))
    assert _run(s, runner.RunOptions(date=DAY, reprint=True), print_pdf, now=FRI_2PM.replace(day=14)) == 0
    assert (day_dir / "sheet-preview.pdf").is_file()
    assert (day_dir / "sheet.pdf").read_bytes() == b"%PDF-1.4 the printed one"
    assert json.loads((day_dir / "rows.json").read_text()) == {"Alex": [{"name": "the real rows"}]}
    assert archived.read_bytes() == b"%PDF-1.4 the archived one"


def test_the_real_run_still_writes_all_three(env):
    s, prints, print_pdf = env
    assert _run(s, runner.RunOptions(), print_pdf) == 0
    day_dir = s.home / "sheets" / DAY
    assert (day_dir / "sheet.pdf").is_file() and (day_dir / "rows.json").is_file()
    assert (Path(s.sheets_archive) / runner.school_year(FRI_2PM.date()) / f"{DAY} Open Work.pdf").is_file()
    assert not (day_dir / "sheet-preview.pdf").exists()


def test_build_context_names_the_pdf_for_every_report():
    """Both reports take their PDF name from the context, so the runner's one decision --
    real sheet or side build -- reaches a saved report's `report.pdf` the same way."""
    def ctx(variant):
        return BuildContext(settings=None, home=Path("/h"), day=date(2026, 9, 11), now=FRI_2PM, out_dir=Path("/h/sheets/2026-09-11"),
                            kid=None, nicknames={}, prev_rows=None, prev_label=None, stale_note=None, options={},
                            data_as_of=FRI_2PM, variant=variant)
    assert ctx("").pdf_path("sheet") == Path("/h/sheets/2026-09-11/sheet.pdf")
    assert ctx("preview").pdf_path("report") == Path("/h/sheets/2026-09-11/report-preview.pdf")
    assert ctx("Al").pdf_path("sheet") == Path("/h/sheets/2026-09-11/sheet-Al.pdf")


def test_the_variant_is_the_kid_else_preview_else_nothing():
    """One decision, in one place: what, if anything, this build is instead of the day's sheet.
    A kid prefix is user-typed and reaches a file name, so it is reduced the way a saved
    report's name is."""
    assert runner.build_variant(runner.RunOptions()) == ""
    assert runner.build_variant(runner.RunOptions(force=True, reprint=True, force_print=True)) == ""
    assert runner.build_variant(runner.RunOptions(dry_run=True)) == "preview"
    assert runner.build_variant(runner.RunOptions(date="2026-09-09")) == "preview"
    assert runner.build_variant(runner.RunOptions(kid="Al")) == "Al"
    assert runner.build_variant(runner.RunOptions(kid="../Al", dry_run=True)) == "Al"


# --- Reprint prints the stored PDF ------------------------------------------------------------

def _stored_run(home, name="sheet.pdf"):
    conn = seed(home)
    pdf = home / "sheets" / "2026-09-15" / name
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.4 stored")
    rid = runs.record(conn, "open-work", "2026-09-15T14:00:00-04:00", "2026-09-15T14:02:00-04:00", "schedule", "OK",
                      "printed job=1 2p Alex=3", str(pdf))
    conn.close()
    return rid, pdf


def test_reprint_action_prints_the_file_it_is_given_and_records_a_run(tmp_path):
    rid, pdf = _stored_run(tmp_path)
    s = config.Settings(home=tmp_path)
    s.printer = "Brother"
    prints = []

    def print_pdf(p, printer, title):
        prints.append((p, printer, title))
        return "job-7"

    lines = []
    assert actions.reprint(home=tmp_path, log=lines.append, settings=s, run_id=rid, pdf=str(pdf), report_key="open-work",
                           print_pdf=print_pdf) == 0
    assert prints == [(pdf, "Brother", "fridgesheet open work sheet 2026-09-15 (reprint)")]
    conn = db.open_db(tmp_path)
    row = runs.latest_for(conn, "open-work")
    conn.close()
    assert row["id"] != rid and row["outcome"] == "OK" and row["trigger"] == "web" and row["job_ref"] == "job-7"
    assert row["pdf_path"] == str(pdf) and row["message"].startswith("reprinted")
    assert any("job-7" in ln for ln in lines)


def test_reprint_action_reports_a_printer_failure_as_fail(tmp_path):
    rid, pdf = _stored_run(tmp_path)

    def bad(p, printer, title):
        raise PrintError("printer offline")

    assert actions.reprint(home=tmp_path, log=lambda ln: None, settings=config.Settings(home=tmp_path), run_id=rid,
                           pdf=str(pdf), report_key="open-work", print_pdf=bad) == 1
    conn = db.open_db(tmp_path)
    row = runs.latest_for(conn, "open-work")
    conn.close()
    assert row["outcome"] == "FAIL" and "printer offline" in row["message"] and row["pdf_path"] == str(pdf)


def _client(home):
    application = webapp.create_app(config.Settings(home=home), worker=False)
    fake = FakeActions()
    w = jobs.Worker(application.state.fridgesheet, actions=fake)
    application.state.fridgesheet.jobs = w
    return TestClient(application, headers=LOCAL_HOST_HEADERS), w, fake


def test_the_runs_page_reprint_button_posts_the_run_not_a_date(tmp_path):
    rid, pdf = _stored_run(tmp_path)
    c, w, fake = _client(tmp_path)
    form = re.search(r'<form hx-post="/jobs/reprint".*?</form>', c.get("/runs").text, re.S).group(0)
    assert dict(re.findall(r'name="(\w+)" value="([^"]*)"', form)) == {"run_id": str(rid)}
    assert 'hx-post="/jobs/print"' not in c.get("/runs").text


def test_reprint_sends_the_stored_pdf_to_the_printer_and_rebuilds_nothing(tmp_path):
    rid, pdf = _stored_run(tmp_path, name="sheet-preview.pdf")   # a preview row reprints its own file too
    c, w, fake = _client(tmp_path)
    r = c.post("/jobs/reprint", data={"run_id": rid})
    assert r.status_code == 200
    w.run_pending()
    assert fake.calls == [("reprint", rid, str(pdf), "open-work")]
    assert w.last.outcome == "OK" and w.last.pdf == pdf
    assert f'href="/jobs/{w.last.id}/pdf"' in c.get(f"/jobs/{w.last.id}").text


def test_reprint_refuses_a_run_whose_pdf_is_gone_or_unknown(tmp_path):
    rid, pdf = _stored_run(tmp_path)
    pdf.unlink()
    c, w, fake = _client(tmp_path)
    assert c.post("/jobs/reprint", data={"run_id": rid}).status_code == 404
    assert c.post("/jobs/reprint", data={"run_id": 999}).status_code == 404
    assert c.post("/jobs/reprint").status_code == 404
    assert fake.calls == [] and w.current is None


def test_reprint_is_not_offered_without_a_worker(tmp_path):
    _stored_run(tmp_path)
    assert 'hx-post="/jobs/reprint"' not in app_for(tmp_path).get("/runs").text


# --- the help text tells the truth -------------------------------------------------------------

@pytest.mark.parametrize("command", ["run", "print-sheet"])
def test_dry_run_help_says_the_run_is_recorded_not_that_it_is_not(command, capsys):
    with pytest.raises(SystemExit):
        cli.main([command, "--help"])
    out = capsys.readouterr().out
    line = re.search(r"--dry-run\s+(.*?)(?=\n\s+--|\Z)", out, re.S).group(1)
    assert "not record" not in line and "do not print or record" not in line
    assert "recorded" in line and "sheet-preview.pdf" in line
