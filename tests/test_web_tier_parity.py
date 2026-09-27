"""Simplification must never become concealment.

This is the failure this feature is most exposed to, and the one a child would never report:
they would not know an assignment had been left off their page. So every tier renders the
same rows -- different words, same facts.
"""
from __future__ import annotations

import re

import pytest

from fridgesheet.web import tiers
from tests.web_fixtures import app_for, client_with_grades, seed


GRADE_OF = {"early": 5, "middle": 7, "older": 11, "": None}


def _row_ids(tmp_path_factory, tier: str, path: str) -> set[str]:
    home = tmp_path_factory.mktemp(f"parity-{tier or 'none'}")
    seed(home).close()
    c = client_with_grades(home, Alex=GRADE_OF[tier]) if GRADE_OF[tier] is not None else client_with_grades(home)
    return set(re.findall(r'id="row-(\d+)"', c.get(path).text))


@pytest.mark.parametrize("tier", list(tiers.TIERS) + [""])
@pytest.mark.parametrize("path", ["/kids/Alex?show=all", "/kids/Alex?show=open", "/open"])
def test_every_tier_renders_every_row_the_oldest_gets(tmp_path_factory, tier, path):
    older = _row_ids(tmp_path_factory, "older", path)
    assert older, "the fixture must render rows for this to mean anything"
    assert _row_ids(tmp_path_factory, tier, path) == older


def test_no_tier_hides_a_badge_the_oldest_gets(tmp_path_factory):
    """The words differ; the number of things said about a row does not."""
    def badges(tier):
        home = tmp_path_factory.mktemp(f"badge-{tier or 'none'}")
        seed(home).close()
        c = client_with_grades(home, Alex=GRADE_OF[tier]) if GRADE_OF[tier] is not None else client_with_grades(home)
        body = c.get("/kids/Alex?show=all").text
        return len(re.findall(r'<span class="badge', body))
    for tier in list(tiers.TIERS) + [""]:
        assert badges(tier) == badges("older"), tier


def _question_ids(tmp_path_factory, tier: str) -> set[str]:
    home = tmp_path_factory.mktemp(f"questions-{tier or 'none'}")
    seed(home).close()
    c = client_with_grades(home, Alex=GRADE_OF[tier]) if GRADE_OF[tier] is not None else client_with_grades(home)
    return set(re.findall(r'id="q-(\d+)"', c.get("/kids/Alex").text))


@pytest.mark.parametrize("tier", list(tiers.TIERS) + [""])
def test_no_tier_hides_a_question_or_a_decided_or_waiting_line(tmp_path_factory, tier):
    """The questions, decided and waiting lines above the table (web/verdicts.py) are facts
    about the child's work too; a younger reader gets plainer words, never fewer of them."""
    older = _question_ids(tmp_path_factory, "older")
    assert older, "the fixture must render at least one question card or line"
    assert _question_ids(tmp_path_factory, tier) == older


def _ids_and_actions(client, path: str) -> tuple[set[str], int, int]:
    """The rows, questions and plan steps a page names, plus how many forms and buttons it
    offers -- every id and action a reader can act on, not the words around them."""
    body = client.get(path).text
    ids = set(re.findall(r'id="(?:row|qc|q)-(\d+)"', body))
    return ids, len(re.findall(r"<form", body)), len(re.findall(r"<button", body))


@pytest.mark.parametrize("path", ["/kids/Alex?show=all", "/kids/Alex/plan", "/kids/Alex/check-in"])
def test_kid_mode_and_family_mode_render_the_same_rows_and_actions(tmp_path, path):
    """Final review, finding 1: `test_web_tier_parity.py` ran only in family mode now that
    `app_for` defaults to a grown-up, so the parity rule this module is about (see the module
    docstring) had no kid-mode coverage at all. A grown-up reading `/kids/Alex...` and Alex
    reading the same address must see the same rows, questions, steps, forms and buttons --
    kid mode changes the rail and the words, never what is offered."""
    seed(tmp_path).close()
    family = app_for(tmp_path)
    kid = app_for(tmp_path)
    kid.cookies.set("fridgesheet_who", "Alex")
    family_seen, kid_seen = _ids_and_actions(family, path), _ids_and_actions(kid, path)
    assert family_seen[0], "the fixture must render at least one id for this to mean anything"
    assert family_seen == kid_seen
