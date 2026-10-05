"""A class's page as the class's record (the Student Planner; the surface brief in
.impeccable/surfaces/, 2026-09-30): the grade's history as a strip of small boxes, the official
number first and the newest on the highlighter; the teacher and the sources fold as pencil lines;
"How it moved" and Notes as quiet folds; the class's assignments as the weekly pages."""
from __future__ import annotations

import re
from pathlib import Path

from fridgesheet.web.stores import notes
from tests.web_fixtures import app_for, seed

CSS = (Path(__file__).resolve().parents[1] / "fridgesheet" / "web" / "static" / "app.css").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"no {selector} rule"
    return m.group(1)


def _course(tmp_path, short="Honors English 9", source="canvas"):
    conn = seed(tmp_path)
    cid = conn.execute("SELECT id FROM courses WHERE source = ? AND short_name = ?", (source, short)).fetchone()["id"]
    conn.close()
    return cid


def _strip(body: str) -> str:
    return body.split('class="week-strip grade-strip"', 1)[1].split("</ol>", 1)[0]


def test_the_grade_strip_puts_the_official_number_first_and_highlights_the_newest(tmp_path):
    cid = _course(tmp_path)
    body = app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text
    strip = _strip(body)
    cells = re.findall(r'<li class="mf-section day-cell([^"]*)">', strip)
    assert cells == [" official", " newest"]
    assert re.search(r'<li class="mf-section day-cell official"><h4><span class="day-word">Official</span></h4>\s*<p><span class="big">88.0</span></p><p class="whose">HAC average · as of 9/11</p></li>', strip)
    assert re.search(r'<li class="mf-section day-cell newest"><h4><span class="day-word">Tue 9/15</span></h4>\s*<p><span class="big">91.2</span> A-</p><p class="whose">Canvas current</p></li>', strip)
    # The retired grade-history table and the three cards stay gone; the categories table under
    # "How it's figured" (spec 2026-10-03 §7.2) is the one table this page draws.
    assert '<table class="items' not in body and "Grade history" not in body and '<div class="cards">' not in body


def test_the_twins_page_reads_its_own_number_and_names_the_other(tmp_path):
    cid = _course(tmp_path, source="hac")
    body = app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text
    strip = _strip(body)
    # HAC is the official grades source, so this page's own newest cell carries "· official" and
    # Canvas' number stands last, in pencil.
    assert re.search(r'day-cell newest"><h4><span class="day-word">[^<]+</span></h4>\s*<p><span class="big">88.0</span></p><p class="whose">HAC average · official</p>', strip)
    assert re.search(r'<li class="mf-section day-cell other"><h4><span class="date">Canvas</span></h4>\s*<p><span class="big">91.2</span> A-</p><p class="whose">Canvas current</p></li>', strip)
    assert "official" not in strip.split('day-cell other', 1)[1]


def test_the_teacher_and_the_sources_are_pencil_lines_under_the_strip(tmp_path):
    cid = _course(tmp_path)
    body = app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text
    assert '<p class="teacher-line muted">Michael Hoch · <a href="mailto:hoch@example.org">hoch@example.org</a> · Also in HAC as Honors English 9 S1</p>' in body
    assert re.search(r'<details class="sources-fold"><summary>Sources for this class: Canvas for scores, HAC for the average · <span class="change">change</span></summary>\s*<form class="sources-form" method="post" action="/kids/Alex/courses/\d+/sources">', body)
    assert body.count("<button>Save</button>") == 1 and 'class="primary"' not in body       # no filled primary on this page


def test_a_rule_of_its_own_keeps_the_sources_fold_open(tmp_path):
    cid = _course(tmp_path)
    c = app_for(tmp_path)
    assert '<details class="sources-fold">' in c.get(f"/kids/Alex/courses/{cid}").text
    c.post(f"/kids/Alex/courses/{cid}/sources", data={"assignments": "hac", "grades": ""})
    body = c.get(f"/kids/Alex/courses/{cid}").text
    assert '<details class="sources-fold" open>' in body and "Sources for this class: HAC for scores, HAC for the average" in body


def test_how_it_moved_and_notes_are_quiet_folds(tmp_path):
    cid = _course(tmp_path)
    conn = seed(tmp_path)
    notes.add(conn, "course", cid, "Syllabus says 7-day late window", now="2026-09-15T14:30:00-04:00")
    conn.close()
    body = app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text
    assert re.search(r'<details class="sec quiet grade-moves"><summary><h3>How it moved</h3><span class="count">1 refresh</span></summary>\s*<div class="chart-holder"', body)
    assert re.search(r'<details class="sec quiet class-notes" open><summary><h3>Notes</h3><span class="count">1</span></summary>', body)
    assert "Syllabus says" in body
    assert body.index("grade-strip") < body.index("teacher-line") < body.index("sources-fold") < body.index("grade-moves") < body.index("class-notes") < body.index('<h3>Assignments</h3>')


def test_the_assignments_are_the_weekly_pages_with_every_row_from_both_gradebooks(tmp_path):
    cid = _course(tmp_path)
    body = app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text
    assert re.search(r'<section class="sec class-work"[^>]*>\s*<div class="sec-head"><h3>Assignments</h3><span class="count">7 listed</span></div>\s*(?:<p id="type-links"[^>]*>.*?</p>\s*)?<div id="items">', body, re.S)   # the type filter's links may sit between (assignment types §6.3)
    assert re.search(r'<p class="sort" role="group" aria-label="Sort by">', body)
    assert body.count('class="mf-section week') >= 2 and "_item_rows" not in body
    rows = re.findall(r'id="row-(\d+)"', body)
    assert len(rows) == 7 and len(set(rows)) == 7                                    # Canvas and its HAC twin, once each (#183)
    for name in ("Quiz 1", "Essay draft", "Participation"):
        assert body.count(f">{name}</a>") == 1, name
    assert "sources-hint" in body
    # Every line is this class: its name in the meta is a word, not seven links to this page.
    assert re.search(r'<span class="meta">Honors English 9 · ', body) and f'href="/kids/Alex/courses/{cid}">Honors English 9</a>' not in body


def test_the_strip_and_the_folds_are_drawn_in_the_planners_rules():
    assert "max-width: var(--page-max)" in _rule(".class-record")
    assert "repeat(auto-fill, minmax(150px, 1fr))" in _rule(".grade-strip")
    narrow = "\n".join(re.findall(r"@media \(max-width: 1023px\)\s*\{(.*?)\n\}", CSS, re.S))
    assert re.search(r"\.class-record \.grade-strip\s*\{[^}]*grid-auto-flow: column", narrow)        # one row on a phone
    assert "background: var(--hl-due)" in _rule(".grade-strip > li.newest > h4 > .day-word")
    assert "color: var(--muted)" in _rule(".grade-strip > li.other > p, .grade-strip > li.empty > p")
    assert "color: var(--muted)" in _rule(".sources-fold > summary") and "list-style: none" in _rule(".sources-fold > summary")
    assert "text-decoration: underline" in _rule(".sources-fold > summary .change")
    coarse = "\n".join(re.findall(r"@media \(pointer: coarse\)\s*\{(.*?)\n\}", CSS, re.S))
    assert re.search(r"\.sources-fold > summary, \.teacher-line a \{[^}]*min-height: 44px", coarse)
    assert "table.work" not in CSS


# --- How it's figured (spec 2026-10-03 §7.2) --------------------------------------------------------

def _account_section(body: str) -> str:
    assert 'class="sec grade-account"' in body, "no How it's figured section"
    return body.split('class="sec grade-account"', 1)[1].split("</section>", 1)[0]


def test_how_its_figured_shows_hacs_categories_their_share_and_the_check(tmp_path):
    cid = _course(tmp_path, source="hac")
    body = app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text
    sec = _account_section(body)
    assert "<h3 id=\"account-head\">How it's figured</h3>" in sec
    assert '<span class="count">2 categories</span>' in sec
    assert '<div class="table-wrap"><table class="categories">' in sec.replace("\n", "")
    assert re.search(r"<td>Assignments</td>\s*<td>28</td><td>30</td><td>93\.33%</td><td>60%</td>", sec)
    assert re.search(r"<td>Daily</td>\s*<td>16</td><td>20</td><td>80\.00%</td><td>40%</td>", sec)
    assert re.search(r"<tfoot>.*<td>Total</td><td>44</td><td>50</td><td>88\.00%</td>", sec, re.S)
    assert re.search(r'<p class="check ok">✓ Adds up: 44 of 50 points\. HAC says 88\.00\.</p>', sec)


def test_the_twins_page_leads_with_the_official_account_and_says_what_canvas_counts(tmp_path):
    cid = _course(tmp_path, source="canvas")
    sec = _account_section(app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text)
    assert sec.index("<h4>HAC</h4>") < sec.index("<h4>Canvas</h4>")                   # official first, whatever page it is
    assert "Canvas counts graded work only" in sec


def test_a_class_with_no_breakdown_is_one_sentence(tmp_path):
    cid = _course(tmp_path, short="Algebra I", source="hac")
    sec = _account_section(app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text)
    assert "<table" not in sec
    assert "HAC says 79.50" in sec and "nothing to rebuild it from" in sec


def test_a_category_with_nothing_possible_prints_a_dash(tmp_path):
    conn = seed(tmp_path)
    cid = conn.execute("SELECT id FROM courses WHERE source = 'hac' AND short_name = 'Honors English 9'").fetchone()["id"]
    rid = conn.execute("SELECT MAX(refresh_id) FROM category_observations").fetchone()[0]
    with conn:
        conn.execute("INSERT INTO category_observations(refresh_id, course_id, category, earned, possible, percent) VALUES (?, ?, 'Project', 0, 0, '')", (rid, cid))
    conn.close()
    sec = _account_section(app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text)
    assert re.search(r"<td>Project</td>\s*<td>0</td><td>0</td><td>—</td><td>0%</td>", sec)


def test_the_account_is_drawn_in_the_planners_rules():
    for sel in (".grade-account table.categories", ".grade-account .check", ".grade-account .check.off"):
        _rule(sel)
    assert "var(--warn)" in _rule(".grade-account .check.off")                     # off is the one red the planner allows
    assert "text-align: right" in _rule(".grade-account table.categories th + th, .grade-account table.categories td + td")


def test_a_canvas_led_mismatch_is_worded_as_canvas_not_hac(tmp_path):
    """Sam's Science with its HAC twin unpaired: Canvas leads, its one graded row is a zero, so
    the groups rebuild to 0 against a current of 85; the red line must name Canvas."""
    conn = seed(tmp_path)
    cid = conn.execute("SELECT id FROM courses WHERE source = 'canvas' AND short_name = 'Science 7'").fetchone()["id"]
    with conn:
        conn.execute("UPDATE courses SET peer_course_id = NULL WHERE id = ? OR peer_course_id = ?", (cid, cid))
    conn.close()
    sec = _account_section(app_for(tmp_path).get(f"/kids/Sam/courses/{cid}").text)
    assert '<p class="check off">The groups add up to 0.00; Canvas says 85.00.</p>' in sec
    assert "HAC says" not in sec


def test_a_hidden_canvas_only_class_is_one_sentence_naming_canvas(tmp_path):
    conn = seed(tmp_path)
    sid = conn.execute("SELECT id FROM students WHERE key = 'Sam'").fetchone()["id"]
    with conn:
        rid = conn.execute("INSERT INTO refreshes(started_at, sources, ok) VALUES ('2026-09-15T14:00:00-04:00', '{}', 1)").lastrowid
        cid = conn.execute("INSERT INTO courses(student_id, source, name, short_name) VALUES (?, 'canvas', 'Technology 7-2027-Dunn', 'Technology 7')", (sid,)).lastrowid
        conn.execute("INSERT INTO grade_observations(refresh_id, course_id, average, letter, current, final, last_updated) VALUES (?, ?, NULL, NULL, NULL, NULL, NULL)", (rid, cid))
    conn.close()
    sec = _account_section(app_for(tmp_path).get(f"/kids/Sam/courses/{cid}").text)
    assert "Canvas hides this class" in sec and "either gradebook" not in sec and "<table" not in sec


# --- What moves it (spec 2026-10-04 §7.2) ----------------------------------------------------------

def _moves(body: str) -> str:
    assert 'class="sec what-moves-it"' in body, "no What moves it section"
    return body.split('class="sec what-moves-it"', 1)[1].split("</section>", 1)[0]


def test_what_moves_it_lists_levers_with_worth_badges_under_the_reach_line(tmp_path):
    cid = _course(tmp_path, source="hac")
    sec = _moves(app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text)
    assert ">What moves it</h3>" in sec and '<span class="count">5 levers</span>' in sec
    assert '<p class="lead">Best move: Participation (10 pts), still accepted: worth up to +2.0 now, and left blank it would cost 14.7. An A needs 10 of the next 50 points.</p>' in sec
    assert sec.index("Participation") < sec.index("Lab notebook") < sec.index("Vocabulary")   # missing work first: its zero is at stake
    assert sec.count('<span class="badge">+2.0</span>') == 5
    assert "Not counted yet · accepted until 9/22 · late credit unknown, ask · left blank it would cost 14.7" in sec    # Participation: due 9/08, 14 days, credit "?"
    assert "Due Sun 9/20 · not counted yet" in sec                                        # Reading log (2026-09-20 is a Sunday)


def test_an_unsound_class_lists_points_not_average_points(tmp_path):
    conn = seed(tmp_path)
    cid = conn.execute("SELECT id FROM courses WHERE source = 'hac' AND short_name = 'Honors English 9'").fetchone()["id"]
    with conn:
        conn.execute("UPDATE grade_observations SET average = 70.0 WHERE course_id = ?", (cid,))     # 44/50 no longer rebuilds it
    conn.close()
    sec = _moves(app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text)
    assert "5 rows still open, 50 points." in sec and 'class="badge">+' not in sec


def test_a_class_with_nothing_open_is_one_sentence(tmp_path):
    cid = _course(tmp_path, short="Algebra I", source="hac")
    sec = _moves(app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text)
    assert "<ol" not in sec and "decides it" in sec


def test_a_lever_worth_nothing_on_the_average_shows_no_plus_zero_badge(tmp_path):
    conn = seed(tmp_path)
    cid = conn.execute("SELECT id FROM courses WHERE source = 'hac' AND short_name = 'Honors English 9'").fetchone()["id"]
    with conn:
        conn.execute("UPDATE grade_observations SET average = 100.0 WHERE course_id = ?", (cid,))
        conn.execute("UPDATE category_observations SET earned = possible WHERE course_id = ?", (cid,))   # 50/50: at the top
        conn.execute("UPDATE item_observations SET score = points FROM items WHERE items.id = item_observations.item_id AND item_observations.source = 'hac' AND item_observations.score IS NOT NULL")
    conn.close()
    sec = _moves(app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text)
    assert "+0.0" not in sec


def test_a_weighted_class_says_it_averages_its_category_percents(tmp_path):
    conn = seed(tmp_path)
    cid = conn.execute("SELECT id FROM courses WHERE source = 'hac' AND short_name = 'Honors English 9'").fetchone()["id"]
    with conn:
        conn.execute("UPDATE category_observations SET weight = CASE category WHEN 'Assignments' THEN 3 ELSE 2 END WHERE course_id = ?", (cid,))
    conn.close()
    sec = _account_section(app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text)
    assert "average of its category percents" in sec and "average is total points" not in sec   # not the total-points lead
    assert re.search(r"<td>Assignments</td>\s*<td>28</td><td>30</td><td>93\.33%</td><td>60%</td>", sec)
    assert re.search(r'<p class="check ok">✓ Adds up: the average of 2 category percents, as HAC weights them\. HAC says 88\.00\.</p>', sec)
