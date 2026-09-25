"""#94: a saved report chooses its date window, and its dates say the year when it is not
this one and, for changes, the time of day."""
from __future__ import annotations

import json
from datetime import datetime

from fridgesheet.web import db, views
from fridgesheet.web.stores import reports as store
from tests.web_fixtures import NOW, TZ, app_for, seed


def _client(home):
    return app_for(home)


def _save(home, **d):
    conn = db.open_db(home)
    rid = store.create(conn, "Mine", json.dumps({"title": "Mine", "source": "items", "columns": ["name", "due"], **d}),
                       now="2026-09-16T08:00:00-04:00")
    conn.close()
    return rid


def _names(c, rid):
    return {r["name"] for r in c.get(f"/reports/{rid}/export.json").json()["rows"]}


def test_a_definition_carries_its_window_and_defaults_to_any_time():
    assert views.defaults().window == "all"
    d = views.from_json(json.dumps({"source": "items", "window": "7d"}))
    assert d.window == "7d" and json.loads(d.to_json())["window"] == "7d"
    assert views.from_json(json.dumps({"source": "items"})).window == "all"      # stored before #94
    assert any("window" in p.lower() for p in views.validate(views.Definition(title="x", columns=("name",), window="fortnight")))


def test_an_items_report_keeps_work_due_inside_its_window(tmp_path):
    """Homework 4 was due 8/20, Participation 9/8; a 7-day window from 9/15 starts 9/8."""
    seed(tmp_path).close()
    c = _client(tmp_path)
    everything = _names(c, _save(tmp_path))
    week = _names(c, _save(tmp_path, window="7d"))
    assert "Homework 4" in everything and "Homework 4" not in week
    assert "Participation" in week and "Reading log" in week                 # due in the future is inside it


def test_a_changes_report_starts_where_its_window_does(tmp_path):
    seed(tmp_path).close()
    c = _client(tmp_path)
    rid = _save(tmp_path, source="changes", columns=["at", "what", "item"], window="7d")
    rows = c.get(f"/reports/{rid}/export.json").json()["rows"]
    assert rows                                                              # the fixture's refresh is inside a week
    rid2 = _save(tmp_path, source="changes", columns=["at", "what", "item"], window="school_year")
    assert len(c.get(f"/reports/{rid2}/export.json").json()["rows"]) >= len(rows)


def test_the_builder_offers_the_window(tmp_path):
    seed(tmp_path).close()
    c = _client(tmp_path)
    body = c.get("/reports/new").text
    assert 'name="window"' in body and "The last 7 days" in body and "This school year" in body
    r = c.post("/reports/builder", data={"title": "Mine", "source": "changes", "columns": ["at"], "window": "30d"})
    assert 'value="30d" selected' in r.text


def test_dates_carry_the_year_only_when_it_is_not_this_one():
    now = datetime(2026, 9, 15, 14, 0, tzinfo=TZ)
    assert views._date(datetime(2026, 9, 8, 23, 59, tzinfo=TZ), now=now) == "9/8"
    assert views._date(datetime(2025, 6, 2, 23, 59, tzinfo=TZ), now=now) == "6/2/2025"


def test_a_change_says_the_time_it_happened(tmp_path):
    seed(tmp_path).close()
    c = _client(tmp_path)
    rid = _save(tmp_path, source="changes", columns=["at", "what"])
    at = c.get(f"/reports/{rid}/export.json").json()["rows"][0]["at"]
    assert at.startswith("9/15 ") and at.endswith(("AM", "PM"))


def test_a_limited_report_says_so_on_the_page(tmp_path):
    seed(tmp_path).close()
    c = _client(tmp_path)
    assert "Rows from: the last 7 days" in c.get(f"/reports/{_save(tmp_path, window='7d')}/view").text
    assert "Rows from" not in c.get(f"/reports/{_save(tmp_path)}/view").text


def test_a_custom_range_needs_both_dates_in_order():
    ok = views.Definition(title="x", columns=("name",), window="custom",
                          date_from="2026-09-01", date_to="2026-09-15")
    assert views.validate(ok) == []
    missing = views.Definition(title="x", columns=("name",), window="custom", date_from="2026-09-01")
    assert any("start and an end date" in p for p in views.validate(missing))
    backwards = views.Definition(title="x", columns=("name",), window="custom",
                                 date_from="2026-09-15", date_to="2026-09-01")
    assert any("on or before" in p for p in views.validate(backwards))
    garbage = views.Definition(title="x", columns=("name",), window="custom",
                               date_from="not-a-date", date_to="2026-09-15")
    assert any("start and an end date" in p for p in views.validate(garbage))


def test_a_custom_range_round_trips_through_json():
    d = views.from_json(json.dumps({"source": "items", "window": "custom",
                                    "date_from": "2026-09-01", "date_to": "2026-09-15"}))
    assert d.window == "custom" and d.date_from == "2026-09-01" and d.date_to == "2026-09-15"
    back = json.loads(d.to_json())
    assert back["date_from"] == "2026-09-01" and back["date_to"] == "2026-09-15"


def test_window_start_reads_the_custom_range():
    d = views.Definition(window="custom", date_from="2026-09-01", date_to="2026-09-15")
    start = views.window_start(d, NOW)
    assert start is not None and (start.month, start.day) == (9, 1)


def test_a_custom_range_bounds_items_by_due_date(tmp_path):
    seed(tmp_path).close()
    c = _client(tmp_path)
    names = _names(c, _save(tmp_path, window="custom", date_from="2026-09-10", date_to="2026-09-14"))
    assert "Homework 4" not in names           # due 8/20, before the range
    assert "Reading log" not in names          # due 9/20, after the range
    assert "Lab notebook" in names             # due 9/10, the range's first day


def test_a_custom_range_bounds_changes_by_when_they_happened(tmp_path):
    seed(tmp_path).close()
    c = _client(tmp_path)
    rid = _save(tmp_path, source="changes", columns=["at", "kid", "what"],
               window="custom", date_from="2026-01-01", date_to="2026-09-01")
    body = c.get(f"/reports/{rid}/view").text
    assert "No rows matched this report." in body   # every seeded change happens after 9/1

    # A range that actually spans the seeded refresh (9/15) must not also exclude everything --
    # the assertion above alone would still pass if the end bound accidentally excluded every
    # row rather than just the out-of-range ones.
    rid2 = _save(tmp_path, source="changes", columns=["at", "kid", "what"],
                window="custom", date_from="2026-09-14", date_to="2026-09-16")
    rows = c.get(f"/reports/{rid2}/export.json").json()["rows"]
    assert rows                                          # at least one real event falls inside the range
    assert any(r["what"] for r in rows)


def test_a_custom_range_bounds_grades_by_when_they_were_observed(tmp_path):
    """A grade observation's `at` is the refresh it was seen on, not the course's own field --
    mirroring test_a_custom_range_bounds_items_by_due_date's pattern of checking a specific
    value, not just a row count, on both sides of the boundary."""
    from tests.web_fixtures import snapshot
    early = snapshot()
    early["fetched_at"] = "2026-08-01T08:00:00-04:00"
    seed(tmp_path, early, now=datetime(2026, 8, 1, 8, 0, tzinfo=TZ)).close()
    later = snapshot()
    later["fetched_at"] = "2026-09-10T08:00:00-04:00"
    later["students"]["Alex"]["canvas"]["courses"][0]["grade"]["current_score"] = 95.5
    seed(tmp_path, later, now=datetime(2026, 9, 10, 8, 0, tzinfo=TZ)).close()
    c = _client(tmp_path)
    rid = _save(tmp_path, source="grades", columns=["course", "source", "value", "at"],
               window="custom", date_from="2026-09-05", date_to="2026-09-15")
    rows = c.get(f"/reports/{rid}/export.json").json()["rows"]
    values = {r["value"] for r in rows}
    assert "91.2" not in values          # the original score, observed 8/1, before the range
    assert "95.5" in values              # the updated score, observed 9/10, inside the range


def test_the_preview_names_a_custom_range(tmp_path):
    seed(tmp_path).close()
    c = _client(tmp_path)
    rid = _save(tmp_path, window="custom", date_from="2026-09-01", date_to="2026-09-15")
    body = c.get(f"/reports/{rid}/view").text
    assert "custom range" in body and "9/1" in body and "9/15" in body
