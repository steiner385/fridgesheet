"""Residual report bugs from #6: group order, exported file names, spreadsheet formulas, a
stored definition the builder cannot use, and run history naming saved reports."""
from __future__ import annotations

import csv
import re
import io
import json

import pytest
from datetime import date

from fridgesheet.web import db
from fridgesheet.web.stores import reports as store
from tests.web_fixtures import FakeScheduling, app_for, seed


def _client(home):
    c = app_for(home)
    c.app.state.fridgesheet.extra["scheduling"] = FakeScheduling()
    return c


def _save(home, name="Mine", **over):
    conn = db.open_db(home)
    d = {"title": name, "source": "items", "columns": ["kid", "name"], **over}
    rid = store.create(conn, name, json.dumps(d), now="2026-09-16T08:00:00-04:00")
    conn.close()
    return rid


def test_date_groups_come_in_date_order_not_text_order(tmp_path):
    """Grouped by due date, "9/8" sorted after "9/20" as text; groups follow the column's own
    sort key, the same one the rows use."""
    seed(tmp_path).close()
    rid = _save(tmp_path, columns=["name"], group_by="due")
    labels = [g["label"] for g in _client(tmp_path).get(f"/reports/{rid}/export.json").json()["groups"]]
    dated = [l for l in labels if l]
    assert len(dated) > 2
    as_dates = [date(2026, *map(int, l.split("/"))) for l in dated]
    assert as_dates == sorted(as_dates), labels


def test_a_title_outside_latin_1_downloads_instead_of_crashing(tmp_path):
    """An HTTP header is Latin-1; a Cyrillic or emoji title raised on export. The header now
    carries an ASCII fallback plus the real name as RFC 5987 `filename*`."""
    seed(tmp_path).close()
    rid = _save(tmp_path, name="Оценки Алекса")
    c = _client(tmp_path)
    for ext in ("csv", "json"):
        r = c.get(f"/reports/{rid}/export.{ext}")
        assert r.status_code == 200, ext
        cd = r.headers["content-disposition"]
        assert cd.startswith("attachment; filename=\"") and "filename*=UTF-8''" in cd
        cd.encode("latin-1")                                   # the header itself is sendable
        assert "%D0%9E%D1%86%D0%B5%D0%BD%D0%BA%D0%B8" in cd     # "Оценки", percent-encoded


def test_a_csv_cell_that_starts_like_a_formula_is_neutralised(tmp_path):
    """Assignment names come from Canvas and HAC. A name like `=HYPERLINK(...)` opened in a
    spreadsheet runs as a formula; such cells get a leading apostrophe. Numbers are left alone."""
    conn = seed(tmp_path)
    conn.execute("UPDATE items SET name = '=HYPERLINK(\"http://x\",\"y\")' WHERE name = 'Quiz 1'")
    conn.execute("UPDATE items SET name = '@SUM(1)' WHERE name = 'Lab notebook'")
    conn.close()
    rid = _save(tmp_path, columns=["name", "points"])
    text = _client(tmp_path).get(f"/reports/{rid}/export.csv").text
    cells = [c for row in csv.reader(io.StringIO(text)) for c in row]
    assert "'=HYPERLINK(\"http://x\",\"y\")" in cells and "'@SUM(1)" in cells
    assert not any(c[:1] in "=+-@" and not c.lstrip("-").replace(".", "").isdigit() for c in cells if c)
    assert "10" in cells or "30" in cells                       # points stay plain numbers


def test_a_stored_definition_with_an_unknown_source_says_so_in_the_builder(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path, source="nope")
    body = _client(tmp_path).get(f"/reports/{rid}").text
    assert "Unknown source" in body and "nope" in body


def test_run_history_names_a_saved_report_by_its_title(tmp_path):
    conn = seed(tmp_path)
    conn.close()
    rid = _save(tmp_path, name="Weekly grades")
    conn = db.open_db(tmp_path)
    conn.execute("INSERT INTO runs(report_key, started_at, finished_at, trigger, outcome, message) VALUES (?,?,?,?,?,?)",
                 (f"view:{rid}", "2026-09-15T14:00:05-04:00", "2026-09-15T14:02:00-04:00", "schedule", "OK", "1p"))
    conn.close()
    body = _client(tmp_path).get("/runs").text
    assert "<td>Weekly grades</td>" in body
    assert f"<td>view:{rid}</td>" not in body


def test_a_scoped_changes_report_asks_the_store_for_that_kid_before_the_cap(tmp_path, monkeypatch):
    """#6: the changes source took the newest MAX_ROWS events for every kid and only then
    dropped the other kids, so a busy sibling could push this kid's rows past the cap."""
    from fridgesheet.web.stores import changes as changes_store
    conn = seed(tmp_path)
    sam = conn.execute("SELECT id FROM students WHERE key = 'Sam'").fetchone()["id"]
    conn.close()
    asked = []
    real = changes_store.since
    monkeypatch.setattr(changes_store, "since", lambda conn, **kw: asked.append(kw.get("student_id")) or real(conn, **kw))
    rid = _save(tmp_path, source="changes", columns=["kid", "what"], scope=["Sam"])
    rows = _client(tmp_path).get(f"/reports/{rid}/export.json").json()["rows"]
    assert asked == [sam]
    assert rows and {r["kid"] for r in rows} == {"Sam"}


def test_the_preview_says_how_many_rows_it_has(tmp_path):
    seed(tmp_path).close()
    r = _client(tmp_path).post("/reports/preview", data={"title": "Mine", "source": "items", "columns": ["kid", "name"]})
    assert re.search(r"\d+ rows?\b", r.text)


def test_changing_the_source_redraws_the_builder_for_that_source(tmp_path):
    """#6: the column, group, sort and filter lists were drawn for the source the page opened
    with; picking another source left them listing columns it does not have."""
    seed(tmp_path).close()
    c = _client(tmp_path)
    body = c.get("/reports/new").text
    assert 'hx-post="/reports/builder"' in body and 'hx-trigger="change"' in body
    r = c.post("/reports/builder", data={"title": "Mine", "source": "changes", "columns": ["kid", "name", "status"]})
    assert r.status_code == 200
    assert 'value="what"' in r.text and 'value="status"' not in r.text          # changes' columns, not items'
    assert re.search(r'value="kid"\s+checked', r.text)                           # a column both have stays ticked


def test_deleting_a_report_already_deleted_in_another_tab_is_a_plain_404(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path)
    c = _client(tmp_path)
    assert c.post(f"/reports/{rid}/delete").status_code == 200
    r = c.post(f"/reports/{rid}/delete")
    assert r.status_code == 404


def test_running_a_saved_report_that_was_deleted_says_so(tmp_path):
    from fridgesheet import reports as registry
    from fridgesheet.reports.base import ReportError
    seed(tmp_path).close()
    rid = _save(tmp_path)
    conn = db.open_db(tmp_path)
    store.delete(conn, rid)
    conn.close()
    with pytest.raises(ReportError, match=f"view:{rid}"):
        registry.resolve(f"view:{rid}", tmp_path)
