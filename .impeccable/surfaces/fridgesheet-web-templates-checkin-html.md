---
version: 1
slug: "fridgesheet-web-templates-checkin-html"
primary_target: "fridgesheet/web/templates/checkin.html"
related_targets: ["fridgesheet/web/templates/_must_finish.html","fridgesheet/web/templates/_plan_panel.html"]
---

# Surface brief: a child's Plan page

Scope: `/kids/{key}/plan` (checkin.html with `_must_finish.html` and `_plan_panel.html`), the
nightly page a child and a parent read together; Operate mode. Audience: the child at their tier
beside a parent, and the parent alone on a phone at night. Job: see what must be finished tonight
and tomorrow, answer each line with one tap, and see the family's steps beneath. Proof: the
school's list as of the last refresh, the sheet's word on every line in the sheet's colour.
Constraints: parity of rows and actions at every tier; the vocabulary table; one filled primary
per page; 44px for buttons and main links, 24px for secondary links; the printed sheet is the
product and this page is its screen. Unresolved: whether Today adopts the same world next (yes,
planned), and whether the three child tabs collapse (decide after this surface ships).

## Direction contract

THESIS: The child's Plan is her own planner spread: tonight and tomorrow are printed day boxes
with a checkbox on every line, checked off by one tap. It refuses the card-stack admin page this
category ships, and its predictable opposite, the mascot-and-progress-ring kids' app.

OWN-WORLD: Warm planner white with a faint ruled grid; printed day-box rules in a planner
blue-grey; a square checkbox at the head of every line; the sheet's word carried as a highlighter
stroke behind the word in the sheet's colour family (due, not-in, check, late), never a filled
button; ballpoint blue for links and the default answer's stroke; the family's steps in pencil
grey beneath the line; the system sans kept at the tier's size (Operate), with the day-box label
in small caps tracking like a printed agenda. Recognisable with the words removed: two ruled
boxes side by side with checkbox lines and a highlighter stripe.

STORY: The child sees Tonight first, taps "I'll do it today" or "I handed it in", and watches the
line change in place: the checkbox fills and the line is struck. The parent reads the same spread
with the school's record folded under each line and the family's steps beneath the boxes.

FIRST VIEWPORT: The child's name and the school-list date as one ruled header line. Below it,
Tonight and Tomorrow as two printed day boxes side by side (stacked on a phone, Tonight first),
each holding its lines: checkbox, assignment name, class in pencil grey, the sheet's word
highlighted at the line's right, the prompt and the answer row beneath. Later as a narrower third
box under them, then "Overdue, still fixable" and "On paper" as boxes of their own. "Our next
steps" follows as ballpoint lines under a ruled head. No card borders, no left rules; the day box
is the only box. Nothing on the Plan is filled blue; the primary lives on the check-in page.

FORM: The Student Planner, position 1 of the ordered grounded list (Impeccable's pick, chosen by
the maintainer over the assigned index 3, The Teacher's Gradebook); seed key 5d8bc5ca; code-led,
no image generation. Signature interaction: the one-tap answer strikes the line in place. Motion
grammar: one 180ms ease-out on the checkbox fill and the strike; nothing else moves.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the
verdict, DESIGN.md, and every shipping raster carrying its provenance.
