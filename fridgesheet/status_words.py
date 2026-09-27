"""The status word table: the one place the sheet and the web page both read it (#137).

Kept apart from `sheet.py` (which imports reportlab at module scope to build the PDF) so a
web page can say a status word without pulling reportlab into the app process.
"""
from __future__ import annotations

from .web import phrasing

#: The web page's status phrase -> the sheet's word for it: one table, read this way to print
#: the page's rows (`reports.open_work.sheet_status`, `web/stores/items.sheet_status`) and the
#: other way to say a word in a kid's tier (`status_word`), so the two surfaces cannot name one
#: fact differently (#137).
STATUS_WORD = {"Missing": "MISSING", "Zero": "ZERO", "Late, ungraded": "LATE", "Paper, check": "PAPER — CHECK",
               "In class, check": "IN CLASS — CHECK", "HAC, no grade": "HAC — NO GRADE"}

#: The sheet's status word -> the web page's, so the phrase table can say it for the kid's tier.
#: Older and no-tier sections keep the capitals the parent knows from the legend.
_STATUS_KEY = {word: phrase for phrase, word in STATUS_WORD.items()}


def status_word(status: str, tier: str) -> str:
    """"MISSING" for a parent; "Teacher hasn't got it" for a 5th grader; "Due today" rather than
    DUE TODAY for either young tier. Same fact, same colour, the kid's words."""
    if tier not in ("early", "middle"):
        return status
    key = _STATUS_KEY.get(status)
    if key:
        return phrasing.phrase(key, tier)
    head, _, rest = status.partition(" ")       # DUE TODAY / DUE TONIGHT / DUE TOMORROW / DUE TUE
    rest = rest.lower() if rest.lower() in ("today", "tonight", "tomorrow") else rest.title()
    return f"{head.title()} {rest}".strip()
