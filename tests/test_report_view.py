"""A stored definition as a Report: it resolves by key and builds a PDF through the runner's protocol."""
from __future__ import annotations

import json
from datetime import date
from unittest.mock import patch

import pytest

from fridgesheet import config, reports, runner, sheet
from fridgesheet.reports import ReportError
from fridgesheet.web import views
from fridgesheet.web import db
from fridgesheet.web.stores import reports as reportstore
from tests.conftest import needs_pdftotext
from tests.web_fixtures import NOW, seed


def _save(home, name="Weekly summary", **over):
    conn = db.open_db(home)
    d = {"title": name, "source": "items", "columns": ["kid", "course", "name", "status"], **over}
    rid = reportstore.create(conn, name, json.dumps(d), now="2026-09-16T08:00:00-04:00")
    conn.close()
    return rid


def test_resolve_finds_code_and_view_reports(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path)
    assert reports.resolve("open-work", tmp_path).key == "open-work"
    r = reports.resolve(f"view:{rid}", tmp_path)
    assert r.key == f"view:{rid}" and r.title == "Weekly summary"
    assert r.output_dir == f"reports/view-{rid}" and r.archive_name(date(2026, 9, 16)).endswith("Weekly summary.pdf")
    with pytest.raises(ReportError):
        reports.resolve("view:999", tmp_path)
    with pytest.raises(ReportError):
        reports.resolve("nonsense", tmp_path)
    with pytest.raises(ReportError):
        reports.resolve(f"view:{rid}", None)


def test_only_plain_digits_name_a_saved_report(tmp_path):
    """`int()` takes "+7", " 7 " and "7_0". Every one of those resolves to a report, renders to
    the same `fridgesheet-view-7` unit, and stores its own `[reports."view:+7"]` table -- three keys
    for one timer, two of which the Schedules page never shows."""
    seed(tmp_path).close()
    rid = _save(tmp_path)
    assert reports.resolve(f"view:{rid}", tmp_path).key == f"view:{rid}"
    for bad in (f"view:+{rid}", f"view: {rid} ", "view:7_0", "view:", "view:-1", "view:٧"):
        with pytest.raises(ReportError, match="malformed"):
            reports.resolve(bad, tmp_path)


def test_a_leading_zero_is_also_rejected_though_it_passes_isdigit(tmp_path):
    """#36: `"007".isdigit()` is true, so the plain-digits check above let it through. It
    resolves to report 7 -- same as `"7"` -- but renders to a *different* unit
    (`fridgesheet-view-007.timer`, distinct from `fridgesheet-view-7.timer`, since `safe_key` does not
    normalize numerals) and stores a second `[reports."view:007"]` table that the Schedules
    page can never show or remove. `_VIEW_KEY_RE`'s `(0|[1-9][0-9]*)` catches it the same way
    it catches every other non-canonical spelling above."""
    seed(tmp_path).close()
    rid = _save(tmp_path)
    with pytest.raises(ReportError, match="malformed"):
        reports.resolve("view:007", tmp_path)                # the format check runs before any lookup
    with pytest.raises(ReportError, match="malformed"):
        reports.resolve(f"view:0{rid}", tmp_path)             # a leading zero on the id that does exist
    assert reports.resolve(f"view:{rid}", tmp_path).key == f"view:{rid}"          # the canonical spelling still works
    with pytest.raises(ReportError, match="no saved report"):
        reports.resolve("view:0", tmp_path)                   # canonical spelling of an id nothing uses


def test_a_trailing_newline_is_also_rejected_though_python_s_dollar_lets_it_through(tmp_path):
    """`_VIEW_KEY_RE` anchors its end with `$`, which in Python matches either at the string's
    end or just before a single trailing `\\n` -- so `"view:7\\n"` used to pass where the old
    `isdigit()` check rejected it. `safe_key` folds it to the same unit as `"view:7"`, so no
    foreign object is reachable through it, but `web/schedules.py` writes `[reports.<key>]`
    verbatim for any key `resolve` accepts -- a second config table for the same timer, which
    is exactly what the comment two lines above the regex says one shared pattern prevents."""
    seed(tmp_path).close()
    rid = _save(tmp_path)
    for bad in (f"view:{rid}\n", f"view:{rid} "):
        assert not reports.is_schedulable_key(bad), bad
        with pytest.raises(ReportError, match="malformed"):
            reports.resolve(bad, tmp_path)
    assert reports.resolve(f"view:{rid}", tmp_path).key == f"view:{rid}"     # the plain spelling still works


def test_is_schedulable_key_accepts_exactly_what_resolve_does_without_a_database(tmp_path):
    """`schedule remove --all` cannot call `resolve` -- resolving `view:<id>` opens the
    database it goes to such trouble not to create -- so it gates its key set on
    `is_schedulable_key` instead. The two must agree on spelling, or the `--all` path either
    removes a key the single-key path refuses (`web`, which on Windows names the web server's
    own logon task) or skips one a parent really did schedule.

    They agree by construction: both read `_VIEW_KEY_RE`. This pins that, and pins the one
    place they differ on purpose -- `is_schedulable_key` says True for a `view:<id>` whose
    report has been deleted, because its schedule still needs removing."""
    seed(tmp_path).close()
    rid = _save(tmp_path)
    for good in ("open-work", f"view:{rid}", "view:0", "view:999"):
        assert reports.is_schedulable_key(good), good
    for bad in ("web", "Web", "WEB", "print-sheet", "view:007", "view:+1", "view: 1", "view:", "view:٧", ""):
        assert not reports.is_schedulable_key(bad), bad
        with pytest.raises(ReportError):                    # resolve refuses every one of them too
            reports.resolve(bad, tmp_path)
    # ...and the deliberate difference: report 999 does not exist, so resolve says so -- but
    # its schedule, if a parent ever had one, is still this app's to remove.
    with pytest.raises(ReportError, match="no saved report"):
        reports.resolve("view:999", tmp_path)


def test_archive_name_strips_unsafe_characters_from_the_report_name(tmp_path):
    """`reports.name` is user-editable and reaches the filesystem through `archive_name`: a
    name with a path separator, a `..`, or a quote must not survive into the file name."""
    seed(tmp_path).close()
    rid = _save(tmp_path, name='../../../../tmp/fridgesheet-escaped "Report"')
    r = reports.resolve(f"view:{rid}", tmp_path)
    name = r.archive_name(date(2026, 9, 16))
    assert "/" not in name and ".." not in name and '"' not in name
    assert name.startswith("2026-09-16 ") and name.endswith(".pdf")

    empty = reports.resolve(f"view:{_save(tmp_path, name='////')}", tmp_path)
    assert empty.archive_name(date(2026, 9, 16)) == "2026-09-16 report.pdf"


def test_get_still_serves_code_reports_only():
    assert reports.get("open-work").key == "open-work"
    with pytest.raises(ReportError):
        reports.get("view:1")


def _ctx(home, out):
    return reports.BuildContext(settings=config.Settings(home=home), home=home, day=NOW.date(), now=NOW,
                                out_dir=out, kid=None, nicknames={"Alex": "Al"}, prev_rows=None,
                                prev_label=None, stale_note=None, options={}, data_as_of=NOW)


@needs_pdftotext
def test_build_writes_a_pdf_and_rows(tmp_path):
    from fridgesheet import sheet
    seed(tmp_path).close()
    rid = _save(tmp_path)
    r = reports.resolve(f"view:{rid}", tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    built = r.build({}, _ctx(tmp_path, out))
    assert built.pdf.is_file() and built.pdf.parent == out
    text = sheet.pdf_text(built.pdf)
    assert "Quiz 1" in text and "Al" in text
    assert built.rows["columns"] == ["kid", "course", "name", "status"]
    assert any(row["name"] == "Quiz 1" for row in built.rows["rows"])
    n = len(built.rows["rows"])
    assert built.summary.endswith(f"{n} rows") and built.summary[0].isdigit()


def test_build_refuses_a_broken_definition(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path, columns=[])
    r = reports.resolve(f"view:{rid}", tmp_path)
    with pytest.raises(ReportError):
        r.build({}, _ctx(tmp_path, tmp_path))


def test_the_runner_runs_a_view_report(tmp_path):
    """The runner loads a snapshot before building whatever the report is, so one has to be on
    disk even though a view report reads the database instead."""
    from tests.web_fixtures import snapshot
    seed(tmp_path).close()
    (tmp_path / "cache").mkdir(exist_ok=True)
    (tmp_path / "cache" / "snapshot.json").write_text(json.dumps(snapshot()))
    rid = _save(tmp_path)
    s = config.Settings(home=tmp_path)
    rc = runner.run(f"view:{rid}", runner.RunOptions(dry_run=True, force=True, no_refresh=True, notify=False),
                    s, now=NOW)
    assert rc == 0
    conn = db.open_db(tmp_path)
    row = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    assert row["report_key"] == f"view:{rid}" and row["outcome"] == "OK"
    assert (tmp_path / f"reports/view-{rid}" / NOW.date().isoformat() / "report.pdf").is_file()


def test_a_scheduled_view_report_follows_the_assignments_source(tmp_path):
    """Review finding: the browser preview followed [sources]; the scheduled PDF of the same report did not."""
    from fridgesheet import sources
    from fridgesheet.reports.base import BuildContext
    seed(tmp_path).close()
    rid = _save(tmp_path)
    s = config.Settings(home=tmp_path)
    s.sources = sources.DEFAULT.with_default("hac", "hac")
    out = tmp_path / "out"
    out.mkdir()
    ctx = BuildContext(settings=s, home=tmp_path, day=NOW.date(), now=NOW, out_dir=out, kid=None, nicknames={},
                       prev_rows=None, prev_label=None, stale_note=None, options={}, data_as_of=NOW)
    built = reports.resolve(f"view:{rid}", tmp_path).build({}, ctx)
    quiz = next(r for r in built.rows["rows"] if r["name"] == "Quiz 1")
    assert quiz["status"] == "28/30"


def test_build_table_pdf_embeds_a_chart_image_when_given_one(tmp_path):
    png_bytes = _tiny_png()          # a minimal real PNG -- reportlab's Image flowable opens it with PIL
    rendered = views.Rendered("Recap", [views.Column("name", "Name", "text")],
                              [views.Group("", [{"name": "Quiz 1"}])])
    out = tmp_path / "r.pdf"
    pages = sheet.build_table_pdf(rendered, out, title="Recap", printed_at=NOW, chart_png=png_bytes)
    assert pages >= 1 and out.exists()


def _tiny_png() -> bytes:
    """A 1x1 white PNG, small enough to inline here rather than shipping a fixture file."""
    import base64
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


@needs_pdftotext
def test_a_chart_bearing_report_embeds_the_chart(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path, chart={"type": "bar", "x": "due", "y": None, "bucket": "week"})
    r = reports.resolve(f"view:{rid}", tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    built = r.build({}, _ctx(tmp_path, out))
    assert built.pdf.is_file()


@needs_pdftotext
def test_a_broken_chart_renderer_still_produces_a_built_report(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path, chart={"type": "bar", "x": "due", "y": None, "bucket": "week"})
    r = reports.resolve(f"view:{rid}", tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    with patch("fridgesheet.reports.view.chart_render.render_chart_png", side_effect=RuntimeError("no chromium")):
        built = r.build({}, _ctx(tmp_path, out))
    assert built.pdf.is_file()
    from fridgesheet import sheet
    assert "Chart unavailable" in sheet.pdf_text(built.pdf)
