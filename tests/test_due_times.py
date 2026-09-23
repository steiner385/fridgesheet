"""The time an assignment is actually due, wherever a due date is shown.

A parent's son put it best: "due 8 in the morning" and "due 11:59 at night" are the
difference between finishing it tonight and having tomorrow evening for it. The web app
showed neither -- only the date -- while the printed sheet had been showing the time all
along whenever it was not 23:59. These pin the one rule both surfaces now share.

The rule turns on where the time came from. Canvas gives a real timestamp, so 23:59 there
means a teacher set 11:59 PM. HAC gives a date with no time at all, and ingest stores it as
23:59 (`web/ingest.py`, `open_items.py`) -- so a HAC-only item's time is the app's own
invention and is never shown as though the school had said it.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from fridgesheet.dates import due_time

TZ = ZoneInfo("America/New_York")


def _at(h: int, m: int = 0) -> datetime:
    return datetime(2026, 9, 26, h, m, tzinfo=TZ)


# --- the rule itself ------------------------------------------------------------------

@pytest.mark.parametrize("h,m,expected", [
    (7, 20, "7:20am"),      # the morning deadline this exists for
    (9, 55, "9:55am"),
    (15, 0, "3pm"),         # a round hour drops its ":00"
    (14, 10, "2:10pm"),
    (12, 30, "12:30pm"),    # noon is 12, not 0
    (0, 5, "12:05am"),      # midnight is 12, not 0
    (23, 59, "11:59pm"),    # a real Canvas end-of-day deadline, said out loud
])
def test_a_canvas_time_is_shown_compactly(h, m, expected):
    assert due_time(_at(h, m), from_canvas=True) == expected


def test_a_hac_only_item_never_shows_a_time():
    """HAC hands over a date and nothing else; the 23:59 is ours. Printing "11:59pm" would
    state a precision the school never gave us."""
    assert due_time(_at(23, 59), from_canvas=False) == ""
    assert due_time(_at(7, 20), from_canvas=False) == ""


def test_no_due_date_is_no_time():
    assert due_time(None, from_canvas=True) == ""
    assert due_time(None, from_canvas=False) == ""


# --- the hour, for a reader who does not yet read a clock quickly ----------------------

@pytest.mark.parametrize("h,expected", [
    (7, "morning"), (11, "morning"),
    (12, "afternoon"), (16, "afternoon"),
    (17, "evening"), (23, "evening"),
])
def test_a_canvas_hour_has_a_part_of_the_day(h, expected):
    from fridgesheet.dates import day_part
    assert day_part(_at(h, 20), from_canvas=True) == expected


def test_a_hac_only_item_has_no_part_of_the_day():
    """Same rule as the hour itself: HAC never gave one, so the app does not offer one."""
    from fridgesheet.dates import day_part
    assert day_part(_at(23, 59), from_canvas=False) == ""
    assert day_part(None, from_canvas=True) == ""


def test_the_part_of_day_is_the_hour_it_already_shows(tmp_path):
    """Not a new fact -- the same timestamp, said in a word."""
    from fridgesheet.dates import day_part, due_time
    d = _at(7, 20)
    assert due_time(d, from_canvas=True) == "7:20am" and day_part(d, from_canvas=True) == "morning"


# --- the web pages --------------------------------------------------------------------

def test_the_kid_table_shows_a_canvas_items_time(tmp_path):
    from tests.web_fixtures import app_for, seed
    conn = seed(tmp_path)
    iid = conn.execute("SELECT id FROM items WHERE name = 'Quiz 1'").fetchone()["id"]
    conn.close()
    body = app_for(tmp_path).get("/kids/Alex?show=all").text
    row = _row(body, iid)
    assert "11:59pm" in row, row


def test_the_kid_table_shows_no_time_for_a_hac_only_item(tmp_path):
    """"Participation" in the fixture is HAC-only: a date, no time, ever."""
    from tests.web_fixtures import app_for, seed
    conn = seed(tmp_path)
    iid = conn.execute("SELECT id FROM items WHERE name = 'Participation'").fetchone()["id"]
    conn.close()
    row = _row(app_for(tmp_path).get("/kids/Alex?show=all").text, iid)
    assert "pm" not in row.lower() and "am" not in row.lower(), row


def test_the_reconcile_card_shows_the_time_too(tmp_path):
    """The same fact, on the page where a parent decides what to do about it."""
    from tests.web_fixtures import app_for, seed
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/reconcile").text
    assert "due 9/12 11:59pm" in body


def _row(body: str, item_id: int) -> str:
    import re
    m = re.search(rf'id="row-{item_id}">(.*?)</tr>', body, re.S)
    assert m, f"no row for item {item_id}"
    return m.group(1)


# --- the printed sheet ----------------------------------------------------------------

def test_the_sheet_says_a_canvas_end_of_day_deadline_out_loud():
    """It used to suppress 23:59 entirely. Web and paper now agree, which is the point:
    the two disagreeing is what hid this from a parent in the first place."""
    from fridgesheet.sheet import fmt_due
    assert fmt_due(_at(23, 59), from_canvas=True) == "Sat 9/26 11:59pm"
    assert fmt_due(_at(7, 20), from_canvas=True) == "Sat 9/26 7:20am"


def test_the_sheet_shows_no_time_for_a_hac_only_row():
    from fridgesheet.sheet import fmt_due
    assert fmt_due(_at(23, 59), from_canvas=False) == "Sat 9/26"
