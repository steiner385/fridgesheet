"""One flag, one set of words (#129).

The same stored flag was shown under five names: the row badge said "ignore", the menu
"Let it go", the confirmation "Ignored", the filter "let go" and the record "let it go".
`verdicts.py` promised a family answer is "never the stored flag name" and the badge broke
it. One label table (`phrasing.FLAG_LABELS`) now feeds every surface, in the three forms a
page actually needs: the button, the state and the confirmation. And the same item's record
read differently on the detail card and the check-in card; one partial serves both.
"""
from __future__ import annotations

import html
import re

import pytest

from fridgesheet.web import phrasing, tiers
from fridgesheet.web.stores import flags
from tests.web_fixtures import app_for, client_with_grades, seed

#: The stored names, and the half-translated forms that used to leak ("Ignored", "ask teacher").
RAW = re.compile(r"\b(follow_up|ask_teacher|too_late|ignored?|ask teacher|marked follow up)\b", re.IGNORECASE)


def _text(page: str) -> str:
    """The words a reader sees: tags (and so every `value="ignore"`) stripped, entities decoded."""
    return html.unescape(re.sub(r"<[^>]+>", " ", page))


def _id(tmp_path, name: str) -> int:
    conn = seed(tmp_path)
    try:
        return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]
    finally:
        conn.close()


def test_the_label_table_covers_every_flag_the_store_knows():
    assert set(phrasing.FLAG_LABELS) == set(flags.FLAGS)
    for flag in flags.FLAGS:
        for form in phrasing.FLAG_FORMS:
            for tier in list(tiers.TIERS) + [""]:
                assert phrasing.flag_label(flag, form, tier), (flag, form, tier)
    # The menu is the table's button column, in the store's order; the store never spells labels.
    assert flags.CHOICES == tuple((f, phrasing.flag_label(f, "button")) for f in flags.FLAGS)


def test_the_three_forms_are_distinct_where_english_needs_them_to_be():
    assert phrasing.flag_label("ignore", "button") == "Let it go"
    assert phrasing.flag_label("ignore", "state") == "let go"
    assert phrasing.flag_label("ignore", "confirm") == "Let go"
    assert phrasing.flag_label("ask_teacher", "state") == "asked the teacher"
    assert phrasing.flag_label("follow_up", "state") == "following up"


@pytest.mark.parametrize("flag", flags.FLAGS)
def test_every_surface_says_a_flag_with_the_same_words(tmp_path, flag):
    """Confirmation, menu button, menu status line, row badge, filter option, the check-in's
    record and the change log: one answer, one vocabulary, and never the stored name."""
    lab = _id(tmp_path, "Lab notebook")
    c = app_for(tmp_path)
    button, state, confirm = (phrasing.flag_label(flag, form) for form in phrasing.FLAG_FORMS)
    saved = c.post(f"/items/{lab}/flag", data={"flag": flag, "text": "because"}).text
    assert confirm in _text(saved)
    detail = c.get(f"/items/{lab}").text
    menu = re.search(r'<form class="flagmenu".*?</form>', detail, re.S).group(0)
    assert f">{button}<" in html.unescape(menu)
    assert f"Your answer: {state}" in _text(menu) and "Flag:" not in _text(menu)
    kid = c.get("/kids/Alex?show=all").text
    row = re.search(rf'<tr id="row-{lab}".*?</tr>', kid, re.S).group(0)
    assert re.search(rf'class="badge flag"[^>]*>{re.escape(state)} \d+/\d+<', row), row
    option = re.search(rf'<option value="{flag}"[^>]*>(.*?)</option>', kid).group(1)
    assert option == state
    step = c.get(f"/kids/Alex/check-in/step?item_id={lab}").text
    assert f"Your answer: {state} · because" in _text(step)
    changes = c.get("/changes").text
    assert f"{state}: because" in _text(changes)
    for page in (saved, detail, kid, step, changes):
        assert not RAW.search(_text(page)), RAW.search(_text(page)).group(0)


def test_clearing_says_so_in_the_same_vocabulary(tmp_path):
    lab = _id(tmp_path, "Lab notebook")
    c = app_for(tmp_path)
    c.post(f"/items/{lab}/flag", data={"flag": "ignore", "text": ""})
    cleared = c.post(f"/items/{lab}/flag", data={"flag": "clear"}).text
    assert "Answer cleared" in _text(cleared) and not RAW.search(_text(cleared))
    assert "Your answer: none" in _text(cleared)


def test_a_stale_answer_quotes_the_button_the_family_pressed():
    from fridgesheet.web import verdicts
    v = verdicts.Verdict("question", "stale_answer", {"flag": "ignore", "when": "9/10", "change": "Canvas now says missing"})
    said = verdicts.say("facts.stale_answer", "", verdicts.family_facts(v))
    assert "“Let it go”" in said and not RAW.search(said)


def test_the_printed_sheets_marker_is_the_same_button_in_capitals():
    from fridgesheet import sheet
    assert sheet.marker("follow_up") == "FOLLOW UP" and sheet.marker("ask_teacher") == "ASK THE TEACHER"


# --- the record: one partial, whichever card shows it (#46) -------------------------------------

def _sources(body: str) -> list[str]:
    return re.findall(r'<div class="source">.*?</div>', body, re.S)


@pytest.mark.parametrize("name, kid", [("Quiz 1", "Alex"), ("Essay draft", "Alex"), ("Lab notebook", "Alex"),
                                       ("Participation", "Alex"), ("Safety quiz", "Sam"), ("Reading log", "Alex")])
def test_the_record_reads_identically_on_the_detail_card_and_the_step_page(tmp_path, name, kid):
    """The detail said "handed in", "nothing submitted", "no grade"; the check-in said
    "submitted … (late)", "no submission recorded", "no grade posted". One partial now."""
    iid = _id(tmp_path, name)
    c = app_for(tmp_path)
    detail, step = c.get(f"/items/{iid}").text, c.get(f"/kids/{kid}/check-in/step?item_id={iid}").text
    assert _sources(detail) and _sources(detail) == _sources(step)
    for old in ("no submission recorded", "no online submission expected", "(late)", "<span>no grade</span>"):
        assert old not in detail and old not in step, old
    assert not re.search(r"\bsubmitted [A-Z]", detail + step)        # "submitted Mon 9/14": now "handed in"


def test_the_record_states_the_facts_the_sources_hold(tmp_path):
    c = app_for(tmp_path)
    quiz = _text(c.get(f"/items/{_id(tmp_path, 'Quiz 1')}").text)
    assert "marked missing" in quiz and "28 of 30" in quiz
    essay = _text(c.get(f"/items/{_id(tmp_path, 'Essay draft')}").text)
    assert "handed in Mon 9/14 8:00 PM" in essay and "no grade posted" in essay
    step = _text(c.get(f"/kids/Sam/check-in/step?item_id={_id(tmp_path, 'Safety quiz')}").text)
    assert "Canvas" in step and "nothing submitted" in step and "0 of 10" in step
    # One way to say a score on a source line, the verdict sentence's way ("28 of 30").
    lines = " ".join(_sources(c.get(f"/items/{_id(tmp_path, 'Quiz 1')}").text) + _sources(c.get(f"/kids/Sam/check-in/step?item_id={_id(tmp_path, 'Safety quiz')}").text))
    assert "28/30" not in lines and "0/10" not in lines


@pytest.mark.parametrize("tier", list(tiers.TIERS) + [""])
def test_every_tier_gets_every_source_line_the_oldest_gets(tmp_path_factory, tier):
    """The record is tiered now (persona review, 4.1); tiering changes the words, never the
    number of facts stated."""
    grade = {"early": 5, "middle": 7, "older": 11, "": None}[tier]

    def lines(t):
        home = tmp_path_factory.mktemp(f"record-{t or 'none'}")
        conn = seed(home)
        quiz = conn.execute("SELECT id FROM items WHERE name = 'Quiz 1'").fetchone()["id"]
        conn.close()
        c = client_with_grades(home, Alex=grade) if grade is not None else client_with_grades(home)
        return _sources(c.get(f"/items/{quiz}").text)
    assert len(lines(tier)) == len(lines("older")) == 2


def test_a_young_reader_gets_the_record_in_plainer_words(tmp_path):
    conn = seed(tmp_path)
    quiz = conn.execute("SELECT id FROM items WHERE name = 'Quiz 1'").fetchone()["id"]
    conn.close()
    lines = _text(" ".join(_sources(client_with_grades(tmp_path, Alex=5).get(f"/items/{quiz}").text)))
    assert phrasing.phrase("record.missing", "early") in lines and "marked missing" not in lines


def test_the_email_to_the_teacher_cites_the_record_in_the_same_words(tmp_path):
    """`mailto_body` had a third copy of the record's words."""
    from urllib.parse import unquote
    c = app_for(tmp_path)
    detail = c.get(f"/items/{_id(tmp_path, 'Quiz 1')}").text
    body = unquote(re.search(r"body=([^\"]+)", detail).group(1))
    assert "Canvas: marked missing" in body and "HAC: 28 of 30" in body
