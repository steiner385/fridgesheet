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
               "Outside Canvas, check": "OUTSIDE CANVAS — CHECK", "HAC, no grade": "HAC — NO GRADE"}

#: The sheet's status word -> the web page's, so the phrase table can say it for the kid's tier.
#: Older and no-tier sections keep the capitals the parent knows from the legend.
_STATUS_KEY = {word: phrase for phrase, word in STATUS_WORD.items()}

#: The sheet's word -> the colour it is printed in, named for what the colour means: `red` is
#: the school saying not in (the sheet's RED), `late` handed in after the deadline (AMBER),
#: `check` work the school cannot see yet (PURPLE), `due` a deadline ahead (BLUE). The page
#: reads this table for a row's rule and word (`_item.html`) and `sheet.STATUS_COLOR` is the
#: same table in reportlab colours, so a row cannot be red on screen and blue on the fridge
#: (critique 2026-09-29: DUE TODAY was red on the Plan because every word was).
STATUS_TONE = {"MISSING": "red", "ZERO": "red", "LATE": "late",
               "PAPER — CHECK": "check", "OUTSIDE CANVAS — CHECK": "check", "HAC — NO GRADE": "check"}


def status_tone(status: str) -> str:
    """"red", "late", "check" or "due" for a sheet word; "" for anything the sheet has no
    colour for (a phrase the page says on its own, such as "Submitted, ungraded")."""
    if status in STATUS_TONE:
        return STATUS_TONE[status]
    return "due" if status.startswith("DUE ") else ""


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
