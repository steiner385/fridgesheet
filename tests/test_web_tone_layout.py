"""Second persona pass, batch D3: last checked vs last changed (#75), a decided list that stays
short (#76), tone (#77), layout and accessibility nits (#78)."""
from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

from fridgesheet.web import verdicts
from fridgesheet.web.stores import flags
from tests.web_fixtures import NOW, app_for, history, seed

WEB = Path(__file__).resolve().parents[1] / "fridgesheet" / "web"
CSS = (WEB / "static" / "app.css").read_text(encoding="utf-8")


def _id(conn, name):
    return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]


# --- #75 ----------------------------------------------------------------------------------------

def test_the_record_says_when_each_source_was_checked_and_when_it_changed(tmp_path):
    conn = history(tmp_path)                            # three refreshes; Quiz 1's HAC grade posted on day 2
    qid = _id(conn, "Quiz 1")
    conn.close()
    body = app_for(tmp_path).get(f"/items/{qid}").text
    hac = re.search(r'<span class="src">HAC(.*?)</span>', body, re.S).group(1)
    assert "checked Tue 9/15" in hac and "changed Mon 9/14" in hac


# --- #76 ----------------------------------------------------------------------------------------

def test_old_decided_lines_fold_under_earlier(tmp_path):
    seed(tmp_path).close()
    later = app_for(tmp_path, now=NOW + timedelta(days=10)).get("/kids/Alex").text
    assert re.search(r"<summary>Earlier \(1\)</summary>", later)          # Quiz 1, settled 10 days ago
    assert "Earlier (" not in app_for(tmp_path).get("/kids/Alex").text     # today: still recent


def test_a_kid_with_nothing_to_answer_is_told_so(tmp_path):
    seed(tmp_path).close()
    assert "Nothing to answer." in app_for(tmp_path).get("/kids/Sam").text     # said to the child (kids' UX audit F7)


# --- #77 ----------------------------------------------------------------------------------------

def test_the_app_does_not_speak_for_the_school(tmp_path):
    seed(tmp_path).close()
    assert "automatic" not in verdicts.say("facts.graded_in_hac", "", {"hac": "28 of 30"})
    assert verdicts.say("where.past_credit", "", {"school": "Canvas marks it missing"}).startswith("Canvas marks it missing")
    body = app_for(tmp_path).get("/kids/Alex").text
    assert "Decided for you" not in body and "Settled by the records" in body


def test_family_answers_use_family_words_everywhere(tmp_path):
    conn = seed(tmp_path)
    lab = _id(conn, "Lab notebook")
    flags.set_flag(conn, lab, "ignore", now="2026-09-12T08:00:00-04:00")
    conn.close()
    c = app_for(tmp_path)
    detail = c.get(f"/items/{lab}").text
    menu = re.search(r'<form class="flagmenu".*?</form>', detail, re.S).group(0)
    assert ">Let it go<" in menu and ">It's done<" in menu.replace("&#39;", "'") and ">ignore<" not in menu
    assert "You answered" in detail and "You flagged" not in detail
    step = c.get(f"/kids/Alex/check-in/step?item_id={lab}").text
    assert "Existing family flag" not in step and "I handed this in on paper" not in step
    assert "missing flag" not in c.get("/kids/Alex/check-in").text


def test_a_stale_answer_quotes_the_answer_in_family_words():
    v = verdicts.Verdict("question", "stale_answer", {"flag": "ignore", "when": "9/10", "change": "Canvas now says missing"})
    assert "ignore" not in verdicts.say("facts.stale_answer", "", verdicts.family_facts(v))


# --- #78 ----------------------------------------------------------------------------------------

def test_layout_and_names(tmp_path):
    assert re.search(r"\.section-head\s*\{[^}]*flex-wrap:\s*wrap", CSS)
    # `.qmark` is sized by the tier token, which resolves at the root to the 13px that shipped.
    root = re.search(r":root\s*\{([^}]*)\}", CSS).group(1)
    tokens = {f"var(--{k})": int(v) for k, v in re.findall(r"--(type-[a-z]+):\s*(\d+)px", root)}
    for sel in (r"\.qmark", r"\.rail \.count"):
        size = re.search(sel + r"\s*\{[^}]*font-size:\s*([^;]+);", CSS)
        assert size, sel
        px = tokens.get(size.group(1).strip()) or int(re.match(r"(\d+)px", size.group(1)).group(1))
        assert px >= 13, sel
    seed(tmp_path).close()
    c = app_for(tmp_path)
    body = c.get("/kids/Alex").text
    assert not re.search(r"<a [^>]*hx-post=", body), "a link that POSTs should be a button"
    assert re.search(r'<button[^>]*aria-label="Not right\? Quiz 1"', body)
    assert "Asks you on" in body and "Asks you after" not in body
    conn = seed(tmp_path)
    qid = _id(conn, "Quiz 1")
    conn.close()
    detail = c.get(f"/items/{qid}").text
    assert detail.index("data-focus-target") < detail.index("data-close-detail")          # Close after the heading
    assert re.search(r'data-close-detail[^>]*aria-label="Close Quiz 1"', detail)


def test_check_in_answer_buttons_sit_in_a_row_like_on_assignments():
    """Found in Chrome after #79: the check-in's review cards reuse _answers.html but the row
    styling was scoped to .q cards, so the buttons stacked one per line."""
    assert re.search(r"\.review-card \.answers[^{]*\{[^}]*display:\s*flex", CSS)
