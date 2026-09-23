"""Picks the version release.yml releases for a merge to main, so an ordinary merge needs no
human to bump a version by hand.

pyproject.toml is the floor. If its version is newer than the latest published tag, that is a
deliberate bump and it releases exactly -- the way a minor or major release starts. Otherwise
the latest tag's patch number goes up by one, so an ordinary merge is a patch release and
pyproject.toml's committed value is left alone between deliberate bumps.
"""
from __future__ import annotations

import re
import sys

_PATTERN = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")


def _parse(version: str) -> tuple[int, int, int]:
    m = _PATTERN.fullmatch(version.strip())
    if not m:
        raise ValueError(f"not a x.y.z version: {version!r}")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def next_version(pyproject_version: str, latest_tag: str | None) -> str:
    py = _parse(pyproject_version)
    if not latest_tag:
        return pyproject_version
    major, minor, patch = _parse(latest_tag)
    if py > (major, minor, patch):
        return pyproject_version
    return f"{major}.{minor}.{patch + 1}"


if __name__ == "__main__":
    pyproject_version = sys.argv[1]
    latest_tag = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None
    print(next_version(pyproject_version, latest_tag))
