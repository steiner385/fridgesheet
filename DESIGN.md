---
name: Fridge Sheet
description: A child's schoolwork as a planner spread, checked off one tap at a time, on screen and on the fridge.
colors:
  ballpoint-blue: "#1f5fa8"
  red-pen: "#b3261e"
  checkmark-green: "#2e7d32"
  amber-pencil: "#b8860b"
  amber-pencil-ink: "#9a5b00"
  purple-stamp: "#6b3fa0"
  ink: "#1c1c1c"
  pencil-grey: "#595959"
  stroke-grey: "#8a8a8a"
  ruled-grey: "#c9d3dd"
  day-box-blue-grey: "#8fa3b8"
  paper-white: "#ffffff"
  planner-white: "#fffdf6"
  red-pen-wash: "#fdecea"
  highlighter-yellow: "#fff1a8"
  highlighter-red: "#ffd9d4"
  highlighter-purple: "#ead9ff"
  highlighter-amber: "#ffe4b8"
  ink-early: "#10151b"
  pencil-grey-early: "#4a5568"
  ruled-grey-early: "#b9c6d4"
  day-box-blue-grey-early: "#7f95ad"
  planner-white-early: "#fffaee"
  ballpoint-blue-early: "#0b5cab"
  red-pen-early: "#a3170f"
  checkmark-green-early: "#1d6b27"
  amber-pencil-ink-early: "#8a5200"
  purple-stamp-early: "#5f3594"
  ink-middle: "#161b22"
  pencil-grey-middle: "#5a6474"
  ruled-grey-middle: "#ccd5de"
  day-box-blue-grey-middle: "#8aa0b5"
  planner-white-middle: "#fffcf4"
  ballpoint-blue-middle: "#14539b"
  red-pen-middle: "#a81d14"
  checkmark-green-middle: "#24702c"
  amber-pencil-ink-middle: "#915600"
  purple-stamp-middle: "#653a9a"
typography:
  display:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "28px"
    fontWeight: 600
    lineHeight: 1.2
  headline:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "24px"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.3px"
  title:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "18px"
    fontWeight: 650
    lineHeight: 1.3
  subtitle:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "16px"
    fontWeight: 650
    lineHeight: 1.35
  body:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.4
  day-label:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "13px"
    fontWeight: 650
    lineHeight: 1.45
    letterSpacing: "0.08em"
  caption:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.4
  print-heading:
    fontFamily: "Helvetica-Bold"
    fontSize: "16pt"
    fontWeight: 700
    lineHeight: 1.19
  print-cell:
    fontFamily: "Helvetica"
    fontSize: "10pt"
    fontWeight: 400
    lineHeight: 1.2
  print-small:
    fontFamily: "Helvetica"
    fontSize: "8.5pt"
    fontWeight: 400
    lineHeight: 1.24
rounded:
  planner: "2px"
  stale: "4px"
  control: "6px"
  card: "8px"
  pill: "10px"
  chooser: "12px"
spacing:
  s1: "4px"
  s2: "8px"
  s3: "12px"
  s4: "16px"
  s5: "24px"
  s6: "32px"
  gutter: "24px"
  gutter-narrow: "16px"
components:
  button-secondary:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "6px 12px"
  button-secondary-hover:
    backgroundColor: "{colors.planner-white}"
    textColor: "{colors.ink}"
  button-primary:
    backgroundColor: "{colors.ballpoint-blue}"
    textColor: "{colors.paper-white}"
    typography: "{typography.subtitle}"
    rounded: "{rounded.control}"
    padding: "6px 12px"
  button-default:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.ink}"
    typography: "{typography.subtitle}"
    rounded: "{rounded.control}"
    padding: "5px 11px"
  button-danger:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.red-pen}"
    rounded: "{rounded.control}"
    padding: "6px 12px"
  button-link:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
  input-text:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "4px 6px"
  badge:
    backgroundColor: "{colors.planner-white}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "1px 8px"
  badge-current:
    backgroundColor: "{colors.ballpoint-blue}"
    textColor: "{colors.paper-white}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "1px 8px"
  card:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "12px 16px"
  day-box:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.planner}"
    padding: "0 12px 4px"
  day-box-label:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.pencil-grey}"
    typography: "{typography.day-label}"
    padding: "4px 12px"
  planner-line:
    backgroundColor: "{colors.planner-white}"
    textColor: "{colors.ink}"
    padding: "8px 0 8px 30px"
  highlighter-due:
    backgroundColor: "{colors.highlighter-yellow}"
    textColor: "{colors.ballpoint-blue}"
    rounded: "{rounded.planner}"
    padding: "0 0.35em"
  highlighter-red:
    backgroundColor: "{colors.highlighter-red}"
    textColor: "{colors.red-pen}"
    rounded: "{rounded.planner}"
    padding: "0 0.35em"
  highlighter-check:
    backgroundColor: "{colors.highlighter-purple}"
    textColor: "{colors.purple-stamp}"
    rounded: "{rounded.planner}"
    padding: "0 0.35em"
  highlighter-late:
    backgroundColor: "{colors.highlighter-amber}"
    textColor: "{colors.amber-pencil-ink}"
    rounded: "{rounded.planner}"
    padding: "0 0.35em"
  inset:
    backgroundColor: "{colors.planner-white}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.card}"
    padding: "8px 12px"
  notice:
    backgroundColor: "{colors.planner-white}"
    textColor: "{colors.ink}"
    padding: "12px 16px"
  nav-link:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "6px 8px"
  nav-link-current:
    backgroundColor: "{colors.planner-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "6px 8px"
  chooser-button:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.chooser}"
    padding: "18px"
    size: "22px"
---

# Design System: Fridge Sheet

<!-- Captured by /impeccable document on 2026-09-29 from fridgesheet/web/static/app.css, the
     planner templates (_must_finish, _item, _plan_panel, checkin, _child_nav, _answers, base),
     the four review renders in .impeccable/review/, fridgesheet/sheet.py and
     fridgesheet/web/charts.py. Scan mode: this records The Student Planner as it shipped on a
     child's Plan page, and the incumbent shell as it still stands on the other pages. Where the
     build departs from the direction contract, the build is what is written here. -->

## Overview

**Creative North Star: "The Student Planner"**

Fridge Sheet is the family's copy of the school's list, kept the way a child keeps a planner:
tonight and tomorrow are printed day boxes, every assignment is a line with a square checkbox at
its head, the sheet's word is a highlighter stroke at the line's right, and one tap checks the line
off in place. The record is still the hero and the interface still recedes into paper, but the
paper is now a planner's warm white with a faint ruling behind it, its rules and checkboxes are a
printed blue-grey, and the family's own steps are written in pencil beneath the school's ink. It
refuses the card-stack admin page and, just as firmly, the mascot-and-progress-ring kids' app.

The feel is **calm, plain, trustworthy**. Nothing shouts. Red is rare and always means the school
recorded something as not in. Type is the system font, set at a comfortable size that grows for a
younger reader. The same spread serves a child of eight beside a parent and the parent alone on a
phone at night, so density and vocabulary flex through three reading tiers while the layout, the
rows and the actions never do. The world arrived on the child's Plan page first (2026-09-29,
Impeccable's pick over The Teacher's Gradebook, seed 5d8bc5ca) and the item line carried it to
every page; the shell around the other pages (Today, the Assignments table, Settings, Reports,
the rail) still stands in its incumbent ledger composition on the planner's paper.

Confirmed visual rejections: dashboard chrome, gradients as decoration, cards floating on shadows,
and colour used as the only carrier of meaning.

**Key Characteristics:**
- A planner spread: two printed day boxes side by side (stacked on a phone, Tonight first), each a
  stack of checkbox lines under hairlines, on warm planner white with a faint ruling behind.
- The day box is the only box on the planner; a line has no border, no left rule and no fill.
- Status is a word in a colour, carried as a highlighter stroke in that colour's family, never a
  colour alone and never a filled button.
- One accent (ballpoint blue) for links, the default answer's stroke, the current tab, the focus
  ring and, elsewhere in the app, the page's single filled action.
- Three reading tiers redefine every token together, so the youngest reader gets a larger,
  warmer, higher-contrast page with the same rows.
- Flat at rest, with one motion: 180ms ease-out on the checkbox fill and the strike.

## Colors

A near-monochrome planner with five ink colours that each mean one thing, four highlighter fills
that carry them, and a printed blue-grey for every rule and box.

### Primary
- **Ballpoint Blue** (#1f5fa8): links, the default answer's 2px stroke, the current child tab's
  underline, the focus ring, the current filter chip, and the one filled primary button on the
  pages that have one ("Print now" on Today, "Finish check-in" on Check-in). On the Plan nothing is
  filled blue: the primary lives on the check-in page. As the sheet's DUE word it sits on
  Highlighter Yellow. Early #0b5cab, middle #14539b.

### Secondary
- **Red Pen** (#b3261e): the school says it is not in. The MISSING and ZERO words on Highlighter
  Red, a zero or missing grade cell, the danger button, the stale-data banner, a warn notice, the
  "revisit this date" word on a step. Early #a3170f, middle #a81d14.
- **Checkmark Green** (#2e7d32): done. The filled checkbox with its drawn tick on an answered line,
  a done-line's glyph, a source that answered "OK", the on-time series on Trends. Early #1d6b27,
  middle #24702c.

### Tertiary
- **Amber Pencil** (#b8860b): late, as a stroke: the late series on Trends. As a word it is too
  light (3.3:1), so on screen the LATE word and its checkbox rule use **Amber Pencil Ink**
  (#9a5b00, 5.4:1; `--late`, early #8a5200, middle #915600) on Highlighter Amber.
- **Purple Stamp** (#6b3fa0; `--check`, early #5f3594, middle #653a9a): "check on paper". The
  PAPER — CHECK, IN CLASS — CHECK and HAC — NO GRADE words on Highlighter Purple, the checkbox
  rule under them, the fourth chart series. Work the school cannot see, so neither red nor green.

### Neutral
- **Ink** (#1c1c1c): all body text and headings. Early #10151b, middle #161b22.
- **Pencil Grey** (#595959): the family's own writing and everything secondary: the steps under
  "Our next steps", meta lines, the day-box label, the status bar, stamps, quiet section heads, a
  struck-through name, the "nothing due tonight" line. Early #4a5568, middle #5a6474.
- **Stroke Grey** (#8a8a8a): the 1px stroke on buttons, selects and inputs, so a control reads as
  a control against the planner's lighter rules.
- **Ruled Grey** (#c9d3dd; `--rule`): the planner's blue-grey hairline under every line, the card
  and table borders, the rail's edge and, at 40% over transparent, the faint ruling behind the
  planner page. Early #b9c6d4, middle #ccd5de.
- **Day-box Blue-grey** (#8fa3b8; `--box`): the printed rule. The 1.5px border of a day box and
  its label's underline, the 2px stroke of an untoned checkbox, the ruled header line under the
  child tabs and under "Our next steps". Darker than Ruled Grey so a box reads as printed on the
  page rather than ruled into it. Early #7f95ad, middle #8aa0b5.
- **Paper White** (#ffffff): a day box, a card, a table, an input, the rail, the empty checkbox.
- **Planner White** (#fffdf6; `--wash`): the page itself, warm; the hover on a nav link or
  button, an inset quoting the record, a badge's fill, the sticky save bar. Early #fffaee, middle
  #fffcf4: a touch warmer for the younger tiers.
- **Red Pen Wash** (#fdecea; `--warn-wash`): the fill behind a warn notice or the stale banner,
  always with Red Pen text.
- **Highlighter Yellow** (#fff1a8; `--hl-due`), **Highlighter Red** (#ffd9d4; `--hl-red`),
  **Highlighter Purple** (#ead9ff; `--hl-check`), **Highlighter Amber** (#ffe4b8; `--hl-late`):
  the four strokes behind the sheet's word, one per colour family, the same at every tier. They
  exist only under a word in their ink and are never a fill on their own.

### Named Rules
**The Word Beside the Colour Rule.** Nothing is conveyed by colour alone. What is red is red *and*
says "not done", "0" or "Missing"; what is green is green *and* has a checkmark or the word
"done". This is the accessibility requirement and the age requirement at the same time.

**The One Voice Rule.** Ballpoint Blue fills at most one button per page, the page's main action,
and marks at most one current choice per control group. Everything else it touches is a stroke,
an underline, a rule or a link.

**The Red Pen Rule.** Red is reserved for what the school recorded as not in. A past due date is
not red on its own; the app's own inference ("No" under Handed in, "School evidence changed") is
bold or blue, not red; a budget overrun on a child's page is not red.

**The Sheet's Colour Rule.** The sheet's word on a line wears the colour the sheet prints it in,
from one table (`status_words.STATUS_TONE`, the same table as `sheet.STATUS_COLOR`): DUE words
Ballpoint Blue, LATE Amber Pencil Ink, PAPER — CHECK and HAC — NO GRADE Purple Stamp, MISSING
and ZERO Red Pen. The line's checkbox takes the same colour. A line cannot be red on screen and
blue on the fridge.

**The Highlighter Rule.** The sheet's word is a highlighter stroke: the word in its ink on the
fill of its own family (`--hl-*`), 2px corners, hugging the word (0 .35em) and never a bar across
the page or a filled button. A word with no colour is ink on the bare page.

**The Only-Blue Rule.** On the planner only links and the default answer's stroke are Ballpoint
Blue. The family's steps are written in Pencil Grey; the checkbox of a due line is blue because the
sheet's word is, not because the family wrote it.

**The Whole-Tier Rule.** A reading tier redefines every colour token at once, never some of them,
so no page inherits a colour nobody designed for that tier.

## Typography

**Display Font:** system-ui (with -apple-system, "Segoe UI", sans-serif)
**Body Font:** system-ui (the same stack)
**Print Font:** Helvetica (Helvetica-Bold, Helvetica-Oblique) in the PDF sheet

**Character:** The device's own text face, set plainly, with hierarchy carried by size and a
slightly heavy 650 weight rather than by a second family. The one typographic flourish is the day
box's label: small capitals tracked like a printed agenda. The printed sheet uses Helvetica at
sizes chosen for a child reading standing at a fridge.

### Hierarchy
The frontmatter sizes are the root's. Headline, Title and Subtitle are set as multiples of the
tier root (`--type-root`: 16px at the root, 16 / 18 / 20px on the older / middle / early tiers),
so a heading is never smaller than the body it heads: Headline 1.5×, Title 1.125× (the Open work
per-child head 1.375×, a report title 1.25×), Subtitle 1×.
- **Display** (600, 28px): the Today card's big tally number and the kid chooser's heading. The
  chooser's own buttons are 22px, the one size outside this ramp, on a page that has no tier.
- **Headline** (700, 1.5× root = 24px, -0.3px tracking): the child's name or the page title, in
  the exact words of its rail link. One per page.
- **Title** (650, 1.125× root = 18px): a section's h3 ("Must finish", "Our next steps") and
  `main h3`.
- **Subtitle** (650, 1× root = 16px): h4 inside a section ("Work to do"), a card's h3, the
  assignment name at the head of a line (a step's name is 600), the primary and default buttons'
  labels (600).
- **Body** (400, 15px/1.45 at the root): the default. The reading tiers raise the root to 16px
  (older), 18px (middle) and 20px (early), and every rem-free size below follows. The ruled header
  line and a line's facts, ask line and answers are body size.
- **Label** (400, 13px, `--type-small`): meta lines (class · points · due), the step under a
  line, the foot links, the status bar, badges, chips, the record inset. Tiers raise it to 15px
  (middle) and 16px (early) so the lines a child is asked to judge are never the smallest text.
- **Day label** (650, `--type-small`, .08em tracking, uppercase, Pencil Grey): "DUE TONIGHT",
  "DUE TOMORROW", "ON PAPER, NO GRADE YET" along a day box's top edge. Never smaller than the line
  it heads, because it is set from the same tier token as the meta.
- **Caption** (400, 12px, `--type-tiny`): stamps, legends under tables, provenance. 13px (middle),
  14px (early).
- **Print heading** (Helvetica-Bold 16pt/19), **print cell** (Helvetica 10pt/12, bold for the
  status word), **print small** (8.5pt/10.5) and **print tiny** (8pt/9.5) for the sheet's
  sub-lines. 10pt cells and 8pt sub-lines are the floor: two children still fit one page.

### Named Rules
**The Measure Rule.** Prose, intros and forms are bounded to 760px (`--measure`, about 75
characters at body size); tables, cards and charts fill the 1600px content column, and the planner
spread takes 1100px because two day boxes need more than a measure.

**The Never-Smallest Rule.** On a tiered page the secondary sizes and the headings move with the
body size. A fact a child must judge ("Canvas shows 0 of 10") is never rendered at the page's
smallest size, and the head of a section or a day box is never smaller than the sentence under it.

**The Strike Rule.** An answered line is struck through in place, its name in Pencil Grey, the
checkbox filled green with a drawn tick; the line keeps its place, its meta and its Undo. Nothing
is removed from the child's spread by an answer; the school's record removes it on the next
refresh.

## Layout

One shell, one content column. On a wide screen a 220px rail sits at the left with the wordmark and
navigation; the status bar, an optional stale banner and the page stack in the second column. Under
1024px the rail becomes one horizontal strip that scrolls sideways under a right-edge fade, group
labels dropped; a kid-mode strip is short (Plan, Check-in, Assignments, Trends, Changes, Not
{name}?) so it wraps onto a second row with no fade and every tab in the first viewport. A phone
held sideways puts the strip and the status bar on one row. Under 1280px the status bar drops its
two reassurance items and two-column workspaces such as the check-in stack.

Every page is the same blocks in the same order: status bar, page head (crumb, title in the rail
link's words, actions at the right, one intro sentence bounded to the measure), notices, then the
content column, a ceiling of 1600px with 24px gutters (16px under the strip). The content column is
a stack of sections 32px apart. A section is an h3, a count, one lead sentence and its own controls
at the right; a folded section draws the same head as its summary; a fold with nothing in it is
one quiet line at body size ("Completed steps · nothing here yet"), its marker gone and its pointer
off. Under the strip a page action ("Print plan") and a section's control ("Check Canvas again",
"Add a step") are text links, not boxes between the title and the first line.

**The planner spread** (a child's Plan and Check-in): under the child tabs one ruled header line
(the last check-in, its dates bold, what was agreed in Pencil Grey) with a 1.5px Day-box rule
beneath. Then "Must finish" and its spread: a two-column grid with 16px gaps in which Tonight and
Tomorrow are day boxes side by side, printed whether or not anything is in them, and every other
section (Later, Overdue but still fixable, On paper, Waiting) takes the full width beneath as a
box of its own; under 1024px the grid is one column, Tonight first. A day box is 0 12px 4px inside
with its label bleeding to the edges; the lines in it are 8px 0 8px 30px, the 30px being the
checkbox's column, under 1px hairlines, the last line without one. "Our next steps" follows as
lines under a ruled head, grouped by h4 (Work to do, Blocked, Waiting), a step's name at 600 and
its text in Pencil Grey. Behind all of it `.checkin-main` draws a faint ruling pitched to the line
height (`--line` = 1.45 × root, Ruled Grey at 40%), and the day boxes are Paper White on top of it.

The spacing scale is 4px steps: 4, 8, 12, 16, 24, 32 (`--s1` to `--s6`). Cards sit on a
`repeat(auto-fit, minmax(280px, 1fr))` grid with 16px gaps; form fields on a `minmax(220px, 1fr)`
grid label-over-control. Tables are full width with 6px 8px cells, rising to 10px 8px on a coarse
pointer and 12px 10px on the early tier. Under the strip a work list stops being a table: each row
is one box under a hairline and the header row becomes a row of sort links. A quiet fold carries
24px above its head and 12px below.

## Elevation & Depth

Flat at rest. Depth comes from paper on paper and from rules: a Paper White day box printed with a
1.5px Day-box rule on the Planner White page, the faint ruling behind the page, a hairline under
each line, an inset in the wash inside a box. No shadow exists anywhere in the shipped stylesheet.

The maintainer has opened the door to subtle elevation *(2026-09-29)*: a light ambient shadow may
lift the few things that float over content, namely the sticky Save bar and check-in halves bar,
an opened row-actions menu, and the kid chooser's buttons. Nothing at rest in the content column
lifts. The only motion is the planner's own: 180ms ease-out on the checkbox's fill and border and
on the struck name's colour; nothing else moves.

### Shadow Vocabulary
- **Ambient lift** (`box-shadow: 0 2px 8px rgba(28, 28, 28, 0.08)`, provisional; not yet used in
  code): for a bar or menu that floats over scrolling content. Keep it this quiet or quieter.

### Named Rules
**The Paper Rule.** Surfaces are flat at rest. A shadow is a response to floating over content,
never a way to make a card look important.

**The Only-Box Rule.** On the planner the day box is the only box. A line has no border, no left
rule and no fill of its own; its tone is the colour of its checkbox's rule and of the highlighted
word, nothing else. Cards remain the container on the pages that still carry the incumbent shell.

## Shapes

Printed stationery. The planner's corners are near-square (2px): the day box, the 18px checkbox
with its 2px rule, the highlighter stroke, a chart swatch. Controls keep 6px (buttons, inputs,
selects, nav links, the child tabs' underline has none), 8px on cards, insets and chart holders
(`--radius`), 10px pills on badges, chips and chart-key buttons, 12px on the kid chooser's large
buttons, 4px on the stale banner. Strokes are 1px Stroke Grey on controls, 1px Ruled Grey on
hairlines and cards, 1.5px Day-box Blue-grey on the day box, its label's underline and the two
ruled header lines, 2px on the checkbox and the default answer. The checkbox's tick is drawn, not a
glyph: two sides of a rotated square in Paper White on the green fill. A grey line (nothing to do,
the school has it) draws its checkbox dashed. The wordmark's mark is a 28px square with 6px
corners. The two gradients in the system are functional, not decorative: the 32px fade at the
right edge of the family strip, and the repeating ruling behind the planner page.

## Components

Printed and plain: each control is a 1px stroke on paper, one look at three weights, generous
targets, nothing filled until it matters, and on the planner nothing filled at all.

### Buttons
- **Shape:** gently rounded (6px), 1px Stroke Grey border, inherits body type, 6px 12px padding
  (10px 14px and a 44px minimum height on a coarse pointer).
- **Secondary (default):** Paper White fill, Ink text. Hover: Planner White fill.
- **Primary:** Ballpoint Blue fill and border, white text, 600 weight; hover brightens 10%. One per
  page: the action that spends paper or saves the form. The Plan has none.
- **Default answer:** the first answer on a line, the one to tap if the sentence above it is
  right: a 2px Ballpoint Blue stroke, Ink text, 600 weight, 5px 11px padding so it stays level
  with its neighbours. Never a fill. On a waiting line no answer is the default.
- **Danger:** Paper White fill, Red Pen text and border. The one that deletes.
- **Disabled:** 50% opacity, default cursor.
- **Two-step in the card (Today):** an action that spends paper asks in place, never in a browser
  dialog. "Print now" is a disclosure summary in the primary look; open, it steps back to the
  plain look and the question ("Print today's sheet on Kitchen Inkjet?") sits under it with the
  filled "Print" and a "Cancel" link button. A job's log then lives behind a "Details" fold.
- **Link button:** no border or fill, Pencil Grey underlined text, for "Close" and "undo".
- **Button link (an `<a>` drawn as a button):** the secondary look with 8px 12px padding ("Print
  plan", "Add a step"); under the strip it is a Ballpoint Blue underlined link.
- **Chooser button:** the kid chooser's 22px text, 18px padding, 12px corners, Ruled Grey stroke;
  the grown-up's is 16px on the wash in Pencil Grey.

### Chips
- **Style:** Planner White fill, 1px Ruled Grey border, 10px pill, 1px 8px padding, label type,
  Ink text. Badges ("Must finish"-style flags in a meta line, "printed"), filter chips, the
  segmented Open/Everything choice and chart-key buttons share it.
- **State:** the one in force is filled Ballpoint Blue with white text; a linked badge's border
  turns Ballpoint Blue on hover; a chart series toggled off is Pencil Grey, struck through, its
  swatch at 30%. Outcome badges in the status bar take Checkmark Green or Red Pen text and border.

### Cards / Containers
- **Day box (planner):** Paper White, 1.5px Day-box Blue-grey border, 2px corners, 0 12px 4px
  inside; its h4 label runs along the top edge in Day label type over a 1.5px rule of the same
  colour. Tonight and Tomorrow are always printed; an empty one holds one Pencil Grey line
  ("Nothing due tonight"). A folded section (Later, Waiting) opens onto a day box 8px below its
  summary.
- **Card (incumbent shell: Today, Settings, Reports, the check-in's "Agree and wrap up"):** Paper
  White, 1px Ruled Grey, 8px corners, 12px 16px inside, no shadow.
- **Inset:** anything quoted inside a box: the record, a witness line, the class's pace, the
  "school evidence changed" notice. Planner White, 8px corners, 8px 12px, label type, no left
  rule; the changed notice's lead is Ballpoint Blue 600.
- **Lines list (Today's steps):** Paper White, 1px Ruled Grey, 8px corners, 0 16px, one action per
  row at the right, rows under hairlines.

### Inputs / Fields
- **Style:** Paper White, 1px Stroke Grey, 6px corners, inherits body type, 4px 6px padding
  (10px 14px on touch). Textareas 60px minimum, 88px in the plan form. Labels sit over their
  controls at 550 weight with Pencil Grey 13px help text beneath.
- **Focus:** a 3px Ballpoint Blue outline offset 3px, on every focusable thing including hidden
  radio chips.
- **Checkbox / radio:** 24px square on a coarse pointer (WCAG 2.5.8). The planner line's own
  checkbox is drawn, not an input: the answer buttons are the control.
- **Error / Disabled:** no distinct field error style; errors are said in a warn notice.

### Navigation
- **Rail (family):** Paper White, 1px Ruled Grey right border, 16px padding. The wordmark (mark
  plus "Fridge Sheet", 18px) then links at 6px 8px with 6px corners; uppercase 12px Pencil Grey
  group labels; the current link and hover take the Planner White fill; a question count beside
  a child's name in Ballpoint Blue 600. On a child's page the rail folds everything but Today and
  that child under an "App" disclosure.
- **Kid rail:** that child's five tabs, the question count riding on Plan, and a quiet "Not
  {name}?" foot link in Pencil Grey label type 24px below.
- **Strip (under 1024px):** the same links in one row, 8px 10px padding; the family strip scrolls
  under a right-edge fade, the kid strip wraps.
- **Child tabs:** 10px 14px Ballpoint Blue links under a hairline; the current one carries a 3px
  Ballpoint Blue underline and 650 weight.
- **Ruled header line:** under the tabs, one body-size line in Ink with its dates at 650 and the
  agreement in Pencil Grey, over a 1.5px Day-box rule; "Our next steps" draws the same rule under
  its head.

### Status bar (signature, incumbent shell)
One line of Pencil Grey label type under the rail's top edge: when the data was refreshed, each
source's state in Checkmark Green or Red Pen with the word "OK" or the error, the last run's
outcome as a badge, a running job, an available update, and the clock. Drops its reassurances on
narrow screens and never its warnings. Below it, when the data is older than the runner will
print from, a Red Pen Wash banner with Red Pen text and a "Refresh now" link.

### The planner line (signature)
One assignment, one line, app-wide. An 18px square checkbox at the left (2px Day-box rule, Paper
White, 2px corners) whose rule takes the line's tone: Ballpoint Blue for a question or a due line,
Red Pen for not in, Amber Pencil Ink for late, Purple Stamp for check-on-paper, dashed for a grey
line, and filled Checkmark Green with a drawn tick once answered or done. Head: the name (650,
linked to Assignments), meta in Pencil Grey label type (class · kind · points · due), and the
sheet's word pushed right as a highlighter stroke (700, ink of its family on its fill); on a phone
the word drops to its own line and hugs its width. Facts: one sentence from the verdict. Ask line
(600) and answers: the first answer in the default stroke, the two answers that close a line for
good behind a "More answers" fold inside the line, identically at every tier. The family's layer:
one Pencil Grey label-size line each, no rule. Foot: "▸ Record" and "Plan a step" as blue links
and a Caption-size stamp pushed right ("New since Tue 9/29"). Inside a table's opened row or a
card the same line draws without the checkbox and without its hairline. A step on "Our next
steps" is the same line with its "Must finish · MISSING" word highlighted inside the meta.

### The printed sheet (signature, paper)
Landscape Letter, 0.5in margins, one section per child. Helvetica-Bold 16pt heading, 10pt cells
with the status word bold in its colour, 8.5pt and 8pt sub-lines for the "until" date, the
follow-up marker and notes, an 11pt checkbox per row, a legend at the foot. Overdue first, then
coming due, then two trailer counts. The reader is a child standing at a fridge; the Plan on
screen is this sheet's spread.

## Do's and Don'ts

### Do:
- **Do** put the word beside the colour: every red, green, amber or purple value carries a word or
  glyph that says the same thing, and the sheet's word rides on its own highlighter fill.
- **Do** give every assignment a checkbox line: tone is the checkbox's rule colour and the
  highlighted word, never a border, a left rule or a fill on the line.
- **Do** keep the day box as the planner's only box (1.5px Day-box Blue-grey, 2px corners, label
  along the top edge) and print Tonight and Tomorrow even when empty.
- **Do** write the family's own lines in Pencil Grey and keep Ballpoint Blue for links and the
  default answer's 2px stroke; a page keeps at most one filled primary, and the Plan has none.
- **Do** give every button, control, tab and main link 44px on a coarse pointer; a secondary link
  inside a line or card keeps a 24px floor with padding (the maintainer's rule, 2026-09-29), and a
  checkbox or radio input is 24px.
- **Do** redefine every token when adding to a tier, and set secondary sizes and the day label
  from `--type-small` and `--type-tiny` so they move with the tier.
- **Do** render a fold with nothing in it as one quiet Pencil Grey line at body size, marker gone,
  not a heading over nothing.
- **Do** bound prose and forms to `--measure` (760px), the planner spread to 1100px, and let
  tables, cards and charts fill the column.
- **Do** build a new page from the same blocks: status bar, page head, notices, sections of
  `.sec` with `.sec-head`, and assignments as `_item.html` at card, detail or line density.
- **Do** use the 4px spacing scale (`--s1` to `--s6`) and the 2px / 6px / 8px / 10px radius set.

### Don't:
- **Don't** convey state by colour alone, and don't make a past due date red on its own; red is for
  what the school recorded as not in.
- **Don't** fill the sheet's word as a button or stretch its highlighter into a bar; the stroke
  hugs the word.
- **Don't** add shadows to boxes, lines or anything at rest; a shadow may lift only a sticky bar,
  an open menu or the chooser's buttons, and no heavier than the provisional ambient lift.
- **Don't** animate anything but the checkbox fill and the strike (180ms ease-out).
- **Don't** introduce a second value for a status colour. The printed sheet still uses #1A5FB4
  (blue), #1E7A3E (green), #B26A00 (amber), #6C3FA0 (purple) and #555555 (grey); the targets are
  Ballpoint Blue, Checkmark Green, Amber Pencil, Purple Stamp and Pencil Grey, and the
  unification belongs to the extract step.
- **Don't** use gradients, glows, or decorative imagery; the only gradients are the strip's fade
  and the planner's ruling.
- **Don't** put a card, a left rule or a box inside a day box; the inset is the one thing quoted
  inside a line.
- **Don't** hide a row or an action from a child by tier; fold navigation and secondary fields if
  you must, identically at every tier.
- **Don't** hard-code a colour in a template or in `sheet.py`, `charts.py` or `app.js`; every
  colour in this file is the token to reach for. `app.css` carries none outside its token blocks
  (held by `tests/test_web_colour_and_type.py`); `sheet.py` and `charts.py` are the drift to
  remove.
- **Don't** fill more than one button per page, and don't fill an answer: the first answer on a
  line is the Ballpoint Blue default stroke.
