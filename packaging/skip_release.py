"""Whether a merge commit opts a release-on-merge run out (release.yml, "Check for a
[skip release] merge commit").

The marker only counts on a line of its own, the way a git trailer does. A plain
`contains(message, '[skip release]')` in release.yml's first cut caught PR #61's own commit,
whose message *explained* the marker in prose ("...opt out with [skip release]") rather than
using it -- `contains` cannot tell an instruction from a mention of it.
"""
from __future__ import annotations

import sys

MARKER = "[skip release]"


def should_skip(commit_message: str) -> bool:
    return any(line.strip().casefold() == MARKER for line in commit_message.splitlines())


if __name__ == "__main__":
    print("true" if should_skip(sys.stdin.read()) else "false")
