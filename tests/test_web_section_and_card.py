"""One section, one card (docs/superpowers/specs/2026-09-28-section-and-card-standard-design.md).

Holds the standard the way test_web_page_layout.py holds the page layout: the tokens, the
section head, the item's five slots at three densities, and, once every page is converted,
the absence of the classes it retired. CSS is not executed here.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.web_fixtures import app_for, client_with_grades, seed

WEB = Path(__file__).resolve().parents[1] / "fridgesheet" / "web"
CSS = (WEB / "static" / "app.css").read_text(encoding="utf-8")
TEMPLATES = WEB / "templates"


def _root() -> str:
    return re.search(r":root\s*\{([^}]*)\}", CSS).group(1)


def _rule(selector: str) -> str:
    # Anchored to a line start: `td.item { order: 1 }` on the phone must not stand in for `.item`.
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"no {selector} rule"
    return m.group(1)


# --- §6: tokens ---------------------------------------------------------------------------------

def test_the_root_defines_the_radius_and_the_gap_scale():
    root = _root()
    assert re.search(r"--radius:\s*8px", root)
    for tok, px in (("--s1", 4), ("--s2", 8), ("--s3", 12), ("--s4", 16), ("--s5", 24), ("--s6", 32)):
        assert re.search(rf"{tok}:\s*{px}px", root), f"{tok} is not {px}px"


# --- §3: the section ----------------------------------------------------------------------------

def test_a_section_head_is_one_wrapping_row_and_a_folded_section_draws_the_same_head():
    assert re.search(r"\.sec\s*\{[^}]*margin: 0 0 var\(--s6\)", CSS)
    head = _rule(".sec-head, details.sec > summary")
    assert "display: flex" in head and "flex-wrap: wrap" in head
    # 18px at the root, and a tier's own step above its body (critique 2026-09-29: the fixed
    # 18px head was the smallest text above the fold on the early tier's 20px page).
    assert re.search(r"\.sec-head h3, details\.sec > summary h3\s*\{[^}]*font-size: calc\(var\(--type-root\) \* 1\.125\)", CSS)
    assert re.search(r"\.sec\.quiet h3\s*\{[^}]*color: var\(--muted\)", CSS)
    assert re.search(r"\.sec-head \.lead\s*\{[^}]*flex-basis: 100%", CSS)
    assert re.search(r"\.sec-head \.controls\s*\{[^}]*margin-left: auto", CSS)
    # A folded section keeps a disclosure marker: `summary { display: flex }` drops the
    # native `::marker` in Chromium and Firefox, so the mark is drawn with `::before` instead,
    # the same pattern the item-foot's own folds already use (final review finding 3).
    assert re.search(r'details\.sec > summary::before\s*\{[^}]*content: "▸ "', CSS)
    assert re.search(r'details\.sec\[open\] > summary::before\s*\{[^}]*content: "▾ "', CSS)


# --- §4: the item surface -----------------------------------------------------------------------

def test_the_item_is_one_planner_line_with_a_checkbox_that_names_its_tone():
    """The Student Planner (2026-09-29): a line under a hairline, a square checkbox at its head,
    the tone on the checkbox's rule. The day box around the lines is the only box."""
    item = _rule(".item")
    assert "border-bottom: 1px solid var(--rule)" in item and "border-radius" not in item and "background: none" in item
    assert "overflow-wrap: anywhere" in item                                   # a long name wraps
    box = _rule("div.item::before")
    assert "width: 18px" in box and "border: 2px solid var(--box)" in box
    for tone, colour in (("ask", "--accent"), ("red", "--warn")):
        assert re.search(rf"\.item\.{tone}::before[^{{]*\{{[^}}]*border-color: var\({colour}\)", CSS), tone
    assert re.search(r"\.item\.ok::before[^{]*\{[^}]*background: var\(--ok\)", CSS)
    assert re.search(r"\.item\.grey\s*\{[^}]*color: var\(--muted\)", CSS)
    assert re.search(r"\.item-head \.when\s*\{[^}]*margin-left: auto", CSS)
    # The sheet's word wears the sheet's colour, and only a school-recorded not-in is red
    # (critique 2026-09-29: DUE TODAY and HAC — NO GRADE were red because every word was).
    assert re.search(r"\.item-head \.when\.word\s*\{[^}]*color: var\(--ink\)", CSS)
    for tone, colour, fill in (("red", "--warn", "--hl-red"), ("late", "--late", "--hl-late"), ("check", "--check", "--hl-check"), ("due", "--accent", "--hl-due")):
        word = re.search(rf"\.item-head \.when\.word\.{tone}\s*\{{([^}}]*)\}}", CSS).group(1)
        assert f"color: var({colour})" in word and f"background: var({fill})" in word, tone   # a highlighter stroke
        assert re.search(rf"\.item\.{tone}::before[^{{]*\{{[^}}]*border-color: var\({colour}\)", CSS), tone
    assert re.search(r"\.item-foot\s*\{[^}]*font-size: var\(--type-small\)", CSS)
    assert re.search(r"\.item-foot \.stamp\s*\{[^}]*font-size: var\(--type-tiny\)", CSS)
    assert re.search(r"\.ours\s*\{[^}]*color: var\(--muted\)", CSS)                   # the family writes in pencil; only links are blue


def test_the_inset_the_record_and_the_lines_share_the_radius():
    for sel in (".inset", ".lines"):
        assert "border-radius: var(--radius)" in _rule(sel), sel
    assert re.search(r"\.sources\s*\{[^}]*grid-template-columns: max-content 1fr", CSS)
    assert re.search(r"\.sources \.stamp\s*\{[^}]*grid-column: 2", CSS)
    assert re.search(r"\.done-line\s*\{[^}]*border-bottom: 1px solid var\(--rule\)", CSS)   # a checked-off line
    assert re.search(r"\.item \.done-line\s*\{[^}]*border: 0", CSS)


def test_a_badge_is_one_neutral_style():
    badge = _rule(".badge, .badge.flag, .badge.plan")
    assert "background: var(--wash)" in badge and "color: var(--ink)" in badge


def test_the_new_targets_are_44px_under_a_finger():
    coarse = "\n".join(re.findall(r"@media \(pointer: coarse\)\s*\{(.*?)\n\}", CSS, re.S))
    for sel in (".item-foot summary", ".item-foot a", "details.sec > summary", ".lines .line > a", ".item-head .name a"):
        assert re.search(re.escape(sel) + r"[^{]*\{[^}]*min-height: 44px", coarse), sel


# --- §4.1 the Record ----------------------------------------------------------------------------

def _id(tmp_path, name):
    conn = seed(tmp_path)
    try:
        return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]
    finally:
        conn.close()


def _element(body: str, start_tag: str) -> str:
    """The HTML of one <div>, from `start_tag` to its matching close, by counting div tags."""
    i = body.index(start_tag)
    depth = 0
    for m in re.finditer(r"<div\b|</div>", body[i:]):
        depth += 1 if m.group(0).startswith("<div") else -1
        if depth == 0:
            return body[i:i + m.end()]
    raise AssertionError(f"unbalanced div after {start_tag!r}")


def test_the_record_puts_each_sources_stamp_under_its_facts_and_carries_no_glossary(tmp_path):
    qid = _id(tmp_path, "Quiz 1")
    body = app_for(tmp_path).get(f"/items/{qid}").text
    inset = _element(body, '<div class="inset">')
    assert re.search(r'<span class="src">Canvas</span><span>[^<]+</span><span class="stamp">checked [^<]+</span>', inset)
    assert re.search(r'<span class="src">HAC</span><span>[^<]+</span><span class="stamp">checked [^<]+</span>', inset)
    assert "Home Access Center" not in inset
    assert "Open in Canvas (opens a new tab)" in inset


# --- §4 the five slots, at card and detail density ------------------------------------------------

def test_a_question_card_has_head_says_ask_answers_and_foot_in_that_order(tmp_path):
    """The question is asked in Needs you now at the top of Assignments (2026-10-04), and its
    line on the weekly pages keeps the rest (2026-09-30): the same five slots, the sheet's word
    at the head's right, the day in the row above."""
    from tests.web_fixtures import needs_row, week_line
    pid = _id(tmp_path, "Participation")
    body = app_for(tmp_path).get("/kids/Alex").text
    asked = needs_row(body, pid)
    order = [asked.index(s) for s in ('class="item-head"', 'class="facts"', 'class="ask-line"', 'class="answers"', 'class="item-foot"')]
    assert order == sorted(order)
    card = week_line(body, pid)
    assert card.startswith('<div class="item check" id="row-%d"' % pid)
    assert card.index('class="facts"') < card.index('class="item-foot"') and 'class="answers"' not in card
    assert 'class="ours"' not in card                                          # no step, no note, no answer yet
    head = _element(card, '<div class="item-head">')
    assert re.search(r'<span class="name"><a href="#row-%d"[^>]*data-focus-target>Participation</a></span>' % pid, head)
    assert re.search(r'<span class="meta"><a href="/kids/Alex/courses/\d+">Honors English 9</a>', head)
    assert '<span class="when word check">HAC — NO GRADE</span>' in head        # the sheet's word, in the sheet's colour
    facts = re.search(r'<p class="facts">(.*?)</p>', card).group(1)
    assert "due" not in facts and "9/8" not in facts                              # said once, in the day row above
    assert '<h5 class="day">Tue 9/8</h5>' in body[:body.index('id="row-%d"' % pid)]
    foot = _element(card, '<div class="item-foot">')
    assert foot.index("<summary>Record</summary>") < foot.index("Plan a step")
    assert "Notes (" not in foot and "<summary>More</summary>" not in foot        # the record the name opens holds those


def test_the_detail_is_the_same_card_with_close_and_the_record_open_and_nothing_twice(tmp_path):
    pid = _id(tmp_path, "Participation")
    body = app_for(tmp_path).get(f"/items/{pid}").text
    assert body.count("Participation</b>") == 1 and body.count("<h2") == 0
    head = _element(body, '<div class="item-head">')
    assert head.index("data-focus-target") < head.index("data-close-detail")
    assert body.index('class="answers"') < body.index('<div class="inset">') < body.index('class="item-foot"')
    assert body.count("<summary>Record</summary>") == 0                          # open in place, not folded
    foot = _element(body, '<div class="item-foot">')
    assert foot.index("Notes (0)") < foot.index("Plan a step") < foot.index("<summary>More</summary>")
    assert 'id="qd-%d"' % pid in body                                            # the detail's answers keep their own slot


def test_undo_inside_a_detail_puts_back_the_wrapper_not_a_second_card(tmp_path):
    """Answering from the detail's own slot (qd-<id>) and undoing it must restore just the
    `qid` wrapper -- the ask line and the answers -- not a whole second `.item` card nested
    inside the detail (final review finding 1)."""
    pid = _id(tmp_path, "Participation")
    c = app_for(tmp_path)
    detail = c.get(f"/items/{pid}").text
    assert f'id="qd-{pid}"' in detail
    answered = c.post(f"/items/{pid}/answer", data={"answer": "done", "prev": "", "slot": f"qd-{pid}"})
    assert f'<div class="line ok done-line" id="qd-{pid}"' in answered.text
    undone = c.post(f"/items/{pid}/undo", data={"prev": "", "slot": f"qd-{pid}"}).text
    assert undone.lstrip().startswith(f'<div id="qd-{pid}"')
    assert "Was it handed in?" in undone
    assert undone.count('class="answers"') == 1
    assert "item-head" not in undone and "data-focus-target" not in undone and "Notes (" not in undone


def test_a_note_and_a_step_show_in_the_family_slot_and_count_in_the_foot(tmp_path):
    from uuid import uuid4
    from fridgesheet.web import db
    from fridgesheet.web.stores import notes
    pid = _id(tmp_path, "Participation")
    conn = db.open_db(tmp_path)
    notes.add(conn, "item", pid, "Doug says he played it Friday", now="2026-09-14T19:00:00-04:00")
    conn.close()
    c = app_for(tmp_path)
    r = c.post(f"/items/{pid}/answer", data={"answer": "plan:today", "prev": "", "slot": f"q-{pid}", "request_key": str(uuid4())})
    assert r.status_code == 200
    body = c.get("/questions").text                       # the item is planned, so it left the question list;
    detail = c.get(f"/items/{pid}").text                  # the detail shows the family's layer
    ours = re.findall(r'<p class="ours">(.*?)</p>', detail)
    assert any(o.startswith("Our step: Work on it · Alex") for o in ours)
    assert any(o.startswith("Note, ") and "played it Friday" in o for o in ours)
    assert "Notes (1)" in detail and "Plan another step" in detail
    assert "played it Friday" not in body or 'class="ours"' in body


# --- §3 the Assignments tab as sections -------------------------------------------------------------

def test_the_assignments_tab_is_four_sections_with_the_filters_in_the_tables_head(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex").text
    content = body.split('class="child-nav"', 1)[1]
    heads = re.findall(r'<(?:section|details) class="sec[^"]*"[^>]*>\s*(?:<div class="sec-head">|<summary>)<h3[^>]*>([^<]*)</h3>', content)
    # The weekly pages (2026-09-30): the list first, the app's verdicts under it; a question is a
    # line on its week's page, and the count is a lead line in the list's head.
    assert heads == ["All assignments", "Settled by the records", "Waiting, nothing to do yet"]
    assert re.search(r'<p id="q-lead" class="lead">1 question about your work</p>', content)
    assert re.search(r'<details class="sec quiet">\s*<summary><h3>Waiting, nothing to do yet</h3> <span class="count">2</span></summary>', content)
    table_head = re.search(r'<h3 id="all-head">All assignments</h3>(.*?)<div id="items">', content, re.S).group(1)
    assert 'class="filters controls"' in table_head and 'name="course"' in table_head and "More filters" in table_head
    assert re.search(r'<div class="lines">\s*<div class="line ok" id="q-\d+"><span class="glyph"', content)   # Settled, line density


def test_a_filter_change_carries_the_tables_count_out_of_band(tmp_path):
    """The count sits in the section head, outside the #items swap; the partial refreshes it."""
    seed(tmp_path).close()
    c = app_for(tmp_path)
    full = c.get("/kids/Alex").text
    assert re.search(r'<span id="all-count" class="count">\d+ open</span>', full)
    assert full.count('id="all-count"') == 2                        # the head, and the inert template copy
    partial = c.get("/kids/Alex?course=999", headers={"HX-Request": "true", "HX-Current-URL": "http://127.0.0.1/kids/Alex"}).text
    assert '<span id="all-count" class="count" hx-swap-oob="true">0 open</span>' in partial
    assert 'class="sec-head"' not in partial


def test_kid_mode_draws_the_state_line_without_the_tabs(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    c.cookies.set("fridgesheet_who", "Alex")
    body = c.get("/kids/Alex").text
    assert 'class="child-nav"' not in body
    assert re.search(r'<p class="tab-hint">Done so far', body)


def test_the_questions_page_is_one_section_per_kid_with_lines_for_the_waiting(tmp_path):
    from fridgesheet.web import db
    from fridgesheet.web.stores import flags
    lab = _id(tmp_path, "Lab notebook")
    conn = db.open_db(tmp_path)
    flags.set_flag(conn, lab, "ask_teacher", now="2026-09-15T08:00:00-04:00")
    conn.close()
    body = app_for(tmp_path).get("/questions").text
    # One list for the house (the parent's answering page, 2026-09-30): "To answer" with the
    # count, the kid named in each line's meta; the waiting lines fold per kid beneath.
    assert re.search(r'<section class="sec household-questions"[^>]*>\s*<div class="sec-head"><h3 id="to-answer">To answer</h3><span id="qcount-page" class="count">1</span>', body)
    assert re.search(r'<span class="meta"><span class="kid">Alex</span> · Honors English 9', body)
    assert re.search(r'<details class="sec quiet waiting-fold"><summary><h3>Waiting on the teacher · Alex</h3><span class="count">1</span></summary>\s*<div class="waiting">\s*<div class="line grey" id="q-%d">' % lab, body)
    assert body.count("<h2") == 1
    line = _element(body, '<div class="line grey" id="q-%d">' % lab)
    assert line.count("mailto:") == 1                                  # the partial's Email link, once


def test_a_waiting_line_still_says_its_kind_and_due_date(tmp_path):
    """The line density draws no head, so `facts.*` no longer saying "{kind} work, due {due}"
    (spec §8, said once in the card's head) must not lose those facts on a line: they move
    into a meta span of their own (final review finding 2), on every tier."""
    lid = _id(tmp_path, "Lab notebook")
    body = app_for(tmp_path).get("/kids/Alex").text
    fold = body[body.index("Waiting, nothing to do yet"):]
    line = _element(fold, '<div class="line grey" id="q-%d">' % lid)
    assert 'class="meta"' in line and "paper" in line and "due " in line

    for i, grade in enumerate((None, 5, 7, 10)):
        home = tmp_path / f"tier-{i}"
        home.mkdir()
        lid = _id(home, "Lab notebook")
        c = client_with_grades(home, **({"Alex": grade} if grade is not None else {}))
        body = c.get("/kids/Alex").text
        fold = body[body.index("Waiting, nothing to do yet"):]
        line = _element(fold, '<div class="line grey" id="q-%d">' % lid)
        assert "paper" in line and "due Thu 9/10" in line, (grade, line)


def test_a_kid_with_no_questions_is_one_pencil_line_under_the_title(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/questions").text
    assert '<p class="quiet-kid muted">Nothing to ask about Sam\'s work.</p>' in body
    assert body.index("quiet-kid") < body.index('class="sec household-questions"')
    assert "Nothing to ask about Alex" not in body


def test_an_answer_collapses_a_card_to_the_line_density(tmp_path):
    pid = _id(tmp_path, "Participation")
    r = app_for(tmp_path).post(f"/items/{pid}/answer", data={"answer": "done", "prev": "", "slot": f"q-{pid}"})
    # On Questions the whole line is the slot, so the answer keeps the line and strikes it (2026-09-30).
    assert re.match(rf'\s*<div class="item ok" id="q-{pid}" data-focus', r.text) and 'class="line ok done-line"' in r.text
    assert "Undo" in r.text


# --- §4.3 Check-in and Plan ---------------------------------------------------------------------------

def test_a_must_finish_row_is_the_item_with_the_sheets_word_at_the_right_and_no_ask(tmp_path):
    vid = _id(tmp_path, "Vocabulary")                                          # due today, nothing handed in
    body = app_for(tmp_path).get("/kids/Alex/plan").text
    # A due-today row is due, not not-in: its rule and its word are the sheet's blue, never red.
    row = re.search(r'<div class="item due" id="mf-%d".*?(?=<div class="item[ "]|</div><!-- /\w+ -->)' % vid, body, re.S).group(0)
    head = re.search(r'<div class="item-head">(.*?)</div>', row, re.S).group(1)
    assert re.search(r'<span class="name"><a href="/kids/Alex\?show=all#row-%d" data-focus-target>Vocabulary</a></span>' % vid, head)
    assert re.search(r'<span class="when word due">DUE TODAY</span>', head)      # sheet_word's own word for a due-today row
    # Not a question, so no `ask-line` of the verdict's; the plan prompt above the answers is its
    # own line, so the rail's question count (which counts ask-lines) is untouched.
    assert 'class="ask-line"' not in row and 'class="ask-line plan"' in row and 'id="qc-%d"' % vid in row
    foot = _element(row, '<div class="item-foot">')                              # the Record fold nests a </div> of its own
    assert "<summary>Record</summary>" in foot and "Plan a step" in foot and "Add details" not in foot and "Notes (" not in foot


def test_the_plan_is_sections_and_a_step_is_the_item_with_its_provenance_in_the_foot(tmp_path):
    from uuid import uuid4
    seed(tmp_path).close()
    c = app_for(tmp_path)
    r = c.post("/kids/Alex/check-in/step", data=dict(title="Pick up the form", family_account="", next_step="Bring it home", owner="Alex",
               planned_for="2026-09-15", minutes="20", state="planned", position="", request_key=str(uuid4()), revision="0"), follow_redirects=False)
    assert r.status_code == 303
    body = c.get("/kids/Alex/plan").text
    # A section/details tag's `class="sec..."` need not be its first attribute (`_must_finish.html`
    # and `_plan_panel.html` carry `id` first, for their own anchors) -- the lookahead finds it
    # wherever it sits in the tag.
    heads = re.findall(r'<(?:section|details)(?=[^>]*\sclass="sec)[^>]*>\s*(?:<div class="sec-head">|<summary>)<h3[^>]*>([^<]*)</h3>', body)
    assert "Must finish" in heads and "Our next steps" in heads
    assert "Worth checking" not in heads and "Waiting on the school" not in heads       # the Plan says the rest in one line (re-critique 2026-09-30)
    assert body.index(">Must finish<") < body.index(">Our next steps<") < body.index('class="review-line"')
    checkin_heads = re.findall(r'<(?:section|details)(?=[^>]*\sclass="sec)[^>]*>\s*(?:<div class="sec-head">|<summary>)<h3[^>]*>([^<]*)</h3>', c.get("/kids/Alex/check-in").text)
    assert "Worth checking" in checkin_heads and "Waiting on the school" in checkin_heads
    step = re.search(r'<div class="item step">.*?<div class="item-foot">(.*?)</div>\s*</div>', body, re.S)
    assert step and "Edit step" in step.group(1) and re.search(r'<span class="stamp">Recorded \w{3} 9/15', step.group(1))
    assert re.search(r'<p class="ours">Alex · 20 min</p>', body)
    assert "checkin-intro" not in body and 'class="eyebrow"' not in body


def test_a_finished_check_in_shows_in_the_state_line(tmp_path):
    from uuid import uuid4
    seed(tmp_path).close()
    c = app_for(tmp_path)
    r = c.post("/kids/Alex/check-in/finish", data={"available_minutes": "40", "next_check": "2026-09-14", "summary": "Biology first.",
                                                   "recorded_by": "Mom", "request_key": str(uuid4())}, follow_redirects=False)
    assert r.status_code == 303
    line = re.search(r'<p class="tab-hint">(.*?)</p>', c.get("/kids/Alex/check-in").text, re.S).group(1)
    assert "Last check-in" in line and "recorded by Mom" in line and "time to check in" in line and "What we agreed: Biology first." in line


# --- §3 every other page ----------------------------------------------------------------------------

def test_today_open_work_and_a_class_page_head_their_sections_the_one_way(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    today = c.get("/").text
    # Today's kids are day boxes on a planner spread, not cards (the Student Planner, Today).
    assert re.search(r'<section class="sec kids"[^>]*>\s*<div class="mf-spread today-spread">', today)
    assert 'class="outcome-line"' in today and 'class="record"' not in today
    open_work = c.get("/open").text
    assert open_work.count('<section class="sec kid"') == 2
    course = c.get("/kids/Alex").text
    cid = re.search(r'/kids/Alex/courses/(\d+)', course).group(1)
    page = c.get(f"/kids/Alex/courses/{cid}").text
    heads = re.findall(r'<section class="sec[^"]*"[^>]*>\s*<div class="sec-head"><h3>([^<]*)</h3>', page)
    assert heads == ["Assignments"]                                  # the grade strip and the two folds head themselves (the class's record)


# --- §9 what this retired ---------------------------------------------------------------------------

RETIRED = (".q ", ".q.", ".q{", ".record", ".mf-row", ".plan-panel", ".plan-card", ".review-card", ".review-grid",
           ".section-head", ".quiet-head", ".workspace-heading", ".school-evidence", ".review-note", ".family-account",
           ".mf-paper", ".witness", ".eyebrow", ".qmark", ".checkin-intro", ".plan-total", ".next-step")
GREENS = ("#286454", "#214f43", "#edf5f1", "#45655e", "#eef3ef", "#aa7c32", "#b7cdc5", "#c9d8cd", "#a2bdb3", "#4f5754", "#6e8f85", "#725017", "#f4f6f4", "#edf6ee", "#eaf1fa")


@pytest.mark.parametrize("selector", RETIRED)
def test_the_stylesheet_has_no_rule_for_a_retired_class(selector):
    assert selector not in CSS, selector


@pytest.mark.parametrize("colour", GREENS)
def test_the_check_ins_own_palette_is_gone(colour):
    assert colour.lower() not in CSS.lower(), colour


@pytest.mark.parametrize("name", sorted(p.name for p in TEMPLATES.glob("*.html")))
def test_no_template_uses_a_retired_class(name):
    src = (TEMPLATES / name).read_text(encoding="utf-8")
    for cls in ("q card", "record\"", "mf-row", "plan-panel", "plan-card", "review-card", "review-grid", "section-head",
                "quiet-head", "workspace-heading", "school-evidence", "review-note", "family-account", "mf-paper",
                "witness", "eyebrow", "qmark", "checkin-intro", "plan-total", "next-step"):
        assert f'class="{cls}' not in src and f' {cls}"' not in src, f"{name} uses {cls}"


def test_every_radius_and_gap_is_a_token():
    """The documented exceptions: the rail's links and buttons (6px), the chips (10px pill), the
    chooser's 12px buttons, the mark's 6px, the stale banner's 4px, the note's 2px swatch."""
    body = CSS.split(":root", 1)[1]
    for m in re.finditer(r"border-radius:\s*([^;]+);", body):
        v = m.group(1).strip()
        assert v in ("var(--radius)", "6px", "10px", "12px", "4px", "2px", "50%"), v
