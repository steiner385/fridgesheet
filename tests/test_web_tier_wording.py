"""The words on the page follow the reader.

Same rows, same actions, plainer words. The fixture's Quiz 1 is Canvas-missing and HAC-graded
-- it carries both a status word and a `disagree` badge, so one row exercises both paths.
"""
from __future__ import annotations

import html

from tests.web_fixtures import app_for, seed


def _client(home, **grades):
    """A client whose config.toml carries these grades.

    `web_fixtures.app_for` builds `config.Settings(home=home)` and never reads config.toml --
    only `AppState.reload()` does that (app.py:62-72). So the file is written first and the
    state reloaded once, which is also what the Settings page does after a save.
    """
    if grades:
        p = home / "config.toml"
        text = p.read_text(encoding="utf-8") if p.exists() else ""
        rows = ", ".join(f"{k} = {v}" for k, v in grades.items())
        p.write_text(text + f"""
[kids]
grades = {{ {rows} }}
""", encoding="utf-8")
    c = app_for(home)
    c.app.state.fridgesheet.reload()
    return c


#: `phrase` returns a plain `str`, autoescaped like everything else on the page -- it has to
#: stay that way, because an untranslated word can be Canvas's own grade text, not vocabulary
#: (see `phrase`'s comment in `web/app.py`). So a phrase with a real apostrophe, like "Teacher
#: hasn't got it", lands in the response as `hasn&#39;t got it`. Tests that check for such a
#: phrase compare against the unescaped body instead of asserting the impossible: that this
#: one filter's output alone skips autoescaping.


def test_a_young_reader_sees_the_plain_words(tmp_path):
    seed(tmp_path).close()
    body = html.unescape(_client(tmp_path, Alex=5).get("/kids/Alex?show=all").text)
    assert "Teacher hasn't got it" in body
    assert ">Missing<" not in body


def test_a_middle_reader_sees_the_middle_words(tmp_path):
    seed(tmp_path).close()
    body = _client(tmp_path, Alex=7).get("/kids/Alex?show=all").text
    assert "Marked missing" in body


def test_an_older_reader_sees_exactly_what_ships_today(tmp_path):
    seed(tmp_path).close()
    body = html.unescape(_client(tmp_path, Alex=9).get("/kids/Alex?show=all").text)
    assert "Missing" in body and "Teacher hasn't got it" not in body


def test_no_grade_set_renders_the_shipped_words(tmp_path):
    seed(tmp_path).close()
    body = html.unescape(_client(tmp_path).get("/kids/Alex?show=all").text)
    assert "Missing" in body and "Teacher hasn't got it" not in body


def test_the_reconcile_kinds_follow_the_reader_too(tmp_path):
    seed(tmp_path).close()
    body = _client(tmp_path, Alex=5).get("/kids/Alex?show=all").text
    assert "Ask your teacher" in body          # `disagree` on Quiz 1
    assert ">disagree<" not in body


def test_an_apostrophe_phrase_stays_escaped(tmp_path):
    """Pins autoescaping itself: `phrase` must never be marked safe (e.g. wrapped in
    `markupsafe.Markup`), because an untranslated word can be Canvas's own grade text. If
    someone re-adds that wrapper, this is the test that catches it -- the raw apostrophe
    would appear unescaped in the response body."""
    seed(tmp_path).close()
    body = _client(tmp_path, Alex=5).get("/kids/Alex?show=all").text
    assert "hasn&#39;t" in body
    assert "hasn't" not in body


def test_open_work_shows_the_plain_words_too(tmp_path):
    """/open lists every kid on one page, and only Alex has a grade set here -- so the check
    is scoped to Alex's own <section>, not the whole body: Sam's rows are correctly still the
    adult words, the same as any kid with no grade set."""
    seed(tmp_path).close()
    body = html.unescape(_client(tmp_path, Alex=5).get("/open").text)
    start = body.index('id="Alex"')
    end = body.index("<section", start + 1)
    alex_section = body[start:end]
    assert "Teacher hasn't got it" in alex_section
    assert ">Missing<" not in alex_section
