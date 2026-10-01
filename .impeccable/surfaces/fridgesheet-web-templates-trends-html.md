---
version: 1
slug: "fridgesheet-web-templates-trends-html"
primary_target: "fridgesheet/web/templates/trends.html"
related_targets: ["fridgesheet/web/routes/trends.py","fridgesheet/web/templates/_chart_canvas.html"]
---

# Surface brief: Trends (the year so far)

Scope: `/trends` (trends.html with `_chart_canvas.html`), the TIME page a parent reads once a
week, for the house or one kid (kid mode shows only that kid); Operate mode. Audience: the
parents; a child on their own device. Job: see how hand-ins are going, how each class's grade
has moved and how each week's work came out, over 4, 8 or 16 weeks (maintainer, 2026-10-01:
"the year so far, read at a glance"; the weekly numbers "the chart, with the table folded
beneath"; Kid and Weeks as "words in the sort line's grammar"). Proof: `outcomes.tally` over
everything due so far (the same numbers as Today), one grade line per class from the family's
grades source, the weekly outcomes by the week the work was due, the longest-open list.
Constraints: the chart configs stay (`tests/test_web_trends_page.py`); the table's rows stay as
`<tr><td>` cells that equal the chart's datasets; an empty database says one thing ("Not enough
history yet"); `?kid=` and `?weeks=` as now; nothing filled on the page. The world is settled
(DESIGN.md, The Student Planner); this brief records composition only. Unresolved: whether the
charts themselves (Chart.js defaults: grey axis titles, a rounded key) get the planner's hand;
whether Changes follows as a ledger.

## Direction contract

THESIS: Trends is one printed page for the year: THE YEAR SO FAR along its top edge, the
hand-in record as its first line, each kid's grade chart and the weeks chart as the page's
figures with the numbers folded, and what has sat open longest in pencil at the foot. It
refuses the row of summary cards over charts and the dashboard of tiles.

OWN-WORLD: The Student Planner as documented: planner white with the faint ruling; the Kid and
Weeks choices as one pencil run-in line in the sort line's grammar, the chosen word in ink at
650; one paper page in the day-box rule with its label along the top edge ("THE YEAR SO FAR ·
last 8 weeks"), its parts as day rows in pencil (ON-TIME HAND-INS, GRADES, WORK DUE EACH WEEK,
OPEN THE LONGEST), the record line in body type with the percentage at 650 and "not done" in
Red Pen (the school's word), the charts drawn flat on the page with no box of their own, the
numbers behind a pencil fold, the longest open as pencil lines under hairlines. Recognisable with
the words removed: a pencil line, one ruled page with two figures and a few ruled lines at its
foot.

STORY: A parent opens Trends on Sunday, reads the record line, glances down each kid's grade
line and the weeks' bars, opens the numbers if a bar needs explaining, and sees at the foot
what has been sitting longest; a tap on a kid's name or a week count turns the same page to
that kid or that window.

FIRST VIEWPORT: The title and its intro. One pencil line: Kid all · Alex · Sam — Weeks 4 · 8 ·
16, the chosen words in ink. Then the page: THE YEAR SO FAR · last 8 weeks; ON-TIME HAND-INS
over "17% on time so far · 1 on time · 0 late · 5 not done · 0 on paper · 2 unknown"; GRADES
over the caption and Alex's chart, then Sam's; WORK DUE EACH WEEK over the stacked bar and
"▸ The numbers"; OPEN THE LONGEST over Homework 4 · 26 days, Participation · 7 days, …. No
primary on this page.

FORM: The report card page, position 4 of the re-rolled grounded list, dealt as the lead and
locked by the maintainer over the grades-and-weeks strips (5) and charts first (3); the first
hand's lead (the kids as tabs) was re-rolled on the maintainer's own interview answer; seed key
c137f15a, re-roll 1; code-led, no image generation. Signature interaction: a word in the pencil
line turns the page to a kid or a window; the numbers fold opens in place; nothing else moves.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the
verdict, DESIGN.md, and every shipping raster carrying its provenance.
