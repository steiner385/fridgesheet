"""A view definition: what it accepts, what it refuses, and the rows it renders."""
from __future__ import annotations

import json

import pytest

from fridgesheet import late_rules
from fridgesheet.web import views
from fridgesheet.web.stores import reports as reportstore, students
from tests.web_fixtures import NOW, history, seed, snapshot

RULES = late_rules.LateRules(late_rules.Rule(), [], [])


def _build(conn, d):
    return views.build(conn, d, now=NOW, rules=RULES, nicknames={"Alex": "Al"})


def test_defaults_are_valid_and_round_trip():
    d = views.defaults()
    assert d.source == "items" and d.columns and views.validate(d) == []
    again = views.from_json(d.to_json())
    assert again == d


def test_from_json_drops_unknown_keys_and_fills_missing():
    d = views.from_json('{"source": "grades", "nonsense": 1}')
    assert d.source == "grades" and d.orientation == "portrait" and not d.scope
    with pytest.raises(views.ViewError):
        views.from_json("not json")
    with pytest.raises(views.ViewError):
        views.from_json('["a list"]')


def test_from_json_reads_per_kid_sections_honestly():
    # A real JSON bool stays itself...
    assert views.from_json('{"source": "items", "per_kid_sections": true}').per_kid_sections is True
    # ...and a JSON string reads as its own word: "false" must not become truthy just because
    # it is a non-empty string (`bool("false")` is `True`, which is the bug being guarded here).
    assert views.from_json('{"source": "items", "per_kid_sections": "false"}').per_kid_sections is False


def test_validate_stops_at_an_unknown_source():
    # The builder only ever posts a `<select>`, so an unknown source is reachable solely by a
    # hand-made request -- and once the source is wrong, "kid" is not a bad column, it simply
    # is not a column of a source that does not exist, so nothing else should be reported.
    d = views.from_json(json.dumps({**json.loads(views.defaults().to_json()),
                                    "source": "nope", "columns": ["kid", "bogus"],
                                    "filters": [{"field": "kid", "op": "~", "value": "x"}],
                                    "group_by": "bogus", "sort": [{"column": "bogus", "dir": "sideways"}],
                                    "orientation": "diagonal"}))
    problems = views.validate(d)
    assert problems == [f"Unknown source 'nope'; choose one of {', '.join(views.SOURCES)}."]


def test_validate_names_every_problem():
    d = views.defaults()
    bad = views.from_json(json.dumps({**json.loads(d.to_json()),
                                      "columns": ["kid", "bogus"],
                                      "filters": [{"field": "kid", "op": "~", "value": "x"}],
                                      "group_by": "bogus", "sort": [{"column": "bogus", "dir": "sideways"}],
                                      "orientation": "diagonal", "title": ""}))
    problems = views.validate(bad)
    assert len(problems) >= 6
    assert any("bogus" in p for p in problems)
    assert any("~" in p for p in problems) and any("sideways" in p for p in problems)
    assert any("orientation" in p.lower() for p in problems) and any("title" in p.lower() for p in problems)
    assert all(p.endswith(".") for p in problems)


def test_validate_rejects_an_empty_column_list():
    d = views.from_json('{"source": "items", "columns": []}')
    assert any("at least one column" in p for p in views.validate(d))


def test_validate_rejects_a_numeric_operator_on_a_text_or_date_column(tmp_path):
    """`_keep` can only answer >= by reading both sides as numbers, so `due >= 9/1` would drop
    every row and the page would say "No rows matched" with no reason. It is a problem instead."""
    for field, op in (("due", "≥"), ("name", "≤")):
        d = views.from_json(json.dumps({"source": "items", "columns": ["kid", "name"],
                                        "filters": [{"field": field, "op": op, "value": "9/1"}]}))
        problems = views.validate(d)
        (p,) = [x for x in problems if op in x]
        assert views.COLUMNS["items"][field].label in p and p.endswith(".")
    ok = views.from_json(json.dumps({"source": "items", "columns": ["kid", "points"],
                                     "filters": [{"field": "points", "op": "≥", "value": "10"}]}))
    assert views.validate(ok) == []


def test_items_source_renders_rows_a_parent_reads(tmp_path):
    conn = seed(tmp_path)
    d = views.from_json(json.dumps({"title": "Open work", "source": "items",
                                    "columns": ["kid", "course", "name", "status", "due"],
                                    "filters": [{"field": "open", "op": "is", "value": "yes"}],
                                    "sort": [{"column": "due", "dir": "asc"}]}))
    r = _build(conn, d)
    assert [c.id for c in r.columns] == ["kid", "course", "name", "status", "due"]
    assert len(r.groups) == 1 and r.groups[0].label == ""
    names = [row["name"] for row in r.groups[0].rows]
    assert "Homework 4" in names and "Essay draft" not in names        # submitted: not open
    assert "Quiz 1" not in names                                       # HAC's 28/30 settles it
    row = next(x for x in r.groups[0].rows if x["name"] == "Homework 4")
    assert row["kid"] == "Al" and row["course"] == "Algebra I" and row["status"] == "Missing"
    assert row["due"] == "8/20" and all(isinstance(v, str) for v in row.values())
    conn.close()


def test_scope_limits_the_kids(tmp_path):
    conn = seed(tmp_path)
    d = views.from_json(json.dumps({"source": "items", "columns": ["kid", "name"], "scope": ["Sam"]}))
    assert {row["kid"] for row in _build(conn, d).groups[0].rows} == {"Sam"}
    conn.close()


def test_group_by_splits_and_labels(tmp_path):
    conn = seed(tmp_path)
    d = views.from_json(json.dumps({"source": "items", "columns": ["kid", "course", "name"], "group_by": "kid"}))
    r = _build(conn, d)
    assert [g.label for g in r.groups] == ["Al", "Sam"]
    assert all(g.rows for g in r.groups)
    conn.close()


def test_filters_by_every_operator(tmp_path):
    conn = seed(tmp_path)
    def rows(f):
        d = views.from_json(json.dumps({"source": "items", "columns": ["name", "points", "course"], "filters": [f]}))
        return [x["name"] for x in _build(conn, d).groups[0].rows]
    assert "Quiz 1" in rows({"field": "course", "op": "contains", "value": "English"})
    assert "Cell diagram" not in rows({"field": "course", "op": "contains", "value": "English"})
    assert rows({"field": "name", "op": "is", "value": "Quiz 1"}) == ["Quiz 1"]
    assert "Quiz 1" not in rows({"field": "name", "op": "is not", "value": "Quiz 1"})
    assert "Quiz 1" in rows({"field": "points", "op": "≥", "value": "30"})
    assert "Quiz 1" not in rows({"field": "points", "op": "≤", "value": "10"})
    conn.close()


def test_sort_is_applied_in_order(tmp_path):
    conn = seed(tmp_path)
    d = views.from_json(json.dumps({"source": "items", "columns": ["kid", "name"],
                                    "sort": [{"column": "kid", "dir": "desc"}, {"column": "name", "dir": "asc"}]}))
    rows = _build(conn, d).groups[0].rows
    assert rows[0]["kid"] == "Sam"
    sam = [r["name"] for r in rows if r["kid"] == "Sam"]
    assert sam == sorted(sam)
    conn.close()


def test_the_open_work_starter_sorts_dates_in_real_order(tmp_path):
    """The shipped starter sorts `due asc`. Sorted as display text, "9/8" lands after "9/20" and
    the printed sheet disagrees with the Kid page about what is most overdue."""
    conn = seed(tmp_path)
    (name, definition), = [t for t in reportstore.TEMPLATES if t[1]["source"] == "items"
                           and t[1].get("filters")]
    r = _build(conn, views.from_json(json.dumps(definition)))
    for g in r.groups:
        due = [row["due"] for row in g.rows]
        assert due == sorted(due, key=lambda s: tuple(int(p) for p in s.split("/"))), f"{name}: {due}"
    al = next(g for g in r.groups if g.label == "Al")
    order = [row["due"] for row in al.rows]
    assert order.index("9/8") < order.index("9/20") and order[0] == "8/20"
    conn.close()


def test_a_number_sort_orders_9_before_10(tmp_path):
    """Points sorted as text put "10" before "9"; a number column sorts as a number."""
    snap = snapshot()
    for a in snap["students"]["Alex"]["canvas"]["courses"][0]["assignments"]:
        if a["name"] == "Reading log":
            a["points_possible"] = 9.0
    conn = seed(tmp_path, snap)
    d = views.from_json(json.dumps({"source": "items", "columns": ["name", "points"],
                                    "sort": [{"column": "points", "dir": "asc"}]}))
    points = [row["points"] for row in _build(conn, d).groups[0].rows]
    assert points[0] == "9" and points[-1] == "30"
    assert points == sorted(points, key=lambda p: float(p or 0))
    conn.close()


def test_build_reports_the_rows_its_own_cap_dropped(tmp_path, monkeypatch):
    """`MAX_ROWS` in `build` itself, not the changes store's cap: an items report past the cap
    keeps the first `MAX_ROWS` rows and says how many it left out."""
    conn = seed(tmp_path)
    d = views.from_json(json.dumps({"source": "items", "columns": ["kid", "name"]}))
    total = len(_build(conn, d).groups[0].rows)
    assert total > 3
    monkeypatch.setattr(views, "MAX_ROWS", 3)
    r = _build(conn, d)
    assert len(r.groups[0].rows) == 3 and r.truncated == total - 3
    conn.close()


def test_grades_source(tmp_path):
    conn = history(tmp_path)
    d = views.from_json(json.dumps({"source": "grades", "columns": ["kid", "course", "source", "value", "at"]}))
    rows = _build(conn, d).groups[0].rows
    assert any(r["course"] == "Honors English 9" and r["source"] == "hac" and r["value"] == "88" for r in rows)
    assert all(r["at"] for r in rows)
    conn.close()


def test_changes_source(tmp_path):
    conn = history(tmp_path)
    d = views.from_json(json.dumps({"source": "changes", "columns": ["at", "kid", "what", "item", "detail"]}))
    rows = _build(conn, d).groups[0].rows
    assert any(r["what"] == "Grade posted" and r["item"] == "Quiz 1" for r in rows)
    conn.close()


def test_changes_source_reports_what_the_store_cap_dropped(tmp_path, monkeypatch):
    # `history` produces far fewer than 2000 events, so the cap is lowered instead (rather than
    # seeding 2000 rows) to prove `_change_rows`'s `feed.dropped` reaches `Rendered.truncated`.
    conn = history(tmp_path)
    monkeypatch.setattr(views, "MAX_ROWS", 2)
    d = views.from_json(json.dumps({"source": "changes", "columns": ["at", "kid", "what"]}))
    r = _build(conn, d)
    assert r.truncated > 0
    conn.close()


def test_an_empty_result_still_renders_columns(tmp_path):
    conn = seed(tmp_path)
    d = views.from_json(json.dumps({"source": "items", "columns": ["kid", "name"],
                                    "filters": [{"field": "name", "op": "is", "value": "nothing at all"}]}))
    r = _build(conn, d)
    assert [c.id for c in r.columns] == ["kid", "name"] and r.groups == []
    conn.close()


def test_build_refuses_an_invalid_definition(tmp_path):
    conn = seed(tmp_path)
    d = views.from_json('{"source": "items", "columns": []}')
    with pytest.raises(views.ViewError):
        _build(conn, d)
    conn.close()


def test_the_verdict_column_is_named_for_parents_and_says_where_it_stands(tmp_path):
    """Deferred finding 8: the column was labelled "Reconcile" and showed a raw verdict kind."""
    assert views.COLUMNS["items"]["cases"].label == "Where it stands"
    conn = seed(tmp_path)
    d = views.from_json(json.dumps({"title": "Questions", "source": "items", "columns": ["name", "cases"],
                                    "filters": [], "sort": [{"column": "name", "dir": "asc"}]}))
    rows = {row["name"]: row["cases"] for row in _build(conn, d).groups[0].rows}
    assert rows["Participation"] == "No grade, longer than usual"
    assert rows["Quiz 1"] == "Done · 28 of 30 in HAC"
    assert "_" not in "".join(rows.values())
