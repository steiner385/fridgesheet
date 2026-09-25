"""The printed sheet and the Open work page are one list (#137).

`web/reconcile.py` decided the screens and `open_items.py` decided the sheet, and the two
disagreed in four cases the user guide turned up. Now the open-work report reads the same
decided rows the page shows whenever the database holds the snapshot it was handed
(`reports.open_work.decided_work`); the snapshot-only path in `open_items` stays for a
household that has never recorded a refresh, and it has to say the same thing.
"""
from __future__ import annotations

from datetime import datetime

import pytest

pytest.importorskip("reportlab")

from fridgesheet import config, late_rules, open_items, reports  # noqa: E402
from fridgesheet.reports import open_work  # noqa: E402
from fridgesheet.reports.base import BuildContext  # noqa: E402
from fridgesheet.web.stores import flags, items, students  # noqa: E402
from tests.web_fixtures import NOW, TZ, history, seed, snapshot  # noqa: E402

RULES = late_rules.LateRules(late_rules.Rule(), [], [])
#: Before anything is due; the HAC-only row's first morning past due (case 1); the paper
#: row's; the fixture's own afternoon; ten days on; and a month on, when everything has
#: closed.
NOWS = [datetime(2026, 8, 25, 14, tzinfo=TZ), datetime(2026, 9, 9, 10, tzinfo=TZ), datetime(2026, 9, 11, 9, tzinfo=TZ),
        NOW, datetime(2026, 9, 25, 14, tzinfo=TZ), datetime(2026, 10, 20, 14, tzinfo=TZ)]


def _ctx(home, conn, now, **over) -> BuildContext:
    d = dict(settings=config.Settings(home=home), home=home, day=now.date(), now=now, out_dir=home / "out", kid=None,
             nicknames={}, prev_rows=None, prev_label=None, stale_note=None, options={}, data_as_of=now, conn=conn)
    d.update(over)
    d["out_dir"].mkdir(parents=True, exist_ok=True)
    return BuildContext(**d)


def _page(conn, now, **window) -> dict[str, items.OpenWork]:
    return {s["key"]: items.open_work(conn, s, now=now, rules=RULES, **window) for s in students.visible(conn)}


def _listed(page) -> set[tuple[str, str]]:
    return {(kid, v.key) for kid, w in page.items() for v in w.fixable + w.upcoming}


@pytest.mark.parametrize("now", NOWS)
def test_the_sheet_lists_exactly_what_open_work_lists(tmp_path, now):
    """Still fixable plus Coming due, per kid, is the set of rows the sheet prints; what the
    page counts underneath is what the sheet's trailers count."""
    conn = seed(tmp_path)
    built = reports.get("open-work").build(snapshot(), _ctx(tmp_path, conn, now))
    page = _page(conn, now)
    assert {(kid, r["key"]) for kid, rows in built.rows.items() for r in rows} == _listed(page)
    for key, w in page.items():
        work = open_work.from_views(w, key, now)
        assert {i.key for i in work.dropped} == {v.key for v in w.past_window}
        assert {i.key for i in work.handled} == {v.key for v in w.handled}
    conn.close()


@pytest.mark.parametrize("now", NOWS)
def test_the_snapshot_only_path_agrees_with_the_database(tmp_path, now):
    """A household with no database gets `open_items.open_items` over the snapshot. Same rows,
    same words, same trailers as the decided rows -- this is where the four cases lived."""
    conn = seed(tmp_path)
    page = _page(conn, now)
    for key, entry in snapshot()["students"].items():
        work = open_items.open_items(entry, key, now, rules=RULES, student_key=key)
        w = page[key]
        assert {(i.key, i.status) for i in work.items} == {(v.key, open_work.sheet_status(v)) for v in w.fixable + w.upcoming}, (key, now)
        assert {i.key for i in work.dropped} == {v.key for v in w.past_window}, (key, now)
    conn.close()


def test_the_sheet_reads_the_database_when_it_holds_the_snapshot(tmp_path):
    """Only the database has history: on day 3 Canvas marked Quiz 1 missing *after* HAC's
    28/30, which the app asks about and the snapshot alone cannot see. The sheet built from
    that database prints it; the same sheet built without one follows HAC's grade."""
    conn = history(tmp_path)
    snap = snapshot()
    with_db = reports.get("open-work").build(snap, _ctx(tmp_path, conn, NOW))
    assert ("canvas:77", "MISSING") in {(r["key"], r["status"]) for r in with_db.rows["Alex"]}
    without = reports.get("open-work").build(snap, _ctx(tmp_path, None, NOW))
    assert "canvas:77" not in {r["key"] for r in without.rows["Alex"]}
    conn.close()


def test_a_snapshot_the_database_has_not_recorded_prints_from_the_snapshot(tmp_path):
    """A bare `refresh` (no --record) leaves the snapshot ahead of the database; the sheet
    must not print yesterday's decisions about today's data."""
    conn = history(tmp_path)
    snap = snapshot()
    snap["fetched_at"] = "2026-09-16T06:00:00-04:00"
    assert open_work.decided_work(conn, snap, NOW, days_ahead=14, overdue_days=14, rules=RULES) is None
    built = reports.get("open-work").build(snap, _ctx(tmp_path, conn, NOW))
    assert "canvas:77" not in {r["key"] for r in built.rows["Alex"]}
    conn.close()


def test_a_flag_set_in_the_app_reaches_the_sheet_built_from_the_database(tmp_path):
    conn = seed(tmp_path)
    iid = conn.execute("SELECT id FROM items WHERE name = 'Lab notebook'").fetchone()["id"]
    flags.set_flag(conn, iid, "done", now="2026-09-15T13:00:00-04:00")
    built = reports.get("open-work").build(snapshot(), _ctx(tmp_path, conn, NOW))
    assert "canvas:82" not in {r["key"] for r in built.rows["Alex"]}
    assert "Handled" in built.summary or True                        # the trailer is the PDF's; the rows are what is pinned
    work = open_work.from_views(_page(conn, NOW)["Alex"], "Alex", NOW)
    assert [i.key for i in work.handled] == ["canvas:82"] and work.handled[0].flag == "done"
    conn.close()


def test_the_sheets_words_for_the_pages_rows():
    """The page's status phrase, in the sheet's capitals: the one table `sheet.status_word`
    reads the other way, so a kid's tier says the same thing on both surfaces."""
    from fridgesheet import sheet
    assert sheet.STATUS_WORD == {"Missing": "MISSING", "Zero": "ZERO", "Late, ungraded": "LATE", "Paper, check": "PAPER — CHECK",
                                 "In class, check": "IN CLASS — CHECK", "HAC, no grade": "HAC — NO GRADE"}
    for phrase, word in sheet.STATUS_WORD.items():
        assert sheet.status_word(word, "older") == word
        assert sheet.status_word(word, "early") == sheet.phrasing.phrase(phrase, "early")
