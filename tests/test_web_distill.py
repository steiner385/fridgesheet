"""Structure from the 2026-09-29 critique (.impeccable/critique/), the third polish pass: fewer
empty containers on a child's Plan, the work list as lines on a phone, a detail card whose More
offers only what the answers do not, the two rarely used filters behind a second fold, the
adult answers folded (identically at every tier: parity is rows and actions, and a fold is
neither hidden nor removed), and the Today card leading with tonight's number."""
from __future__ import annotations

import re
from pathlib import Path

from tests.web_fixtures import app_for, seed

WEB = Path(__file__).resolve().parents[1] / "fridgesheet" / "web"
CSS = (WEB / "static" / "app.css").read_text(encoding="utf-8")


def _strip() -> str:
    return re.search(r"@media \(max-width: 1023px\)\s*\{(.*?)\n\}", CSS, re.S).group(1)


def _id(tmp_path, name):
    conn = seed(tmp_path)
    try:
        return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]
    finally:
        conn.close()


# --- the Plan: a state group only when it has a step -----------------------------------------------

def test_an_empty_plan_is_one_line_not_three_empty_groups(tmp_path):
    seed(tmp_path).close()
    plan = app_for(tmp_path).get("/kids/Sam/plan").text
    panel = plan[plan.index('<section id="plan"'):plan.index("</section>", plan.index('<section id="plan"'))]
    assert "<h4>Work to do</h4>" not in panel and "<h4>Need help</h4>" not in panel
    assert panel.count("No steps here yet.") == 1 and "Pick one above" in panel


def test_a_state_group_renders_only_with_a_step_in_it(tmp_path):
    from uuid import uuid4
    from fridgesheet.web.stores import plans
    from tests.web_fixtures import NOW
    conn = seed(tmp_path)
    plans.save(conn, 1, dict(title="Bring PE uniform", family_account="", next_step="x", owner="Alex", planned_for="2026-09-15",
                             minutes=5, state="blocked", position=10, evidence="{}", recorded_by=""),
               now=NOW.isoformat(), request_key=str(uuid4()))
    conn.close()
    plan = app_for(tmp_path).get("/kids/Alex/plan").text
    panel = plan[plan.index('<section id="plan"'):plan.index("</section>", plan.index('<section id="plan"'))]
    assert "<h4>Need help</h4>" in panel
    for label in ("Work to do", "Check again later"):                       # only if a step is in that state
        if f"<h4>{label}</h4>" in panel:
            after = panel[panel.index(f"<h4>{label}</h4>"):]
            assert after.index('<div class="item step') < (after.index("<h4>", 5) if "<h4>" in after[5:] else len(after))


# --- the detail card: More offers only what the answers do not ---------------------------------------

def test_the_flag_menu_leaves_out_the_flags_already_offered_as_answers(tmp_path):
    pid = _id(tmp_path, "Participation")                                       # asks: Yes handed in / today / tomorrow / Ask the teacher
    detail = app_for(tmp_path).get(f"/items/{pid}").text
    menu = re.search(r'<form class="flagmenu".*?</form>', detail, re.S).group(0)
    assert 'value="ask_teacher"' not in menu and 'value="done"' not in menu   # both are answers on the card
    assert 'value="excused"' in menu and 'value="follow_up"' in menu          # still reachable behind More


# --- "Too late to submit" in the row; only "Let it go" folds, at every tier ---------------------------

ANSWERS_BLOCK = r'<div class="answers">.*?</div>\s*(?=<p class="ours"|<div class="inset"|<div class="item-foot")'
FOLD = r'<details class="more-answers"><summary>More answers</summary>(.*?)</details>'


def _zero_on_essay(home):
    """Alex's submitted Essay draft with a HAC zero: the card asks, "Ask the teacher" first and
    "The zero is right" (`ignore`) second -- the one answer that still folds."""
    from tests.web_fixtures import _h, snapshot
    snap = snapshot()
    snap["students"]["Alex"]["hac"]["classes"][0]["assignments"].append(_h("Essay draft", "09/14/2026", 0.0))
    conn = seed(home, snap)
    try:
        return conn.execute("SELECT id FROM items WHERE name = 'Essay draft'").fetchone()["id"]
    finally:
        conn.close()


def test_too_late_to_submit_is_one_tap_in_the_row_never_folded(tmp_path):
    """"Won't do / too late" is a single tap beside the other answers (2026-10-03): a not-done
    row's last button, never behind "More answers"."""
    hw = _id(tmp_path, "Homework 4")                                           # past the window: Let it go first, Too late last
    detail = app_for(tmp_path).get(f"/items/{hw}").text
    answers = re.search(ANSWERS_BLOCK, detail, re.S).group(0)
    assert re.search(r'value="ignore" class="default"', answers)             # the first answer keeps the default stroke
    assert 'value="too_late"' in answers and 'value="done"' in answers
    assert "<details" not in answers                                           # nothing left to fold: both dismissals are in the row
    assert answers.index('value="done"') < answers.index('value="too_late"')   # Too late closes the row, so it comes last


def test_let_it_go_still_folds_behind_more_answers_unless_first(tmp_path):
    eid = _zero_on_essay(tmp_path)
    detail = app_for(tmp_path).get(f"/items/{eid}").text
    answers = re.search(ANSWERS_BLOCK, detail, re.S).group(0)
    assert re.search(r'value="ask_teacher" class="default"', answers)
    fold = re.search(FOLD, answers, re.S)
    assert fold and 'value="ignore"' in fold.group(1)
    assert 'value="ignore"' not in answers.split("<details")[0]


def test_the_fold_is_the_same_at_every_tier(tmp_path):
    from tests.web_fixtures import client_with_grades
    homes = {}
    for tier, grade in (("early", 5), ("older", 11)):
        home = tmp_path / tier
        home.mkdir()
        eid = _zero_on_essay(home)
        homes[tier] = client_with_grades(home, Alex=grade).get(f"/items/{eid}").text
    early, older = homes["early"], homes["older"]
    for body in (early, older):
        assert body.count('<details class="more-answers">') == 1
    assert early.count("<button") == older.count("<button")


# --- the filters: two you use, the rest behind a second fold ------------------------------------------

def test_the_rarely_used_filters_are_gone_and_their_links_still_list(tmp_path):
    """Assignments as a to-do list (spec 2026-10-06): one Class picker on To do, Class and
    Outcome on Done; the gradebook, kind, answer and verdict filters left the page, and a link
    that carries one still opens Done with it in force, kept through a class change."""
    seed(tmp_path).close()
    c = app_for(tmp_path)
    head = c.get("/kids/Alex").text
    for name in ("source", "kind", "flagged", "verdict", "outcome", "show"):
        assert f'<select name="{name}"' not in head and f'name="{name}"' not in head, name
    done = c.get("/kids/Alex?source=hac").text
    assert 'id="done"' in done and '<input type="hidden" name="source" value="hac">' in done
    assert '<select name="outcome"' in done


# --- Today: the number first, the buttons after -------------------------------------------------------

def test_the_today_card_leads_with_the_tally_and_says_nothing_about_zero_news(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/").text
    start = body.index('<h3><a href="/kids/Alex/check-in">')
    card = body[start:body.index("</div><!-- /kid -->", start)]
    assert card.index('class="tally"') < card.index("Start check-in")
    assert "0 new since yesterday" not in body


# --- the stylesheet: lines on a phone, the strip's order, the measure, the folds' rhythm -----------

def test_the_work_list_stacks_into_lines_under_the_strip():
    strip = _strip()
    assert re.search(r"table\.items tbody tr\s*\{[^}]*display: flex[^}]*flex-direction: column", strip)
    assert re.search(r"table\.items td\.item\s*\{[^}]*order: 1", strip)
    assert re.search(r"table\.items thead tr\s*\{[^}]*display: flex", strip)      # the sort links stay


def test_the_strip_puts_a_sections_controls_after_its_lead():
    assert re.search(r"\.sec-head \.controls\s*\{[^}]*order: 9", _strip())
    assert re.search(r"\.page-head \.page-actions \.button-link\s*\{[^}]*border: 0", _strip())


def test_long_lines_are_bounded_to_the_measure():
    for sel in ("p.legend",):
        assert re.search(re.escape(sel) + r"\s*\{[^}]*max-width: var\(--measure\)", CSS), sel
    # The tab hint became the planner's ruled header line, spanning the spread (2026-09-29).
    assert re.search(r"\.tab-hint\s*\{[^}]*border-bottom: 1\.5px solid var\(--box\)", CSS)


def test_a_quiet_fold_has_more_space_above_than_below():
    assert re.search(r"\.sec\.quiet\s*\{[^}]*margin: var\(--s5\) 0 var\(--s3\)", CSS)


def test_a_hidden_detail_row_stays_hidden_when_the_list_is_lines():
    """Re-critique 2026-09-29: `display: flex` on a row outranked the browser's `[hidden]`, so
    every folded detail row drew as an empty box under its assignment on a phone."""
    strip = _strip()
    assert re.search(r"table\.items tbody tr\[hidden\]\s*\{[^}]*display: none", strip)


def test_the_open_everything_chips_follow_the_tier():
    assert "font-size: var(--type-small)" in re.search(r"(?m)^\.seg label\s*\{([^}]*)\}", CSS).group(1)
