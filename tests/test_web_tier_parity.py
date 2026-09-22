"""Simplification must never become concealment.

This is the failure this feature is most exposed to, and the one a child would never report:
they would not know an assignment had been left off their page. So every tier renders the
same rows -- different words, same facts.
"""
from __future__ import annotations

import re

import pytest

from fridgesheet.web import tiers
from tests.web_fixtures import client_with_grades, seed


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
