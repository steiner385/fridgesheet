---
version: 1
slug: "fridgesheet-web-templates-questions-html"
primary_target: "fridgesheet/web/templates/questions.html"
related_targets: ["fridgesheet/web/routes/questions.py","fridgesheet/web/templates/_question.html","fridgesheet/web/templates/_answered.html"]
---

# Surface brief: Questions (the parent's answering page)

Scope: `/questions` (questions.html with `_question.html`, `_item.html`, `_answered.html`), the
page the rail's question counts lead to and the second stop of the nightly phone check; Operate
mode. Audience: the parents and caregivers; children reach it only by address. Job: answer every
question only a parent can answer, in place, down one list; let a kid's too-late work go in one
step and undo it; see what is waiting on the teacher and what the app could not pair
(maintainer, 2026-09-30: "the parent's answering page"; the let-go bar "a pencil line above the
kid's questions"; a kid with nothing to ask keeps "their name and one pencil line"). Proof: the
verdicts' questions with their facts and answers, the same cards Today and Assignments ask
with; the let-go bar naming every item (#124); the Undo that puts back exactly those items.
Constraints: `?kid=` still narrows to one kid (the rail's link, the let-go redirect); the
`q-<id>` slot and the answer, undo, reopen and question-card routes stay; the let-go confirm
names every item and never says "this page"; a 404 for an unknown kid (#150); one filled primary
per page (none here). The world is settled (DESIGN.md, The Student Planner); this brief records
composition only. Unresolved: whether a household of three interleaves too far (the risk the
maintainer accepted); whether the page should speak in the kid's words or the parent's (built in
the parent's voice, as Today does, because one list cannot change tier line by line).

## Direction contract

THESIS: Questions is one ruled list for the whole house: every question on one page in the
order the school's deadlines close, each line naming its kid, so a parent answers down the page
once instead of kid by kid. It refuses the section per kid with its own heading and the card
stack.

OWN-WORLD: The Student Planner as documented: planner white with the faint ruling; the
questions as planner lines under hairlines (checkbox in the ask blue, name at 650, the kid's
name first in the pencil meta, the facts, the ask line and the answers with the default's 2px
ballpoint stroke); who has nothing to ask as one pencil line under the title; beneath the list,
per kid, the let-go sentence as a pencil line with its default button at the end (Undo takes
its place after), and Waiting on the teacher and Can't pair these as quiet folds naming the
kid. No box around the list. Recognisable with the words removed: a ruled page of checkbox
lines with answer buttons, a pencil line or two beneath, folded lines at the foot.

STORY: A parent opens Questions on a phone at night, reads the first line, taps an answer, the
line strikes itself, and the next line is already under their thumb; at the foot they let a
child's too-late work go in one step, or see what is still waiting on the teacher.

FIRST VIEWPORT: The title and its intro. "Nothing to ask about Sam's work." in pencil. Then
"To answer · 1" as the section head and the list: ☐ Participation · Alex · Honors English 9 ·
10 pts · due Wed 9/23; the facts; Was it handed in? with Yes, handed in (the default stroke), Do
it today, Do it tomorrow, Ask the teacher; the foot links. Beneath the list, Alex's let-go line
when two or more of Alex's assignments are too late for credit, then "Waiting on the teacher ·
Alex" and "Can't pair these · Alex" as folds. No primary on this page.

FORM: The household's list, position 3 of the ordered grounded list, dealt as the lead by the
surface roll and locked by the maintainer over Tonight-then-when-you-can (5) and one paper page
with the kids as day rows (7); seed key a3a53837; code-led, no image generation. Signature
interaction: the same in-place strike on an answered line as on the Plan, Undo in its place;
the folds open in place; nothing else moves.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the
verdict, DESIGN.md, and every shipping raster carrying its provenance.
