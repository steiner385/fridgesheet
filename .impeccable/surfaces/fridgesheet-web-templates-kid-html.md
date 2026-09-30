---
version: 1
slug: "fridgesheet-web-templates-kid-html"
primary_target: "fridgesheet/web/templates/kid.html"
related_targets: ["fridgesheet/web/templates/_item_rows.html","fridgesheet/web/templates/_verdict_sections.html"]
---

# Surface brief: Assignments (the child's page)

Scope: `/kids/{key}` (kid.html with `_item_rows.html` and `_verdict_sections.html`), the child's
own list of every assignment the school has recorded, read by the child in kid mode and by a
parent; Operate mode. Audience: the child at their tier ("you"), the parent checking one class or
one week. Job: see everything, find one assignment by week or class, answer the app's question on
the line it belongs to, and open a line's full record. Proof: the school's list, every row, with the
sheet's word in the sheet's colour. Constraints (maintainer, 2026-09-30): sorting by due, name and
standing stays; parity of rows and actions at every tier; the vocabulary table; one filled primary
per page (none here); 44px for buttons and main links, 24px for secondary links; the class page and
Open work keep `_item_rows.html` unchanged. The world is settled (DESIGN.md, The Student Planner);
this brief records composition only. Unresolved: whether the class page adopts the weekly pages;
whether the three child tabs collapse.

## Direction contract

THESIS: Assignments is the child's planner turned back page by page: every assignment sits on the
week it was due, this week's page first, earlier weeks beneath, settled weeks folded to one tally
line. It refuses the filterable data table this category ships and its opposite, the card feed.

OWN-WORLD: The Student Planner as documented: planner white with the faint ruling, one day box per
week in the blue-grey rule with WEEK OF MON 9/29 along its top edge, checkbox lines under
hairlines, the sheet's word as a highlighter stroke, ballpoint only on links and the default
answer's stroke, the family's step and note in pencil grey beneath the line, the day names as
small day labels inside the week. A settled week is a single folded line in the same label type.
Recognisable with the words removed: a stack of ruled boxes, the top one open and full of
checkbox lines, the ones below thinner and folded.

STORY: The child opens Assignments and sees this week's page: the lines due each day with the
sheet's word, the asked line offering its answers in place. They tap an answer and the line
strikes itself. A parent scrolls down the weeks, opens a settled one, and follows a name into its
record; sorting and the class picker narrow the same pages.

FIRST VIEWPORT: The child's name, the three tabs, and the ruled header line: Done so far, then the
run-in controls (Open · Everything, Class, More filters, Sort by Due · Assignment · Where it
stands). Then the first week box: WEEK OF MON 9/29 with its lines, the newest week first: each line
a checkbox, the name (a link to the record in place), the class and due in pencil grey, the sheet's
word on the highlighter, the ask line and answers when the app asks, the family's step beneath.
Overdue weeks follow in the same boxes, still-open lines first; weeks with nothing open fold to
one line with their tally (4 done · 1 late). No primary on this page.

FORM: The weekly pages, position 3 of the ordered grounded list, dealt as the lead by the surface
roll and locked by the maintainer; seed key d4a7b45f; code-led, no image generation. Signature
interaction: the same in-place strike on an answered line as on the Plan; a folded week opens in
place; nothing else moves.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the
verdict, DESIGN.md, and every shipping raster carrying its provenance.
