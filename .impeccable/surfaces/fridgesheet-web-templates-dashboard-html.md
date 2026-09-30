---
version: 1
slug: "fridgesheet-web-templates-dashboard-html"
primary_target: "fridgesheet/web/templates/dashboard.html"
related_targets: []
---

# Surface brief: Today (the household page)

Scope: `/` (dashboard.html), the page a parent opens on a phone at night and on the kitchen
computer in the morning; Operate mode. Audience: the parents and caregivers; the children reach it
only through the rail. Job: see what must be finished tonight across every child, answer a line
without leaving the page, and print or preview the sheet. Proof: each child's Must-finish lines
from the school record, the same rows and counts the Plan shows, the sheet's controls. Constraints:
the Print now two-step stays exactly as shipped; the tally arithmetic still matches the Plan
(red minus planned plus more); the School record fold stays; parity of rows and actions per child;
one filled primary per page (Print). The world is settled (DESIGN.md, The Student Planner);
this brief records composition only. Unresolved: whether the week row should reach beyond five
days, and whether Assignments adopts the same lines (next surface).

## Direction contract

THESIS: Today is the family's planner week: a five-day strip across the top with tonight
highlighted, and under it tonight's day box for each child with their lines answerable in place.
It refuses the dashboard of equal cards and the bare index of links.

OWN-WORLD: The Student Planner as documented: planner white, day boxes in the blue-grey rule with
labels along the top edge, checkbox lines, highlighter words, ballpoint only on links and the
default stroke, pencil-grey family lines, the faint ruling. The week strip is a row of five small
day boxes, the same rule and label as a day box, tonight's label on the yellow highlighter, each
holding the children's counts for that day in pencil grey. The sheet's controls form the page's
date header: one ruled strip under the title with the last sheet's line and the Refresh, Preview
and Print controls, the Print two-step unchanged.

STORY: A parent opens Today, reads the week at a glance, sees tonight's box for each child with
the lines that must be finished, taps an answer or opens the child's Plan, and prints the sheet
from the header when the morning comes.

FIRST VIEWPORT: The title and its intro line. Under them the sheet strip: what printed today (or
"No sheet built today yet"), then Refresh now, Refresh data first, Preview, Print now. Then the
week strip: five day boxes, TONIGHT · TUE 9/29 highlighted, then WED, THU, FRI, SAT, each with
"Alex 2 · Sam 1" in pencil grey. Then one day box per child side by side (stacked on a phone):
label "ALEX · TONIGHT", the tally line as the box's first line (the numeral, the words, the Plan
link), the questions line, then the Must-finish lines by tomorrow as planner lines with their
answers, then the family line (next check-in, steps today), the three links, and the School
record fold. The one filled primary is Print inside the two-step.

FORM: The week strip, position 5 of the ordered grounded list, dealt as the lead by the surface
roll and locked by the maintainer; seed key 484d9aac; code-led, no image generation. Signature
interaction: the same in-place strike on an answered line as on the Plan; nothing else moves.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the
verdict, DESIGN.md, and every shipping raster carrying its provenance.
