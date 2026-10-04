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


# --- GitHub's squash body lists every commit of a multi-commit PR (2026-10-04, PR #245) ------------

SQUASH_HEAD = "The report card: every class one line with its official average (#245)\n\n"


def _section(subject: str, body: str = "", marker: bool = False) -> str:
    return f"* {subject}\n\n{body}\n" + ("\n[skip release]\n" if marker else "") + "\nCo-Authored-By: Someone <x@y>\n\n"


def test_a_marker_in_two_of_eleven_squashed_commits_does_not_skip_the_feature():
    # The exact bug: the spec and plan commits of PR #245 carried the marker; GitHub listed them
    # in the squash body; the release of the whole feature was skipped.
    msg = SQUASH_HEAD + _section("Spec", "design", marker=True) + _section("Plan", "tasks", marker=True) + "".join(
        _section(f"code change {i}") for i in range(9))
    assert not skip_release.should_skip(msg)


def test_a_marker_in_every_squashed_commit_still_skips_a_docs_only_pr():
    msg = "Docs: feature map (#300)\n\n" + _section("docs one", marker=True) + _section("docs two", marker=True)
    assert skip_release.should_skip(msg)


def test_a_marker_in_the_squash_messages_own_head_skips_whatever_the_list_says():
    msg = "Docs: feature map (#300)\n\n[skip release]\n\n" + _section("docs one") + _section("code-looking subject")
    assert skip_release.should_skip(msg)


def test_a_single_commit_squash_keeps_the_old_behaviour():
    assert skip_release.should_skip("docs: fix a typo (#301)\n\nOne paragraph.\n\n[skip release]\n")
    assert not skip_release.should_skip("fix: a real change (#302)\n\nOne paragraph.\n")
