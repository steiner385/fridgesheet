"""Turning user text into a file name.

A report's name and title are the parent's own words, and both reach the filesystem -- the
archive copy through `Report.archive_name`, the download through `Content-Disposition`. One
function, so a title that is safe for one is safe for the other; it lives here rather than in
`dates.py` because that module is about date text and nothing else.
"""
from __future__ import annotations


def safe_name(text: str, fallback: str = "report") -> str:
    """`text` reduced to what a file name needs: letters, digits, spaces, dashes, underscores.

    Everything else -- quotes, separators, dots, control characters -- is dropped rather than
    escaped, so the result can never be a path, a parent directory, or a header that ends early.
    """
    safe = "".join(ch for ch in text if ch.isalnum() or ch in " -_").strip()
    return safe or fallback
