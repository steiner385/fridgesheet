---
version: 1
slug: "fridgesheet-web-templates-who-html"
primary_target: "fridgesheet/web/templates/who.html"
related_targets: ["fridgesheet/web/routes/who.py"]
---

# Surface brief: the chooser (the planner's cover)

Scope: `/who` (who.html), the page a device sees before it has a reader: a child or a grown-up
taps their name once and the browser remembers (spec 2026-09-27 §13.1; not a login, the
household network is the boundary); Operate mode. Audience: a child on their own device for
the first time, a parent on the kitchen tablet, anyone the "Not Alex?" / "Switch to a kid's
view" links send back here. Job: name the reader in one tap and never see the page again
(maintainer, 2026-10-01: "the planner's cover"; the names "big stroke buttons, as today"; the
grown-up "a quieter button beneath"). Proof: `students.visible` as the kids in order, the
`family` value for a grown-up, the POST that sets the cookie and redirects; the page renders
with an empty database (the grown-up's button alone); the kid buttons carry `data-tier` for
their size. Constraints: no rail and no status bar (the rail would name every child); the
copy stays the phrase table's (`copy.who_looking`, `copy.who_remember`, `copy.a_grownup`);
the buttons stay `<button name="who" value=…>` in the kids' order then `family`; the brand link
back to /who stays. The world is settled (DESIGN.md, The Student Planner); this brief records
composition only. Unresolved: whether a kiosk left open overnight should refresh the date on
its own.

## Direction contract

THESIS: The chooser is the planner's cover opened to today: the mark and the name, today's
date as a day row in pencil over the question, one tall stroke button per kid, the grown-up's
quieter beneath, the remembering sentence as the last pencil line. It refuses the floating
panel of rounded white cards on a bare page.

OWN-WORLD: The Student Planner as documented: planner white with the faint ruling behind the
cover (`.who.planner-main`), a centred column at 520px. The mark and "Fridge Sheet" as the
cover's title (`.brand`, as the rail draws it). Then today's date as a Day row in pencil
("THU 10/1", `h2`-sized? no: the planner's day row type at 650, .04em, uppercase) over "Who's
looking?" at Headline size (28px 600) in Ink. Then the kids: one `button` per kid the column's
width, 22px type, Paper White, the planner's control stroke (1px `--control`) with 2px
corners, 18px padding, 44px and more under a finger. The grown-up's button beneath after a
gap, body size on the wash in pencil, the same stroke. Last, "This browser will remember. You
can change it any time." in pencil label type. No card, no shadow, no box around the choice.
Recognisable with the words removed: a mark, a pencil label, a question, two tall strokes, a
small stroke, a pencil line, centred on ruled paper.

STORY: A child picks up the tablet for the first time, sees today's date and the question,
taps their name once, and lands on their plan; a parent who borrowed it taps "Not Alex?" and
returns here to tap A grown-up.

FIRST VIEWPORT: ⌑ Fridge Sheet; THU 10/1; Who's looking?; [Alex] [Sam]; [A grown-up]; This
browser will remember. You can change it any time. With no kids yet: the grown-up's button
alone under the question. Primary: none; the names are stroke buttons.

FORM: The cover, dated, position 4 of the ordered grounded list, dealt as the lead by the
surface roll and locked by the maintainer over the names on a paper page (2) and the names on
the ruling (3); seed key 1931dce5; code-led, no image generation. Signature interaction: one
tap and the page is gone; nothing else moves.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the
verdict, DESIGN.md, and every shipping raster carrying its provenance.
