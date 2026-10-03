"""The check-in agrees with Assignments (#68), speaks the same words and can answer (#69), and
says what Canvas and HAC are (#70)."""
from __future__ import annotations

import re

from tests.web_fixtures import _h, app_for, seed, snapshot


def _groups(body):
    out = {}
    for g in re.split(r'<details class="sec queue-group', body)[1:]:
        label = re.search(r"<summary><h3>(.*?)</h3>", g)
        if label:
            out[label.group(1)] = g
    return out


def _id(tmp_path, name):
    conn = seed(tmp_path)
    try:
        return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]
    finally:
        conn.close()


# --- #68: one verdict, both pages --------------------------------------------------------------

def test_check_in_groups_follow_the_verdicts(tmp_path):
    seed(tmp_path).close()
    g = _groups(app_for(tmp_path).get("/kids/Alex/check-in").text)
    # "Completed steps" (the plan panel's own fold) now sits ahead of the review groups in the
    # document (Must finish, then the plan, then the queue -- spec 2026-09-27 §4-§7).
    assert list(g)[1:4] == ["Worth checking", "Waiting on the school", "Other open work"]
    assert "Lab notebook" not in g["Waiting on the school"]           # paper, no grade: Must finish's now
    assert "Participation" not in "".join(g.values())                 # HAC-only, a week with no grade: same
    assert "Essay draft" in g["Waiting on the school"]
    assert "Homework 4" in g["Other open work"]
    for name in ("Vocabulary", "Worksheet 3", "Reading log"):         # upcoming: Must finish's now
        assert name not in g["Other open work"], name
    assert "Quiz 1" not in "".join(g.values())                     # decided: nothing to talk about


def test_the_evidence_never_asks_what_the_verdict_has_not(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex/check-in").text
    assert "To clarify" not in body and "Was it collected?" not in body


def test_the_rail_count_is_the_check_ins_questions(tmp_path):
    """The rail count is every "asks" verdict for the kid, wherever it now renders: a review
    card in "Worth checking", or a Must-finish row (spec 2026-09-27 §4) -- Participation,
    HAC-only with no grade, still asks from its own row there ("Was it handed in?")."""
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex/check-in").text
    rail = re.search(r'href="/kids/Alex/check-in"[^>]*>Alex <span id="qcount-Alex" class="count">(\d+)</span>', body)
    worth_asks = len(re.findall(r'<div class="item ask" id="qc-', _groups(body)["Worth checking"]))
    must_finish = re.search(r'<section id="must-finish".*?</section>', body, re.S).group(0)
    mf_rows = re.split(r'id="mf-\d+"', must_finish)[1:]           # one split per row's own id
    mf_asks = sum(1 for row in mf_rows if '<p class="ask-line">' in row)
    assert rail and int(rail.group(1)) == worth_asks + mf_asks


# --- #69: same words, answers on the card, a link to the item ---------------------------------

def test_a_check_in_question_card_can_be_answered_and_opens_the_item(tmp_path):
    """Participation (HAC-only, a week with no grade) asks, and it is a Must-finish row now
    (paper, no grade) -- not a review card, but the same one-tap answer pattern (spec
    2026-09-27 §4: Must-finish rows use `qc-<id>` too, so the answer route swaps either)."""
    pid = _id(tmp_path, "Participation")
    body = app_for(tmp_path).get("/kids/Alex/check-in").text
    card = re.search(r'<div class="item[^"]*" id="mf-%d".*?</div><!-- /paper -->' % pid, body, re.S).group(0)
    assert "Was it handed in?" in card
    assert f'hx-post="/items/{pid}/answer"' in card and 'name="slot" value="qc-%d"' % pid in card
    assert f'href="/kids/Alex?show=all#row-{pid}"' in card


def test_one_name_for_planning_a_step(tmp_path):
    pid = _id(tmp_path, "Participation")
    c = app_for(tmp_path)
    for body in (c.get("/kids/Alex/check-in").text, c.get(f"/items/{pid}").text,
                 c.get(f"/kids/Alex/check-in/step?item_id={pid}").text):
        assert "Choose a next step" not in body
    assert ">Plan a step<" in c.get("/kids/Alex/check-in").text


def test_the_answer_route_accepts_the_check_in_slot(tmp_path):
    pid = _id(tmp_path, "Participation")
    r = app_for(tmp_path).post(f"/items/{pid}/answer", data={"answer": "done", "prev": "", "slot": f"qc-{pid}"})
    assert f'id="qc-{pid}"' in r.text


# --- #70: Canvas and HAC, explained where they are used ----------------------------------------

def test_canvas_and_hac_are_explained_once_per_page_and_not_in_the_record(tmp_path):
    qid = _id(tmp_path, "Quiz 1")
    c = app_for(tmp_path)
    line = "HAC (Home Access Center) is the official gradebook"
    assert c.get("/kids/Alex").text.count(line) == 1 and c.get("/kids/Alex/check-in").text.count(line) == 1
    record = c.get(f"/items/{qid}").text
    assert line not in record and "Open in Canvas (opens a new tab)" in record


# --- the pace sentence (spec 4.6) --------------------------------------------------------------

def test_a_waiting_card_says_what_fridge_sheet_expects_and_why(tmp_path):
    """Essay draft: submitted, ungraded, no history -> the default sentence. (Lab notebook
    carries the same pace facts, but it is Must finish's now -- paper, no grade -- and no
    longer a review card; Essay draft is still one, and still shows it.)"""
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex/check-in").text
    card = _groups(body)["Waiting on the school"]
    assert "Fridge Sheet has no earlier grades from this class to go on" in card
    assert "allows 7 days" in card


def test_the_pace_sentence_shows_on_the_question_card_too(tmp_path):
    """Participation: HAC-only, due 9/8, a week on -> still_ungraded, the default sentence."""
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex").text
    assert "Fridge Sheet has no earlier grades from this class to go on" in body


# --- one tap on every card (spec 6.2, 6.5) --------------------------------------------------------

def _card(body, pid):
    """One item's card, wherever it lives now: a review-card in a queue, or a Must-finish row
    (spec 2026-09-27 §4 moved the upcoming/fixable rows there, out of the review groups)."""
    m = re.search(r'<div class="item[^"]*" id="qc-%d".*?(?=<div class="item[ "]|</details>)' % pid, body, re.S)
    if m:
        return m.group(0)
    return re.search(r'<div class="item[^"]*" id="mf-%d".*?(?=<div class="item[ "]|</div><!-- /\w+ -->)' % pid,
                     body, re.S).group(0)


def test_an_upcoming_card_offers_today_tomorrow_and_handed_in(tmp_path):
    vid = _id(tmp_path, "Vocabulary")                      # due today, nothing handed in
    card = _card(app_for(tmp_path).get("/kids/Alex/check-in").text, vid)
    assert 'value="plan:today"' in card and 'value="plan:tomorrow"' in card and 'value="done"' in card
    assert 'class="ask-line"' not in card                        # a status, not a question


def test_an_upcoming_card_also_offers_too_late_to_submit(tmp_path):
    """The manual override sits beside done/plan:today/plan:tomorrow on any not-yet-done card,
    one tap, never folded (2026-10-03): Homework 4, past its window and a review card ("Other
    open work"), and Vocabulary, due today and a Must-finish row."""
    ids = [_id(tmp_path, name) for name in ("Homework 4", "Vocabulary")]
    body = app_for(tmp_path).get("/kids/Alex/check-in").text
    for pid in ids:
        card = _card(body, pid)
        assert 'value="too_late"' in card and "Too late to submit" in card
        assert "more-answers" not in card


def test_a_waiting_card_offers_ask_the_teacher(tmp_path):
    eid = _id(tmp_path, "Essay draft")                      # submitted, ungraded
    card = _card(app_for(tmp_path).get("/kids/Alex/check-in").text, eid)
    assert 'value="ask_teacher"' in card


def test_a_waiting_card_has_no_default_button(tmp_path):
    """Waiting means time will settle it: the card says so, so "Ask the teacher" must not be the
    filled default beside it (kids' UX audit F9). A question card keeps its filled first answer."""
    eid, pid = _id(tmp_path, "Essay draft"), _id(tmp_path, "Participation")
    body = app_for(tmp_path).get("/kids/Alex/check-in").text
    assert 'class="default"' not in _card(body, eid)
    assert 'class="default"' in _card(body, pid)


def test_the_plan_panel_is_one_partial_with_its_id(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex/check-in").text
    sections = re.findall(r'<section id="plan"[^>]*>', body)          # `id="plan-heading"` is a different id
    assert len(sections) == 1 and "hx-swap-oob" not in sections[0]
