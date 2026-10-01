---
version: 1
slug: "fridgesheet-web-templates-changes-html"
primary_target: "fridgesheet/web/templates/changes.html"
related_targets: ["fridgesheet/web/templates/_change_rows.html","fridgesheet/web/routes/changes.py"]
---

# Surface brief: Changes (the planner's log)

Scope: `/changes` (changes.html with `_change_rows.html`), the TIME page that says what the
gradebooks and the family did since a chosen moment, newest first; Operate mode. Audience: a
parent catching up after a day or a week away; a child on their own device sees only their
own. Job: scan what happened in a minute, open a line's record in place, narrow by window, kid
or kind (maintainer, 2026-10-01: "the planner's log"; the filters "words in the sort line's
grammar"; the rows "dated lines, grouped by day"). Proof: `changes.since` over the chosen
window, one event per line as the store records it, paged 500 at a time; the kid and the
class under every item; the item's record opened in place. Constraints: the `?window=`,
`?kid=`, `?kind=` and `?page=` parameters and the pager stay; an unknown window or kind falls
back and the fallback word is marked current; the chips were plain links and the words stay
plain links (the residuals test); a kid key is URL-encoded in every link; kid mode draws no Kid
words. The world is settled (DESIGN.md, The Student Planner); this brief records composition
only. Unresolved: whether Runs follows as the same log; whether the family's answers should
fold.

## Direction contract

THESIS: Changes is the planner's log: the window's days newest first, each a day row carrying
its own tally over the day's lines, each line one thing that moved, in the order it moved. It
refuses the four-column table with a chip per row and the endless unbroken feed.

OWN-WORLD: The Student Planner as documented: planner white with the faint ruling; the Window,
Kid and Kind choices as pencil run-in lines in the sort line's grammar, the chosen word in ink
at 650, parted by em dashes; each day a Day row in pencil (WED 9/30) with its tally after it at
400 in sentence case ("· 12 changes · 2 grades posted · 1 now missing"); under it the lines, one
per event under a hairline: the time in pencil label type, the kind as a plain word at 650, the
item's name as a link that opens its record in place of the line, the kid and the class in the
pencil meta, the detail in body type; the pager as one pencil line at the foot. No box, no
chip, no table. Recognisable with the words removed: pencil lines of words, then day labels
over ruled lines down the page.

STORY: A parent back from two days away opens Changes, widens the window to three days with a
tap on a word, reads the first day's tally, runs down its lines, opens the one that matters
and sees the record there, and narrows to one kid when the list is long.

FIRST VIEWPORT: The title and its intro. The words: Since yesterday · Last 3 days · Last week ·
Last month — Kid all · Alex · Sam — Kind all · New · Grade posted · Grade changed · Now missing ·
Cleared · You answered · You cleared a flag · Class average, the chosen ones in ink. Then WED
9/30 · 12 changes · 2 grades posted · 1 now missing; its lines: 8:11 PM · You cleared a flag ·
Participation · Alex · Honors English 9 · was asked the teacher; 1:50 PM · Class average ·
Honors English 9 · Alex · Canvas current 93 → 91.2; 1:50 PM · Now missing · Quiz 1 · …; then
TUE 9/29 and its lines. "Nothing has changed in this window." as one pencil line when the window
is empty. No primary on this page.

FORM: Each day with its tally, position 6 of the ordered grounded list, dealt as the lead by
the surface roll and locked by the maintainer over latest-first-with-the-earlier-folded (5) and
the window as one paper page (7); seed key 52af38ac; code-led, no image generation. Signature
interaction: a word turns the page to another window, kid or kind; a name opens its record in
place; nothing else moves.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the
verdict, DESIGN.md, and every shipping raster carrying its provenance.
