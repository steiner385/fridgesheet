---
version: 1
slug: "fridgesheet-web-templates-report_card-html"
primary_target: "fridgesheet/web/templates/report_card.html"
related_targets: ["fridgesheet/web/routes/report_card.py","fridgesheet/web/stores/grades.py","fridgesheet/web/templates/course.html"]
---

# Surface brief: the report card

Scope: `/kids/{key}/report-card` (report_card.html, with `_child_nav.html`), the fourth tab on
a child's pages, beside Plan, Assignments and Check-in; Operate mode. Audience: the kid reading
their own grades in their reading tier, and the parent checking a class or printing the page
for the fridge. Job: read every class's grade the way the paper report card reads, and see in
one sentence how the gradebook arrived at it (maintainer, 2026-10-03: "a report card view",
"a better understanding of the current class average and how it is calculated"). Proof: HAC's
own category subtotals, stored per refresh, and the check of their total against HAC's number
(`grading.Account.match`); the class page's "How it's figured" section holds the table. Constraints:
the same lines in every tier (`tests/test_web_tier_parity.py`); the title is the rail word
("Report card"); no `<h2>` but the page head's; numbers formatted before they reach a phrase;
Red Pen only where the school's number and ours disagree; prints as it stands. The world is
settled (DESIGN.md, The Student Planner); this brief records composition only. Unresolved:
whether a household whose HAC weights categories wants a weights editor (the account reads
"off" on every class until then); whether the fold's two paragraphs should move to the class page.

## Direction contract

THESIS: The report card is the planner's grade page: one ruled line per class, the number at
the right as a teacher writes it, one plain sentence on how it is figured. It refuses the
progress ring, the card grid and the gauge.

OWN-WORLD: The Student Planner as documented: planner white with the faint ruling; each class
a ruled line under a hairline, the class's short name a Ballpoint link at 650 at the left, the
official number at 1.75× root in ink with the scale's letter at 400 beside it at the right,
whose number and "as of" in pencil beneath, the one-line how in Ink capped at the measure; the
section head "Classes" with its count; one quiet fold beneath. Recognisable with the words
removed: a short ruled list with a large numeral at each line's right and a pencil line under
each, one folded line at the foot.

STORY: A kid opens the tab and sees every class with its number and letter; the sentence under
a class tells them whether the number adds up from what the school shows, and when it does not,
to ask the teacher. A parent follows a class name to its page and reads the category table and
the check under the grade strip, or taps Print and puts the page on the fridge.

FIRST VIEWPORT: The crumb back to the kid, "Report card" with the kid's nickname and "marking
period so far" in pencil, Print at the right. The child's four tabs with Report card pulled
forward. CLASSES · 2 classes. "Algebra I … 79.50 C / HAC average · as of 9/12 / HAC says 79.50;
there is nothing to rebuild it from." "Honors English 9 … 88.00 B / HAC average · as of 9/11 /
Adds up: 44 of 50 points." Then "▸ How averages are figured". No primary on this page.

FORM: Code-led composition in the settled world; no roll (the maintainer chose the shape in
discussion on 2026-10-03: the per-kid page plus the class page's section, over breakdowns
inline as folds or the section alone). Signature interaction: none beyond the fold; the lines
are read-only, the class name is the way in.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the
verdict, DESIGN.md, and every shipping raster carrying its provenance.
