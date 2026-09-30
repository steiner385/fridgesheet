---
version: 1
slug: "fridgesheet-web-templates-open-html"
primary_target: "fridgesheet/web/templates/open.html"
related_targets: ["fridgesheet/web/templates/_item.html","fridgesheet/web/routes/open.py"]
---

# Surface brief: Open work (the sheet on a screen)

Scope: `/open` (open.html), the printed sheet's two questions per kid on a screen: what is past
due and still fixable, then what is coming due; Operate mode. Audience: a parent or caregiver
checking the whole window, on the kitchen computer or a phone; a child reaches it only by
address (the kid rail folds it away). Job: read one child's sheet whole, as it will print, and
open a line's record; nothing else is done here (maintainer, 2026-09-30: "a print preview").
Proof: the same rows the sheet prints, in the sheet's order (soonest-closing window first, then
by due date), with the sheet's word in the sheet's colour, when credit ends, and the sheet's
trailers. Constraints: parity with the sheet (`tests/test_open_work_parity.py`); the Not shown
links open exactly the set they count (#125); every kid's page is in the markup at every tier
(parity of rows); the trailer's words; "Nothing open. Nice work."; 44px tabs and main links,
24px secondary links; one filled primary per page (none here). The world is settled (DESIGN.md,
The Student Planner); this brief records composition only. Unresolved: whether a class's page
follows; whether the sheet's legend belongs on every planner page.

## Direction contract

THESIS: Open work turns the sheet one kid at a time: the kids are index tabs standing on the
ruled line, and the chosen kid's page lies beneath in the sheet's order, so a phone shows one
child's sheet whole. It refuses the per-kid stack of sortable tables and the PDF in a frame.

OWN-WORLD: The Student Planner as documented: planner white with the faint ruling; the kids'
tabs are the child tabs (body type, the current one paper white with the box rule on three
sides); each kid's sheet is one paper page in the day-box rule, its label along the top edge
(ALEX — OPEN WORK · 6 open); inside, "Still fixable" and "Coming due" as day-row heads in
pencil, the second parted from the first by the printed rule; every assignment a checkbox line
under a hairline with the sheet's word on its highlighter and the credit-until sentence in the
facts; the trailer in pencil at the page's foot; the sheet's legend once, under the page, its
words on their highlighters. Recognisable with the words removed: a row of tabs, one ruled page
of checkbox lines split by a rule, a pencil line beneath.

STORY: A parent opens Open work and sees the first child's sheet as it will print tonight,
reads down it, taps a name to open the record in place, and taps the next child's tab; the
page turns. "Every kid" lays every page out at once.

FIRST VIEWPORT: The title and its one-line intro. Under them the kids as tabs on the box rule
(Alex 6 · Sam 2), the first pulled forward, "Every kid" as a quiet word at the tabs' right.
Then Alex's page: ALEX — OPEN WORK · 6 open along the top edge; a pencil head line (Wed 9/30 ·
next 14 days plus overdue within 14); STILL FIXABLE · 3, then the three lines soonest-closing
first, each with the sheet's word and "credit until Wed 10/7"; the printed rule; COMING DUE · 3
and its lines by due date; Not shown: 1 past the late-work window (10 pts) in pencil at the
foot. The legend beneath. No primary on this page.

FORM: One page at a time, position 5 of the ordered grounded list, dealt by the surface roll
and locked by the maintainer over the countdown (3) and the sheet's landscape (4); seed key
169d6a89; code-led, no image generation. Signature interaction: the tab moves and the page
turns in place (an htmx swap of the tabs and pages, a full load without script); a name opens
its record in place of the line; nothing else moves.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the
verdict, DESIGN.md, and every shipping raster carrying its provenance.
