---
version: 1
slug: "fridgesheet-web-templates-course-html"
primary_target: "fridgesheet/web/templates/course.html"
related_targets: ["fridgesheet/web/routes/kid.py","fridgesheet/web/templates/_weeks.html"]
---

# Surface brief: a class's page (the class's record)

Scope: `/kids/{key}/courses/{id}` (course.html, with `_weeks.html`, `_week_line.html`,
`_notes.html`, `_chart_canvas.html`), reached from the class link in any line's meta; Operate
mode. Audience: a parent checking one class, occasionally the child. Job: read the class's
grade with the official source first, see how it has moved, find the teacher, keep the
family's notes on the class, and read every assignment from both gradebooks as the planner's
weekly pages (maintainer, 2026-09-30: "the class's record", "weekly pages", the sources
control "a fold on the page"). Proof: the grade observations as recorded, refresh by refresh;
the teacher as the school lists them; the class's rows from Canvas and its HAC twin as one
list. Constraints: the Sources form and its route stay (`tests/test_web_course_sources.py`);
the words "Sources for this class" stay; the chart shows all history (no Weeks selector); a
paired class's rows appear once (#183); the record opens in place of a line; 44px tabs and
main links, 24px secondary. The world is settled (DESIGN.md, The Student Planner); this brief
records composition only. Unresolved: whether Settings, Reports and the other parent tools
follow; whether a class with dozens of observations needs the strip folded.

## Direction contract

THESIS: A class's page is its record opened at the grade: the grade's history as a strip of
small boxes across the top, the newest on the highlighter, and the class's assignments as the
weekly pages beneath. It refuses the row of three equal cards and the sortable table.

OWN-WORLD: The Student Planner as documented: planner white with the faint ruling; the grade
strip is Today's week strip turned to the grade, each cell a small day box in the blue-grey
rule with a day label along its top edge (the refresh date; OFFICIAL · HAC AVERAGE for the
official number from the twin), the value at Display size in ink and the letter beside it,
the newest cell's date on the yellow stroke; the teacher, the email and the sources fold as
one pencil line beneath; "How it moved" (the chart) and Notes as quiet folds; the weekly pages
as on Assignments. Recognisable with the words removed: a row of small boxes, one highlighted,
a pencil line, two folded lines, then ruled week boxes of checkbox lines.

STORY: A parent follows a class's name from a line and sees the grade at once, with how it got
there; they find the teacher's email on the next line, open how it moved if they want the
chart, and read down the weeks to the assignment they came for; a line the app asks about
answers in place.

FIRST VIEWPORT: The crumb back to the child, the class's short name with the long name in
pencil. The grade strip: OFFICIAL · HAC AVERAGE 88.0 updated 9/26, MON 9/28 93.0 A-, WED 9/30
· CANVAS CURRENT 91.2 A- on the yellow stroke. Beneath it one pencil line: Michael Hoch ·
hoch@example.org · Also in HAC as Honors English 9 S1, and the fold "Sources for this class:
Canvas for scores, HAC for the average · change" opening the two selects and Save. Then the
folds "How it moved" and "Notes", then "Assignments" with its count, the sort line and the
weekly pages, this week first. No primary on this page (Save lives inside the fold).

FORM: The grade strip, position 4 of the ordered grounded list, dealt as the lead by the
surface roll and locked by the maintainer over the pages under a header (7) and the grade box
beside the teacher box (2); seed key 2254cef2; code-led, no image generation. Signature
interaction: the same in-place strike on an answered line as on Assignments; the sources fold
and the two quiet folds open in place; nothing else moves.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the
verdict, DESIGN.md, and every shipping raster carrying its provenance.
