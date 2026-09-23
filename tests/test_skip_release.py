"""packaging/skip_release.py: whether a merge commit opts out of release-on-merge.

The first cut used `contains(message, '[skip release]')` directly in release.yml, and PR #61's
own commit message tripped it -- the message *explained* the marker in prose ("a merge commit
can opt out with [skip release]"), and `contains` cannot tell an instruction from a mention.
The fix: the marker only counts on a line of its own, the way a git trailer does, not
anywhere in the message.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# skip_release.py lives in packaging/, not the fridgesheet package -- loaded directly by path
# the way test_pick_version.py loads packaging/pick_version.py.
_spec = importlib.util.spec_from_file_location("skip_release", ROOT / "packaging" / "skip_release.py")
skip_release = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = skip_release
_spec.loader.exec_module(skip_release)


def test_the_marker_on_its_own_line_skips():
    assert skip_release.should_skip("docs: fix a typo\n\n[skip release]\n")


def test_mentioning_the_marker_in_prose_does_not_skip():
    # The exact bug: PR #61's own commit explained the opt-out and tripped it.
    msg = "release on merge\n\na merge commit can opt out with [skip release]\n"
    assert not skip_release.should_skip(msg)


def test_an_ordinary_commit_does_not_skip():
    assert not skip_release.should_skip("Fix the reconcile card's focus order\n")


def test_the_marker_is_case_insensitive():
    assert skip_release.should_skip("chore\n\n[Skip Release]\n")


def test_the_marker_with_surrounding_whitespace_on_its_line_still_skips():
    assert skip_release.should_skip("chore\n\n  [skip release]  \n")
