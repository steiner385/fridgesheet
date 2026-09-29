"""Copy and vocabulary from the 2026-09-29 critique (.impeccable/critique/), the second polish
pass: one number from Today to Plan, a verb on every plan answer, one phrase per row on a
child's two pages, one word for a family step, and one meaning for "waiting"."""
from __future__ import annotations

import re

from fridgesheet.web import phrasing
from fridgesheet.web.stores import plans
from tests.web_fixtures import app_for, client_with_grades, seed


def _ids(tmp_path, *names):
    conn = seed(tmp_path)
    try:
        return [conn.execute("SELECT id FROM items WHERE name = ?", (n,)).fetchone()["id"] for n in names]
    finally:
        conn.close()


# --- the number a parent carries from Today to the Plan ------------------------------------------

def _tally_matches_plan(c, key):
    card = c.get("/").text
    start = card.index(f'<h3><a href="/kids/{key}/check-in">')
    card = card[start:card.index("</div>", start)]
    m = re.search(r'<span class="big">(\d+)</span> to finish by tomorrow(?:, (\d+) planned)?(?: · (\d+) more on the list)?', card)
    assert m, card
    red, planned, more = (int(g or 0) for g in m.groups())
    plan = c.get(f"/kids/{key}/plan").text
    head = int(re.search(r'<h3 id="mf-heading">Must finish</h3><span class="count">(\d+)</span>', plan).group(1))
    assert red - planned + more == head, (red, planned, more, head)
    return red, planned, more


def test_the_today_tally_is_the_plans_must_finish_count_in_parts(tmp_path):
    """"2 to finish by tomorrow · 3 more on the list" on Today; "Must finish 5" on the Plan.
    The old line said "2 not done, due by tomorrow" and the Plan said 5."""
    seed(tmp_path).close()
    red, planned, more = _tally_matches_plan(app_for(tmp_path), "Alex")
    assert (red, planned, more) == (2, 0, 3)


def test_a_red_row_a_step_covers_is_still_counted_and_named_as_planned(tmp_path):
    """Review finding 1 keeps the red count honest; the Plan lists that row under Our next
    steps instead, so the card says so and the arithmetic still lands on the Plan's count."""
    from uuid import uuid4
    from fridgesheet.web.stores import plans as plan_store
    from tests.web_fixtures import NOW
    conn = seed(tmp_path)
    vocab = conn.execute("SELECT id FROM items WHERE name = 'Vocabulary'").fetchone()["id"]
    plan_store.save(conn, 1, dict(title="Vocabulary", family_account="", next_step="x", owner="Alex", planned_for="2026-09-15",
                                  minutes=20, state="planned", position=10, evidence="{}", recorded_by=""),
                    now=NOW.isoformat(), request_key=str(uuid4()), item_id=vocab)
    conn.close()
    red, planned, more = _tally_matches_plan(app_for(tmp_path), "Alex")
    assert (red, planned) == (2, 1)


# --- a verb on every plan answer ------------------------------------------------------------------

def test_a_plan_row_asks_before_it_offers_and_the_answers_carry_their_verb(tmp_path):
    vid, = _ids(tmp_path, "Vocabulary")
    body = app_for(tmp_path).get("/kids/Alex/plan").text
    row = re.search(r'<div class="item due" id="mf-%d".*?(?=<div class="item[ "]|</div><!-- /\w+ -->)' % vid, body, re.S).group(0)
    assert '<p class="ask-line plan">When will you work on it?</p>' in row
    assert re.search(r'value="plan:today" class="default">Do it today</button>', row)
    assert re.search(r'value="plan:tomorrow" class="">Do it tomorrow</button>', row)
    assert ">Today</button>" not in row and ">Tomorrow</button>" not in row


def test_the_early_tier_says_the_same_thing_in_its_own_words():
    assert phrasing.phrase("a.today", "early") == "I'll do it today"
    assert phrasing.phrase("ask.plan", "early") == "When will you do it?"
    for key in ("a.today", "a.tomorrow", "ask.plan"):
        for tier in ("early", "middle", "older"):
            assert not re.search(r"\d", phrasing.phrase(key, tier)), (key, tier)   # no number a tier adds


def test_a_waiting_row_gets_no_plan_prompt(tmp_path):
    """Lab notebook is handed in and waiting for a grade: its sentence says time will settle
    it, and it offers no plan answers, so there is nothing to ask."""
    lab, = _ids(tmp_path, "Lab notebook")
    body = app_for(tmp_path).get("/kids/Alex/plan").text
    row = re.search(r'<div class="item grey" id="mf-%d".*?(?=<div class="item[ "]|</div><!-- /\w+ -->)' % lab, body, re.S)
    if row:                                                    # only when the row is in Must finish
        assert 'class="ask-line plan"' not in row.group(0)


# --- one phrase per row on a child's two pages ---------------------------------------------------

def test_a_young_readers_table_row_says_what_their_plan_says(tmp_path):
    """Sam (early) read "Marked zero - ask about it" on the Plan and "0/10 · Canvas" in the
    Assignments table for the same row. Now the row says the Plan's word; provenance stays
    in the Record. Alex (older) keeps the grade and its source."""
    seed(tmp_path).close()
    c = client_with_grades(tmp_path, Sam=5, Alex=9)                 # early and older tiers
    sam = c.get("/kids/Sam?show=all").text
    quiz = sam[sam.index("Safety quiz"):]
    where = re.search(r'<td class="where[^"]*">([^<]+)', quiz).group(1).strip()
    assert where == "Marked zero - ask about it", where
    assert "· Canvas" not in where
    # A parent's column keeps the grade and its source; the verdict's own phrase still wins.
    from types import SimpleNamespace
    from fridgesheet.web import verdicts
    zero = SimpleNamespace(verdict=SimpleNamespace(kind="not_done", facts={}), grade="0/10", grade_source="canvas", status="Zero", flag=None)
    assert verdicts.standing(zero, "") == "0/10 · Canvas"
    assert verdicts.standing(zero, "older") == "0/10 · Canvas"
    assert verdicts.standing(zero, "middle") == "Scored zero"


# --- one word for a family step, one meaning for waiting -----------------------------------------

def test_a_family_step_is_a_step_everywhere(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    assert "Add a step" in c.get("/kids/Alex/plan").text
    form = c.get("/kids/Alex/check-in/step").text
    assert "<h2>Add a step</h2>" in form and "Add a task" not in form
    for name in ("_plan_panel.html", "plan_step.html", "checkin.html"):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] / "fridgesheet" / "web" / "templates" / name).read_text(encoding="utf-8")
        assert "task" not in text.lower().replace("multitask", ""), name


def test_a_waiting_step_is_named_for_what_to_do_with_it():
    assert plans.STATES["waiting"] == "Check again later"
    assert list(plans.STATES.values()).count("Waiting") == 0
