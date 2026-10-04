"""Questions as the parent's answering page (the Student Planner; the surface brief in
.impeccable/surfaces/, 2026-09-30): one ruled list for the whole house in the order the school's
deadlines close, the kid named first on each line, answered in place in the parent's voice; who
has nothing to ask as one pencil line under the title; beneath the list, per kid, the let-go
sentence as a pencil line and the waiting lines and unpaired twins as quiet folds."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from fridgesheet.web import db
from fridgesheet.web.stores import flags
from tests.web_fixtures import NOW, app_for, client_with_grades, seed

CSS = (Path(__file__).resolve().parents[1] / "fridgesheet" / "web" / "static" / "app.css").read_text(encoding="utf-8")
LATER = datetime(2026, 9, 30, 14, 0, tzinfo=NOW.tzinfo)


def _rule(selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"no {selector} rule"
    return m.group(1)


def _id(home, name):
    conn = db.open_db(home)
    i = conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]
    conn.close()
    return i


def test_the_page_is_one_list_for_the_house_with_the_kid_on_each_line(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/questions").text
    assert body.count('<section class="sec') == 1                                           # one list, no section per kid
    assert re.search(r'<section class="sec household-questions"[^>]*>\s*<div class="sec-head"><h3 id="to-answer">To answer</h3><span id="qcount-page" class="count">1</span></div>\s*<div class="planner-main to-answer">', body)
    assert re.search(r'<div class="item ask" id="q-\d+" data-focus>\s*<div class="item-head"><span class="name"><b tabindex="-1" data-focus-target>Participation</b></span><span class="meta"><span class="kid">Alex</span> · Honors English 9', body)
    assert "Was it handed in?" in body and 'class="default">Yes, handed in</button>' in body
    assert '<p class="quiet-kid muted">Nothing to ask about Sam\'s work.</p>' in body
    assert "Open Alex's work" not in body and 'class="kid-questions"' not in body and 'class="lines' not in body


def test_the_list_speaks_in_the_parents_voice_whatever_the_kids_tier(tmp_path):
    seed(tmp_path).close()
    c = client_with_grades(tmp_path, Alex=5)
    body = c.get("/questions").text
    assert "Was it handed in?" in body and "Did you hand it in?" not in body                # the parent's words, not the fifth-grader's
    assert "data-tier" not in body[body.index("<main"):]
    pid = _id(tmp_path, "Participation")
    # An answer swapped into the list's slot keeps the parent's voice, and so does its Undo.
    done = c.post(f"/items/{pid}/answer", data={"answer": "done", "prev": "", "slot": f"q-{pid}"}).text
    assert f'id="q-{pid}"' in done and "Did you" not in done
    back = c.post(f"/items/{pid}/undo", data={"prev": "", "slot": f"q-{pid}"}).text
    assert "Was it handed in?" in back and "Did you hand it in?" not in back
    # The kid's own page still asks in the kid's words.
    assert "Did you hand it in?" in c.get("/kids/Alex?show=all").text
    # The answered line keeps its head (the name struck, the kid, the class) over the done-line.
    assert re.match(rf'\s*<div class="item ok" id="q-{pid}" data-focus', done) and '<span class="kid">Alex</span> · Honors English 9' in done
    assert 'class="line ok done-line"' in done and "<svg" in done and "✓" not in done
    assert 'id="qcount-page" class="count" hx-swap-oob="true">0</span>' in done or 'id="qcount-page" class="count" hx-swap-oob="true"></span>' in done


def test_an_all_quiet_house_says_so_once(tmp_path):
    seed(tmp_path).close()
    pid = _id(tmp_path, "Participation")
    conn = db.open_db(tmp_path)
    flags.set_flag(conn, pid, "done", now="2026-09-15T13:00:00-04:00")
    conn.close()
    body = app_for(tmp_path).get("/questions").text
    assert "quiet-kid" not in body and body.count("Nothing to ask") == 1
    assert '<p class="muted nothing-to-answer">Nothing to ask about anyone\'s work tonight.</p>' in body


def test_questions_are_ordered_by_the_deadline_that_closes_first(tmp_path):
    """Three days on, Lab notebook (due 9/10, window to 9/24) has become a question beside
    Participation (due 9/08, window to 9/22): the sooner-closing window comes first."""
    from datetime import timedelta
    seed(tmp_path).close()
    body = app_for(tmp_path, now=NOW + timedelta(days=3)).get("/questions").text
    lines = re.findall(r'<div class="item ask" id="q-(\d+)"', body)
    assert len(lines) == 2
    assert body.index("Participation") < body.index("Lab notebook")


def test_the_let_go_line_and_its_undo_sit_beneath_the_list(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path, now=LATER)
    body = c.get("/questions?kid=Alex").text
    bar = re.search(r'<form class="let-go" method="post" action="/questions/let-go" data-confirm="([^"]*)">(.*?)</form>', body, re.S)
    assert bar and "too late for credit" in bar.group(2) and "<button>Let all " in bar.group(2)
    assert body.index('class="sec household-questions"') < body.index('class="let-go"')
    after = c.post("/questions/let-go", data={"kid": "Alex"}).text
    assert re.search(r'<form class="let-go undo" method="post" action="/questions/let-go/undo" role="status">', after)
    assert '<button class="link">Undo</button>' in after


def test_waiting_and_unpaired_fold_per_kid_beneath_the_list(tmp_path):
    seed(tmp_path).close()
    lab = _id(tmp_path, "Lab notebook")
    conn = db.open_db(tmp_path)
    flags.set_flag(conn, lab, "ask_teacher", now="2026-09-15T08:00:00-04:00")
    conn.close()
    body = app_for(tmp_path).get("/questions").text
    fold = re.search(r'<details class="sec quiet waiting-fold"><summary><h3>Waiting on the teacher · Alex</h3><span class="count">1</span></summary>\s*<div class="waiting">(.*?)</div>\s*</details>', body, re.S)
    assert fold and f'<div class="line grey" id="q-{lab}">' in fold.group(1) and fold.group(1).count("mailto:") == 1
    assert "◷" not in fold.group(1) and "<svg" in fold.group(1) and " · <a href=\"mailto:" in fold.group(1)        # a drawn mark, parted facts
    assert 'id="qcount-page" class="count">1</span>' in body                                   # the one question still open
    assert body.index("waiting-fold") > body.index('class="sec household-questions"')
    assert "Waiting on the teacher · Sam" not in body                                       # a kid with nothing waiting has no fold


def test_the_list_and_its_lines_are_drawn_in_the_planners_rules():
    assert "max-width: var(--page-max)" in _rule(".to-answer")
    assert "border-top: 1px solid var(--rule)" in _rule(".to-answer > .item:first-child")
    assert "font-weight: 650" in _rule(".item-head .meta .kid")
    let_go = _rule(".let-go")
    assert "color: var(--muted)" in let_go and "font-size: var(--type-small)" in let_go and "background" not in let_go and "border" not in let_go
    waiting = _rule(".waiting > .line")
    assert "border-bottom: 1px solid var(--rule)" in waiting and "background" not in waiting
    coarse = "\n".join(re.findall(r"@media \(pointer: coarse\)\s*\{(.*?)\n\}", CSS, re.S))
    assert re.search(r"\.waiting \.line a\s*\{[^}]*min-height: 44px", coarse)
