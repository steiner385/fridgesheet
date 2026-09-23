"""packaging/pick_version.py: the version release.yml releases for a merge to main, with no
human bumping one by hand for the ordinary case (docs/release-checklist.md, "release on
merge"). pyproject.toml is the floor: a deliberate bump there wins outright, so that is how a
minor or major release starts; otherwise the latest published tag's patch number goes up by
one.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# pick_version.py lives in packaging/, not the fridgesheet package, so load it directly by
# path rather than trying to make packaging/ importable as a package (test_restamp_snapshot.py
# does the same for packaging/windows/restamp_snapshot.py).
_spec = importlib.util.spec_from_file_location("pick_version", ROOT / "packaging" / "pick_version.py")
pick_version = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = pick_version
_spec.loader.exec_module(pick_version)


def test_an_ordinary_merge_bumps_the_latest_tags_patch():
    assert pick_version.next_version("0.5.0", "v0.5.0") == "0.5.1"


def test_a_deliberate_pyproject_bump_wins_outright():
    assert pick_version.next_version("0.6.0", "v0.5.0") == "0.6.0"


def test_a_pyproject_version_behind_the_latest_tag_still_bumps_the_tag():
    # e.g. main merged a revert, or the tag moved on by hand -- the release must still be
    # newer than what is already published, never a repeat of an old pyproject value.
    assert pick_version.next_version("0.5.0", "v0.5.3") == "0.5.4"


def test_no_tags_yet_releases_exactly_the_pyproject_version():
    assert pick_version.next_version("0.5.0", None) == "0.5.0"


def test_rejects_a_malformed_version():
    import pytest
    with pytest.raises(ValueError):
        pick_version.next_version("not-a-version", "v0.5.0")
