"""The Reports page: the list, the builder, the live preview and saving."""
from __future__ import annotations

import csv
import io
import json
import tomllib

from fridgesheet.web import db, schedules, views
from fridgesheet.web.routes.reports import _chart_json
from fridgesheet.web.stores import reports as store
from tests.web_fixtures import FakeScheduling, app_for, seed, snapshot


def _client(home, sched=None):
    """A client whose scheduler is a fake: deleting a report now removes its schedule, and no
    test may go anywhere near the machine's own systemctl."""
    c = app_for(home)
    c.app.state.fridgesheet.extra["scheduling"] = sched or FakeScheduling()
    return c


def _save(home, name="Mine", **over):
    conn = db.open_db(home)
    d = {"title": name, "source": "items", "columns": ["kid", "name"], **over}
    rid = store.create(conn, name, json.dumps(d), now="2026-09-16T08:00:00-04:00")
    conn.close()
    return rid


def test_empty_list_offers_the_templates(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    body = c.get("/reports").text
    assert "No saved reports yet" in body and 'hx-post="/reports/seed"' in body
    assert "Open Work Sheet" in body                       # the code report is always listed
    r = c.post("/reports/seed")
    assert r.status_code == 200 and "Recent changes" in r.text and "Grade trend" in r.text
    assert "No saved reports yet" not in c.get("/reports").text
    assert "already has reports" in c.post("/reports/seed").text


def test_list_shows_code_and_view_reports_with_links(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path)
    body = app_for(tmp_path).get("/reports").text
    assert f'href="/reports/{rid}"' in body and "Mine" in body
    assert "open-work" in body and f"view:{rid}" in body


def test_the_report_name_links_to_a_rendered_view_not_the_builder(tmp_path):
    """A parent clicking a report's name wants to read it, not edit its definition; the builder
    stays reachable from an explicit Edit link instead."""
    seed(tmp_path).close()
    rid = _save(tmp_path)
    body = app_for(tmp_path).get("/reports").text
    assert f'href="/reports/{rid}/view"' in body
    assert f'href="/reports/{rid}">Edit' in body


def test_report_view_renders_the_report_as_a_standalone_printable_page(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path, title="Mine", columns=["kid", "name"])
    r = app_for(tmp_path).get(f"/reports/{rid}/view")
    assert r.status_code == 200
    assert "Mine" in r.text and "Quiz 1" in r.text                # the report's own rows
    assert "data-print" in r.text and 'href="/reports"' in r.text  # a print button, and a way back


def test_report_view_of_a_broken_definition_is_a_400(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path, columns=[])
    assert app_for(tmp_path).get(f"/reports/{rid}/view").status_code == 400


def test_report_view_404s_for_an_unknown_report(tmp_path):
    seed(tmp_path).close()
    assert app_for(tmp_path).get("/reports/999/view").status_code == 404


def test_builder_renders_every_control(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/reports/new").text
    for name in ("title", "source", "scope", "columns", "group_by", "orientation", "per_kid_sections"):
        assert f'name="{name}"' in body, name
    assert 'value="items"' in body and 'value="grades"' in body and 'value="changes"' in body
    assert "Alex" in body and "Sam" in body            # scope options
    assert 'hx-post="/reports/preview"' in body


def test_preview_returns_a_table(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    r = c.post("/reports/preview", data={"title": "T", "source": "items", "columns": ["kid", "name"],
                                         "sort_column": ["name"], "sort_dir": ["asc"]})
    assert r.status_code == 200 and "<html" not in r.text
    assert "Quiz 1" in r.text and "Kid" in r.text and "Item" in r.text


def test_preview_shows_every_problem_instead_of_rows(tmp_path):
    seed(tmp_path).close()
    r = app_for(tmp_path).post("/reports/preview", data={"title": "", "source": "items"})
    assert r.status_code == 200
    assert "title cannot be empty" in r.text and "at least one column" in r.text
    assert "<table" not in r.text


def test_a_definition_that_cannot_be_read_opens_the_builder_with_a_problem(tmp_path):
    """A hand-edited row is a 400-shaped page, never a traceback: the builder is where it is fixed."""
    seed(tmp_path).close()
    conn = db.open_db(tmp_path)
    rid = store.create(conn, "Broken", "not json", now="2026-09-16T08:00:00-04:00")
    conn.close()
    r = app_for(tmp_path).get(f"/reports/{rid}")
    assert r.status_code == 200
    assert "could not be read" in r.text and 'name="columns"' in r.text
    conn = db.open_db(tmp_path)
    assert store.by_id(conn, rid)["definition"] == "not json"       # opening it wrote nothing
    conn.close()


def test_an_unknown_source_is_a_problem_not_a_500(tmp_path):
    """The builder used to subscript its column dict with the posted source; `nope` was a 500."""
    seed(tmp_path).close()
    c = app_for(tmp_path)
    r = c.post("/reports/new", data={"name": "Odd", "title": "Odd", "source": "nope", "columns": ["kid"]})
    assert r.status_code == 200 and "Unknown source" in r.text and "nope" in r.text
    assert 'name="group_by"' in r.text                              # the controls still rendered
    conn = db.open_db(tmp_path)
    assert store.all(conn) == []
    conn.close()


def test_save_round_trips_and_edits(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    r = c.post("/reports/new", data={"name": "Mine", "title": "Mine", "source": "items",
                                     "columns": ["kid", "name"], "orientation": "portrait"})
    assert r.status_code == 200 and "Saved" in r.text
    conn = db.open_db(tmp_path)
    (row,) = store.all(conn)
    conn.close()
    d = json.loads(row["definition"])
    assert d["columns"] == ["kid", "name"] and d["source"] == "items" and "nonsense" not in d
    r = c.post(f"/reports/{row['id']}", data={"name": "Renamed", "title": "Mine", "source": "items",
                                              "columns": ["kid", "name", "status"], "orientation": "landscape"})
    assert "Saved" in r.text
    conn = db.open_db(tmp_path)
    row = store.by_id(conn, row["id"])
    conn.close()
    assert row["name"] == "Renamed" and json.loads(row["definition"])["orientation"] == "landscape"


def test_the_builder_says_why_a_numeric_filter_on_a_date_column_is_refused(tmp_path):
    """`due >= 9/1` used to save happily and then match nothing at all; the page now says which
    column and which operator, both in the builder and in the live preview."""
    seed(tmp_path).close()
    c = app_for(tmp_path)
    data = {"name": "Late", "title": "Late", "source": "items", "columns": ["kid", "due"],
            "filter_field": ["due"], "filter_op": ["≥"], "filter_value": ["9/1"]}
    r = c.post("/reports/new", data=data)
    assert r.status_code == 200 and "cannot be filtered with" in r.text and "Due" in r.text
    assert "≥" in r.text
    conn = db.open_db(tmp_path)
    assert store.all(conn) == []
    conn.close()
    assert "cannot be filtered with" in c.post("/reports/preview", data=data).text


def test_save_refuses_an_invalid_definition_and_writes_nothing(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    r = c.post("/reports/new", data={"name": "Bad", "title": "Bad", "source": "items", "columns": []})
    assert r.status_code == 200 and "at least one column" in r.text
    conn = db.open_db(tmp_path)
    assert store.all(conn) == []
    conn.close()


def test_delete_removes_it(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path)
    c = _client(tmp_path)
    r = c.post(f"/reports/{rid}/delete")
    assert r.status_code == 200 and "Mine" not in r.text
    assert c.post(f"/reports/{rid}/delete").status_code == 404
    assert c.get(f"/reports/{rid}").status_code == 404


def test_deleting_a_scheduled_report_takes_its_schedule_with_it(tmp_path):
    """`reports.id` has no AUTOINCREMENT, so sqlite hands the next report this one's id. A
    schedule left behind would print the new report on the deleted one's days."""
    seed(tmp_path).close()
    rid = _save(tmp_path)
    sched = FakeScheduling()
    c = _client(tmp_path, sched)
    (tmp_path / "login-ok.txt").write_text("ok")
    schedules.save(f"view:{rid}", enabled=True, time="16:00", days=["Mon"], printer="Brother",
                   prints=True, home=tmp_path, log=lambda s: None, scheduling=sched)
    r = c.post(f"/reports/{rid}/delete")
    assert r.status_code == 200 and "Deleted" in r.text
    assert sched.removed == [f"view:{rid}"]
    assert f"view:{rid}" not in tomllib.loads((tmp_path / "config.toml").read_text()).get("reports", {})


def test_a_schedule_that_cannot_be_removed_stops_the_delete(tmp_path):
    """An orphan timer must never outlive its report's row, so the row stays until the timer
    is gone -- and the page says why."""
    seed(tmp_path).close()
    rid = _save(tmp_path)
    good = FakeScheduling()
    (tmp_path / "login-ok.txt").write_text("ok")
    schedules.save(f"view:{rid}", enabled=True, time="16:00", days=["Mon"], printer="Brother",
                   prints=True, home=tmp_path, log=lambda s: None, scheduling=good)
    c = _client(tmp_path, FakeScheduling(fail="Failed to connect to bus: No medium found"))
    r = c.post(f"/reports/{rid}/delete")
    assert r.status_code == 200 and "No medium found" in r.text and "Mine" in r.text
    conn = db.open_db(tmp_path)
    assert store.by_id(conn, rid) is not None
    conn.close()


def test_export_csv_and_json(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path, title="Mine", columns=["kid", "name"])
    c = app_for(tmp_path)
    r = c.get(f"/reports/{rid}/export.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "Mine" in r.headers["content-disposition"] and ".csv" in r.headers["content-disposition"]
    lines = r.text.strip().splitlines()
    assert lines[0] == "Kid,Item" and any("Quiz 1" in ln for ln in lines[1:])
    r = c.get(f"/reports/{rid}/export.json")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
    data = r.json()
    assert data["title"] == "Mine" and data["columns"] == ["kid", "name"]
    assert any(row["name"] == "Quiz 1" for row in data["rows"])
    assert c.get("/reports/999/export.csv").status_code == 404


def test_export_of_a_broken_definition_is_a_400(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path, columns=[])
    assert app_for(tmp_path).get(f"/reports/{rid}/export.csv").status_code == 400


def test_a_group_column_is_exported_once(tmp_path):
    """Grouped by a column the report also prints: the export must not repeat it."""
    seed(tmp_path).close()
    rid = _save(tmp_path, columns=["kid", "name"], group_by="kid")
    r = app_for(tmp_path).get(f"/reports/{rid}/export.csv")
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == ["Kid", "Item"]
    assert all(len(row) == 2 for row in rows if row)


def test_a_grouped_export_keeps_its_grouping(tmp_path):
    """Grouped by a column the report does not print: the PDF shows it as a heading, so the
    exports carry it as a column rather than handing back undifferentiated rows."""
    seed(tmp_path).close()
    rid = _save(tmp_path, columns=["name", "status"], group_by="kid")
    c = app_for(tmp_path)
    rows = [r for r in csv.reader(io.StringIO(c.get(f"/reports/{rid}/export.csv").text)) if r]
    assert rows[0] == ["Kid", "Item", "Status"]             # the group column first, once
    assert {r[0] for r in rows[1:]} == {"Alex", "Sam"}
    assert next(r for r in rows[1:] if r[1] == "Quiz 1")[0] == "Alex"

    data = c.get(f"/reports/{rid}/export.json").json()
    assert data["columns"] == ["name", "status"] and data["labels"] == ["Item", "Status"]
    assert data["group_by"] == "kid"
    assert [g["label"] for g in data["groups"]] == ["Alex", "Sam"]
    assert sum(len(g["rows"]) for g in data["groups"]) == len(data["rows"])
    assert any(row["name"] == "Quiz 1" for row in data["groups"][0]["rows"])


def test_csv_quotes_a_comma_keeps_non_ascii_and_never_breaks_the_filename(tmp_path):
    """Three things the reviewer checked by hand: a value with a comma round-trips through
    `csv.reader`, a non-ASCII character survives the download, and a hostile title cannot put
    a quote or a path separator into `Content-Disposition`."""
    snap = snapshot()
    for a in snap["students"]["Alex"]["canvas"]["courses"][0]["assignments"]:
        if a["name"] == "Quiz 1":
            a["name"] = "Quiz 1, café ½"
    seed(tmp_path, snap).close()
    rid = _save(tmp_path, title='Bad"; rm -rf /..\\name', columns=["kid", "name"])
    r = app_for(tmp_path).get(f"/reports/{rid}/export.csv")
    assert '"Quiz 1, café ½"' in r.text                     # quoted on the wire
    rows = list(csv.reader(io.StringIO(r.text)))
    assert ["Alex", "Quiz 1, café ½"] in rows            # and one cell again on the way back
    disposition = r.headers["content-disposition"]
    filename = disposition.split('filename="', 1)[1].split('"', 1)[0]      # the ASCII fallback; `filename*` follows
    assert filename.startswith("Bad rm -rf name ") and filename.endswith(".csv")
    assert not any(ch in filename for ch in '";/\\\r\n')


def test_the_builder_saves_a_custom_range(tmp_path):
    seed(tmp_path).close()
    c = _client(tmp_path)
    r = c.post("/reports/new", data={"title": "Recap", "source": "items", "columns": ["kid", "name"],
                                     "window": "custom", "date_from": "2026-09-01", "date_to": "2026-09-15"})
    assert r.status_code == 200 and "Saved." in r.text
    body = c.get("/reports/1").text
    assert 'name="date_from" value="2026-09-01"' in body and 'name="date_to" value="2026-09-15"' in body


def test_the_builder_shows_the_custom_range_problem(tmp_path):
    seed(tmp_path).close()
    c = _client(tmp_path)
    r = c.post("/reports/new", data={"title": "Recap", "source": "items", "columns": ["kid", "name"],
                                     "window": "custom", "date_from": "2026-09-15", "date_to": "2026-09-01"})
    assert "on or before" in r.text


def test_a_saved_chart_report_shows_a_canvas_and_its_config(tmp_path):
    seed(tmp_path).close()
    c = _client(tmp_path)
    rid = _save(tmp_path, source="items", columns=["kid", "name", "due"],
               chart={"type": "bar", "x": "due", "y": None, "bucket": "week"})
    body = c.get(f"/reports/{rid}/view").text
    assert "data-report-chart" in body and "data-chart-config" in body
    assert '"type": "bar"' in body or '"type":"bar"' in body


def test_a_table_only_report_shows_no_chart_markup(tmp_path):
    seed(tmp_path).close()
    c = _client(tmp_path)
    rid = _save(tmp_path, source="items", columns=["kid", "name"])
    body = c.get(f"/reports/{rid}/view").text
    assert "data-report-chart" not in body


def test_chart_json_escapes_a_label_that_would_close_the_script_tag():
    """A series label can come straight from a course or assignment name -- untrusted the same
    way `sheet.py`'s `_esc()` and the CSV formula-injection guard already treat those names.
    Inlined into `<script type="application/json">` with a bare `json.dumps`, a label of
    literal `</script>` would close the element early in the browser's HTML parser; `_chart_json`
    must escape it so the string is safe to inline as-is."""
    evil = "</script><script>alert(1)</script>"
    chart = views.ChartData(type="bar", x_label="Due", y_label="Count",
                            series=[views.ChartSeries(label=evil, points=[("W1", 3.0)])],
                            labels=("W1",))
    rendered = views.Rendered(title="T", columns=[], groups=[], chart=chart)
    out = _chart_json(rendered)
    assert "</script>" not in out
    assert "<script>" not in out
    # still valid, round-tripping JSON once the escapes are undone by JSON.parse
    assert json.loads(out.replace("\\u003c", "<").replace("\\u003e", ">"))["data"]["datasets"][0]["label"] == evil
