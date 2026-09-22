"""The words on the page follow the reader.

Same rows, same actions, plainer words. The fixture's Quiz 1 is Canvas-missing and HAC-graded
-- it carries both a status word and a `disagree` badge, so one row exercises both paths.
"""
from __future__ import annotations

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


def test_a_young_reader_sees_the_plain_words(tmp_path):
    seed(tmp_path).close()
    body = _client(tmp_path, Alex=5).get("/kids/Alex?show=all").text
    assert "Teacher hasn't got it" in body
    assert ">Missing<" not in body


def test_a_middle_reader_sees_the_middle_words(tmp_path):
    seed(tmp_path).close()
    body = _client(tmp_path, Alex=7).get("/kids/Alex?show=all").text
    assert "Marked missing" in body


def test_an_older_reader_sees_exactly_what_ships_today(tmp_path):
    seed(tmp_path).close()
    body = _client(tmp_path, Alex=9).get("/kids/Alex?show=all").text
    assert "Missing" in body and "Teacher hasn't got it" not in body


def test_no_grade_set_renders_the_shipped_words(tmp_path):
    seed(tmp_path).close()
    body = _client(tmp_path).get("/kids/Alex?show=all").text
    assert "Missing" in body and "Teacher hasn't got it" not in body


def test_the_reconcile_kinds_follow_the_reader_too(tmp_path):
    seed(tmp_path).close()
    body = _client(tmp_path, Alex=5).get("/kids/Alex?show=all").text
    assert "Ask your teacher" in body          # `disagree` on Quiz 1
    assert ">disagree<" not in body
