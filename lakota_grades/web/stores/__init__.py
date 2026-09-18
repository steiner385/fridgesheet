"""One module per table family. Every function takes the connection first and leaves no
transaction open, so callers never hold one across a request: connections are autocommit
(`isolation_level=None`), which makes a single statement commit by itself, and anything that
must be all-or-nothing opens `BEGIN IMMEDIATE` and closes it under `with conn:`."""
from __future__ import annotations


def num(v) -> str:
    """A score or points value the way a parent reads it: 9.0 -> '9', 88.5 -> '88.5',
    12.5033 -> '12.5'.

    Canvas hands back whatever float its weighting produced, and `:g` alone printed it
    verbatim -- `12.5033/50` sat in the Status column of the live app (#40 item 6). Two
    decimals is one more than any gradebook shows; `:g` then drops the trailing zeros so a
    whole number stays a whole number. Shared by the Kid page and the Changes feed so the
    same score cannot read two ways."""
    return "" if v is None else f"{round(v, 2):g}"
