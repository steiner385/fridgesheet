"""#97: an item's identity across two sections of one class, and across a class renamed vs. a
new section appearing beside it."""
from __future__ import annotations

import copy
from datetime import date, timedelta

from fridgesheet import open_items
from fridgesheet.matching import hac_only_key
from fridgesheet.web import db, ingest
from fridgesheet.web.stores import flags as flagstore
from tests.web_fixtures import NOW, TZ, _h, seed, snapshot


def _two_sections():
    """Alex in two HAC sections of Algebra with a same-named, ungraded homework in each."""
    snap = snapshot()
    classes = snap["students"]["Alex"]["hac"]["classes"]
    classes.append({"name": "Algebra I - 3", "assignments": [_h("Homework 5", "09/10/2026", None)]})
    alg = next(c for c in classes if c["name"] == "Algebra I - 2")
    alg["assignments"].append(_h("Homework 5", "09/10/2026", None))
    return snap


def test_a_flag_on_one_section_does_not_strike_the_other_off_the_sheet(tmp_path):
    """Both sections' homework has the key `hac:Algebra I:homework 5:2026-09-10`; the sheet
    looked flags up by key alone, so marking one done removed both."""
    snap = _two_sections()
    conn = seed(tmp_path, snap)
    key = hac_only_key("Algebra I - 2", "Homework 5", date(2026, 9, 10))
    iid = conn.execute("""SELECT i.id FROM items i JOIN courses c ON c.id = i.course_id
                          WHERE i.key = ? AND c.name = 'Algebra I - 2'""", (key,)).fetchone()["id"]
    flagstore.set_flag(conn, iid, "done", now="2026-09-15T13:00:00-04:00")
    flags = flagstore.active_by_student(conn)["Alex"]
    conn.close()
    work = open_items.open_items(snap["students"]["Alex"], "Alex", NOW, flags=flags)
    handled = [(i.course, i.name) for i in work.handled if i.name == "Homework 5"]
    shown = [i for i in work.items + work.dropped if i.name == "Homework 5"]
    assert len(handled) == 1 and len(shown) == 1


def test_a_plain_key_flag_still_applies(tmp_path):
    """Callers that hand `open_items` a flat {key: flag} (the MCP server, older tests) keep
    working; only the store's own map is course-qualified."""
    snap = snapshot()
    key = hac_only_key("Honors English 9 S1", "Participation", date(2026, 9, 8))
    work = open_items.open_items(snap["students"]["Alex"], "Alex", NOW, flags={key: "done"})
    assert any(i.name == "Participation" for i in work.handled)


def test_a_new_section_listed_first_does_not_take_the_old_sections_history(tmp_path):
    """A new section of the same class, with a same-named assignment, arriving ahead of the
    old one used to claim the old item (the rename fallback) and leave the old section a
    fresh item with no flags, notes or history."""
    snap = _two_sections()
    classes = snap["students"]["Alex"]["hac"]["classes"]
    classes[:] = [c for c in classes if c["name"] != "Algebra I - 3"]     # first refresh: one section
    conn = seed(tmp_path, snap)
    key = hac_only_key("Algebra I - 2", "Homework 5", date(2026, 9, 10))
    before = conn.execute("SELECT i.id, i.first_seen FROM items i WHERE i.key = ?", (key,)).fetchone()

    later = copy.deepcopy(snap)
    later["fetched_at"] = "2026-09-16T13:50:00-04:00"
    later["students"]["Alex"]["hac"]["classes"].insert(
        0, {"name": "Algebra I - 3", "assignments": [_h("Homework 5", "09/10/2026", None)]})
    ingest.record(conn, later, tz=TZ, now=NOW + timedelta(days=1))
    rows = {r["course"]: (r["id"], r["first_seen"]) for r in conn.execute(
        """SELECT c.name AS course, i.id, i.first_seen FROM items i JOIN courses c ON c.id = i.course_id
           WHERE i.key = ?""", (key,))}
    conn.close()
    assert rows["Algebra I - 2"] == (before["id"], before["first_seen"])   # the old section keeps its item
    assert rows["Algebra I - 3"][0] != before["id"]                        # the new one gets its own


def test_a_renamed_class_still_carries_its_items_over(tmp_path):
    snap = _two_sections()
    classes = snap["students"]["Alex"]["hac"]["classes"]
    classes[:] = [c for c in classes if c["name"] != "Algebra I - 3"]
    conn = seed(tmp_path, snap)
    key = hac_only_key("Algebra I - 2", "Homework 5", date(2026, 9, 10))
    before = conn.execute("SELECT id FROM items WHERE key = ?", (key,)).fetchone()["id"]
    later = copy.deepcopy(snap)
    later["fetched_at"] = "2026-09-16T13:50:00-04:00"
    alg = next(c for c in later["students"]["Alex"]["hac"]["classes"] if c["name"] == "Algebra I - 2")
    alg["name"] = "Algebra I - 2 S1"                                        # renamed; the old name is gone, the key is not
    ingest.record(conn, later, tz=TZ, now=NOW + timedelta(days=1))
    moved = conn.execute("""SELECT c.name FROM items i JOIN courses c ON c.id = i.course_id WHERE i.id = ?""",
                         (before,)).fetchone()["name"]
    conn.close()
    assert moved == "Algebra I - 2 S1"


def test_a_flag_on_one_of_two_same_named_rows_in_a_class_reaches_the_sheet(tmp_path):
    """The database keys two same-named HAC rows in one class by their due dates; the sheet
    used the bare key, so a flag on either never matched a printed row."""
    snap = snapshot()
    alg = next(c for c in snap["students"]["Alex"]["hac"]["classes"] if c["name"] == "Algebra I - 2")
    alg["assignments"] += [_h("Warm-up", "09/08/2026", None), _h("Warm-up", "09/10/2026", None)]
    conn = seed(tmp_path, snap)
    first = conn.execute("SELECT id, key FROM items WHERE name = 'Warm-up' ORDER BY due LIMIT 1").fetchone()
    assert first["key"].endswith(":2026-09-08")
    flagstore.set_flag(conn, first["id"], "done", now="2026-09-15T13:00:00-04:00")
    flags = flagstore.active_by_student(conn)["Alex"]
    conn.close()
    work = open_items.open_items(snap["students"]["Alex"], "Alex", NOW, flags=flags)
    assert [i.due.day for i in work.handled if i.name == "Warm-up"] == [8]
    assert [i.due.day for i in work.items + work.dropped if i.name == "Warm-up"] == [10]
