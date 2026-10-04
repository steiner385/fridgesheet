"""Whether a merge commit opts a release-on-merge run out (release.yml, "Check for a
[skip release] merge commit").

The marker only counts on a line of its own, the way a git trailer does. A plain
`contains(message, '[skip release]')` in release.yml's first cut caught PR #61's own commit,
whose message *explained* the marker in prose ("...opt out with [skip release]") rather than
using it -- `contains` cannot tell an instruction from a mention of it.

GitHub's squash merge of a multi-commit PR writes the PR title as the message's head and then
lists every commit's message under a `* ` bullet. A marker inside that list belongs to one
commit, not to the merge: PR #245 shipped a whole feature whose spec and plan commits carried
the marker, and the release was skipped (2026-10-04). So a marker in the head always counts,
and a marker in the list counts only when every listed commit carries one -- a docs-only PR
whose every commit opted out, which is what the marker is for.
"""
from __future__ import annotations

import sys

MARKER = "[skip release]"


def _has_marker(text: str) -> bool:
    return any(line.strip().casefold() == MARKER for line in text.splitlines())


def should_skip(commit_message: str) -> bool:
    lines = commit_message.splitlines()
    bullets = [i for i, line in enumerate(lines) if line.startswith("* ")]
    if not bullets:
        return _has_marker(commit_message)
    head = "\n".join(lines[:bullets[0]])
    if _has_marker(head):
        return True
    bounds = bullets + [len(lines)]
    sections = ["\n".join(lines[a:b]) for a, b in zip(bounds, bounds[1:])]
    return all(_has_marker(s) for s in sections)


if __name__ == "__main__":
    print("true" if should_skip(sys.stdin.read()) else "false")
