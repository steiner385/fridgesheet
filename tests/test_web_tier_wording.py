"""The words on the page follow the reader.

Same rows, same actions, plainer words. Sam's Cell diagram is Canvas-missing with no HAC
grade, so its row carries the "Missing" status word; Alex's Participation is a question, so
its card carries the question and answer words (web/verdicts.py).
"""
from __future__ import annotations

import html
import re

from tests.web_fixtures import client_with_grades, seed


#: `phrase` returns a plain `str`, autoescaped like everything else on the page -- it has to
#: stay that way, because an untranslated word can be Canvas's own grade text, not vocabulary
#: (see `phrase`'s comment in `web/app.py`). So a phrase with a real apostrophe, like "Teacher
#: hasn't got it", lands in the response as `hasn&#39;t got it`. Tests that check for such a
#: phrase compare against the unescaped body instead of asserting the impossible: that this
#: one filter's output alone skips autoescaping.


def test_a_young_reader_sees_the_plain_words(tmp_path):
    seed(tmp_path).close()
    body = html.unescape(client_with_grades(tmp_path, Sam=5).get("/kids/Sam?show=all").text)
    assert "Teacher hasn't got it" in body
    assert ">Missing<" not in body


def test_a_middle_reader_sees_the_middle_words(tmp_path):
    seed(tmp_path).close()
    body = client_with_grades(tmp_path, Sam=7).get("/kids/Sam?show=all").text
    assert "Marked missing" in body


def test_an_older_reader_sees_exactly_what_ships_today(tmp_path):
    seed(tmp_path).close()
    body = html.unescape(client_with_grades(tmp_path, Sam=9).get("/kids/Sam?show=all").text)
    assert "Missing" in body and "Teacher hasn't got it" not in body


def test_no_grade_set_renders_the_shipped_words(tmp_path):
    seed(tmp_path).close()
    body = html.unescape(client_with_grades(tmp_path).get("/kids/Sam?show=all").text)
    assert "Missing" in body and "Teacher hasn't got it" not in body


def test_no_grade_set_renders_words_not_table_keys(tmp_path):
    """The regression PR #27 shipped: `phrase(word, "")` returning the raw table key instead
    of the `older` phrase. The verdict words are keys too ("where.still_ungraded")."""
    seed(tmp_path).close()
    body = client_with_grades(tmp_path).get("/kids/Alex?show=all").text
    assert "No grade, longer than usual" in body and "Was it handed in?" in body
    import re
    assert not re.search(r"\b(where|ask|facts|a)\.[a-z_]+\b", body.split("<body", 1)[1]), "a raw phrase key reached the page"


def test_the_questions_follow_the_reader_too(tmp_path):
    seed(tmp_path).close()
    body = client_with_grades(tmp_path, Alex=5).get("/kids/Alex?show=all").text
    assert "Did you hand it in?" in body          # Participation's question, for a fifth grader
    assert "Was it handed in?" not in body


def test_an_apostrophe_phrase_stays_escaped(tmp_path):
    """Pins autoescaping itself: `phrase` must never be marked safe (e.g. wrapped in
    `markupsafe.Markup`), because an untranslated word can be Canvas's own grade text. If
    someone re-adds that wrapper, this is the test that catches it -- the raw apostrophe
    would appear unescaped in the response body."""
    seed(tmp_path).close()
    body = client_with_grades(tmp_path, Sam=5).get("/kids/Sam?show=all").text
    assert "hasn&#39;t" in body
    assert "hasn't" not in body


def _row(body: str, item_id: int) -> str:
    """One row's markup, so an assertion can't pass on some other row's text."""
    import re
    m = re.search(rf'id="row-{item_id}">(.*?)</tr>', body, re.S)
    assert m, f"no row for item {item_id}"
    return m.group(1)


def test_a_young_reader_sees_the_due_hour_as_a_part_of_day(tmp_path):
    """Quiz 1 is a Canvas row due 9/12 at 23:59 -- "evening", the same timestamp `due_time`
    would print as "11:59pm", said as the part of the day it already is."""
    conn = seed(tmp_path)
    iid = conn.execute("SELECT id FROM items WHERE name = 'Quiz 1'").fetchone()["id"]
    conn.close()
    body = html.unescape(client_with_grades(tmp_path, Alex=5).get("/kids/Alex?show=all").text)
    row = _row(body, iid)
    assert "evening" in row
    assert "11:59pm" not in row


def test_an_older_reader_still_sees_the_clock(tmp_path):
    """Proves the branch actually branches: without this, a template that always took the
    `early` path would still pass the test above."""
    conn = seed(tmp_path)
    iid = conn.execute("SELECT id FROM items WHERE name = 'Quiz 1'").fetchone()["id"]
    conn.close()
    body = html.unescape(client_with_grades(tmp_path, Alex=9).get("/kids/Alex?show=all").text)
    row = _row(body, iid)
    assert "11:59pm" in row
    assert "evening" not in row


def test_a_hac_only_row_shows_neither_even_at_the_youngest_tier(tmp_path):
    """Participation is HAC-only: no clock time to show, and so no part of day to name
    either, even for the one tier that would otherwise show one -- the `from_canvas` guard,
    proven end to end rather than only at the unit level."""
    conn = seed(tmp_path)
    iid = conn.execute("SELECT id FROM items WHERE name = 'Participation'").fetchone()["id"]
    conn.close()
    body = html.unescape(client_with_grades(tmp_path, Alex=5).get("/kids/Alex?show=all").text)
    row = _row(body, iid)
    assert "morning" not in row and "afternoon" not in row and "evening" not in row
    assert "am" not in row.lower() and "pm" not in row.lower()


def test_open_work_shows_the_plain_words_too(tmp_path):
    """/open lists every kid on one page, and only Alex has a grade set here -- so the check
    is scoped to Alex's own <section>, not the whole body: Sam's rows are correctly still the
    adult words, the same as any kid with no grade set."""
    seed(tmp_path).close()
    body = html.unescape(client_with_grades(tmp_path, Alex=5).get("/open").text)
    start = body.index('id="Alex"')
    end = body.index("<section", start + 1)
    alex_section = body[start:end]
    # Open work shows the verdict in the kid's words, as Assignments does (#85): Participation
    # has had no grade for a week, which the early tier hears as "No grade yet".
    assert "No grade yet" in alex_section
    assert "No grade after a week" not in alex_section


# --- kids' UX audit F3: one instruction sentence per section, and it follows the reader ------------

def _intro(body):
    return re.search(r'<div class="checkin-intro">(.*?)</div>', body, re.S).group(1)


def _client(tmp_path, **grades):
    """One seeded home per client: `client_with_grades` appends a `[kids]` table to config.toml,
    so two grades in one home would be two tables."""
    home = tmp_path / ("g" + "".join(f"{k}{v}" for k, v in grades.items()) or "none")
    home.mkdir()
    seed(home).close()
    return client_with_grades(home, **grades)


def test_the_check_in_says_one_thing_before_the_cards(tmp_path):
    """Eighty words of framing stood before the first card, identical at every tier; children
    skip instruction paragraphs and teens leave. One short instruction, then the cards."""
    for grade in (5, 9):
        body = _client(tmp_path, Sam=grade).get("/kids/Sam/check-in").text
        text = re.sub(r"<[^>]+>", " ", _intro(body))
        assert len(text.split()) <= 40, f"grade {grade}: {text.split()}"
        assert "lag behind" not in body


def test_the_check_in_copy_follows_the_reader(tmp_path):
    young = html.unescape(_client(tmp_path, Sam=5).get("/kids/Sam/check-in").text)
    assert "You could do these" in young and "Ask before you assume" in young        # queue hint; Safety quiz's zero
    older = html.unescape(_client(tmp_path, Sam=9).get("/kids/Sam/check-in").text)
    assert "possibilities, not tonight" in older and "ask before assuming" in older


def test_the_sources_line_follows_the_reader(tmp_path):
    assert "Canvas is where teachers post work." in _client(tmp_path, Sam=5).get("/kids/Sam").text
    assert "HAC (Home Access Center) is the official gradebook" in _client(tmp_path).get("/kids/Sam").text
