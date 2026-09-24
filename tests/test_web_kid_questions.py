"""The kid page's three sections above the work list (spec 6.1)."""
from __future__ import annotations

import re

from tests.web_fixtures import app_for, seed


def _page(tmp_path, q=""):
    seed(tmp_path).close()
    return app_for(tmp_path).get(f"/kids/Alex{q}").text


def test_alex_has_one_question_one_decided_and_two_waiting(tmp_path):
    body = _page(tmp_path)
    assert "1 question about" in body
    assert re.search(r'id="q-\d+"[^>]*>.*?Participation', body, re.S)
    decided = body[body.index("Settled by the records"):body.index("Waiting")]
    assert "Quiz 1" in decided and "Not right?" in decided
    waiting = body[body.index("Waiting"):body.index('id="items"')]
    assert "Essay draft" in waiting and "Lab notebook" in waiting and "Ask now" in waiting


def test_sections_ignore_the_table_filter(tmp_path):
    assert "1 question about" in _page(tmp_path, "?course=999")


def test_the_work_list_has_three_columns_and_no_sources_or_actionable(tmp_path):
    body = _page(tmp_path, "?show=all")
    table = body[body.index('id="items"'):]
    assert "Where it stands" in table and "Sources" not in table and "actionable" not in table


def test_red_marks_only_school_recorded_not_done(tmp_path):
    table = _page(tmp_path, "?show=all")
    rows = dict(re.findall(r'<tr[^>]*id="row-\d+"[^>]*>.*?<a[^>]*>([^<]+)</a>.*?<td class="where([^"]*)"', table, re.S))
    assert "red" in rows["Homework 4"]            # Canvas marked it missing
    assert "red" not in rows["Lab notebook"]      # the app is waiting, not the school saying no
    assert "red" not in rows["Quiz 1"]            # decided done


def test_more_filters_keeps_the_old_selects_behind_a_disclosure(tmp_path):
    body = _page(tmp_path)
    more = body[body.index("<details class=\"more-filters\""):]
    for name in ("source", "kind", "flagged", "outcome"):
        assert f'name="{name}"' in more


def test_the_course_pages_question_tag_links_to_the_kid_pages_card(tmp_path):
    """Finding 10: the course page has no question cards, so its tag must point at the kid page."""
    conn = seed(tmp_path)
    cid = conn.execute("SELECT id FROM courses WHERE source = 'canvas' AND short_name = 'Honors English 9'").fetchone()["id"]
    pid = conn.execute("SELECT id FROM items WHERE name = 'Participation'").fetchone()["id"]
    conn.close()
    body = app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text
    assert f'href="/kids/Alex#q-{pid}"' in body
    assert f'href="#q-{pid}"' not in body



# --- kids' UX audit F8: one true sentence about what has been done ---------------------------------

def test_the_page_says_what_has_been_done_so_far(tmp_path):
    """Every child surface listed only what was wrong; the on-time counts lived inside a collapsed
    details on the parent's Today page. Alex's settled work at the fixture's now: Quiz 1 done on
    paper, Essay draft on time, Lab notebook and Participation unknown, Homework 4 not done."""
    body = _page(tmp_path)
    assert "Done so far: 2 of 5 due · 1 on time." in body
    assert body.index("Done so far") < body.index("1 question about")     # above the questions


def test_nothing_done_yet_says_nothing(tmp_path):
    """A line that exists to state what went right does not appear to state that nothing has,
    which the dashboard's record already does in numbers."""
    seed(tmp_path).close()
    assert "Done so far" not in app_for(tmp_path).get("/kids/Sam").text     # two not-done rows, nothing done
