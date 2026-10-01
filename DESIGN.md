---
name: Fridge Sheet
description: A child's schoolwork as a planner spread, checked off one tap at a time, on screen and on the fridge.
colors:
  ballpoint-blue: "#1f5fa8"
  red-pen: "#b3261e"
  checkmark-green: "#2e7d32"
  amber-pencil: "#b8860b"
  amber-pencil-ink: "#8a5200"
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
  day-row:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "13px"
    fontWeight: 650
    lineHeight: 1.45
    letterSpacing: "0.04em"
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
  rail-tab:
    backgroundColor: "{colors.planner-white}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.planner}"
    padding: "6px 12px"
  rail-tab-current:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.planner}"
    padding: "6px 12px"
  rail-fold:
    backgroundColor: "{colors.planner-white}"
    textColor: "{colors.pencil-grey}"
    typography: "{typography.body}"
    rounded: "{rounded.planner}"
    padding: "6px 12px"
  rail-group:
    backgroundColor: "{colors.planner-white}"
    textColor: "{colors.pencil-grey}"
    typography: "{typography.day-label}"
    padding: "16px 0 4px"
  child-tab:
    backgroundColor: "{colors.planner-white}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.planner}"
    padding: "10px 14px"
  child-tab-current:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.ink}"
    typography: "{typography.subtitle}"
    rounded: "{rounded.planner}"
    padding: "10px 14px"
  status-line:
    backgroundColor: "{colors.planner-white}"
    textColor: "{colors.pencil-grey}"
    typography: "{typography.label}"
    padding: "12px 24px 8px"
  chooser-button:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.chooser}"
    padding: "18px"
    size: "22px"
  sheet-strip:
    backgroundColor: "{colors.planner-white}"
    textColor: "{colors.ink}"
    padding: "8px 0"
  day-cell:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.pencil-grey}"
    typography: "{typography.label}"
    rounded: "{rounded.planner}"
    padding: "0 12px 8px"
  day-word-today:
    backgroundColor: "{colors.highlighter-yellow}"
    textColor: "{colors.ink}"
    typography: "{typography.day-label}"
    rounded: "{rounded.planner}"
    padding: "0 0.35em"
  week-box:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.planner}"
    padding: "0 12px 4px"
  week-word-current:
    backgroundColor: "{colors.highlighter-yellow}"
    textColor: "{colors.ink}"
    typography: "{typography.day-label}"
    rounded: "{rounded.planner}"
    padding: "0 0.35em"
  day-row:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.pencil-grey}"
    typography: "{typography.day-row}"
    padding: "12px 0 0"
  sort-line:
    backgroundColor: "{colors.planner-white}"
    textColor: "{colors.pencil-grey}"
    typography: "{typography.label}"
    padding: "8px 0 12px"
  view-word:
    backgroundColor: "{colors.planner-white}"
    textColor: "{colors.ballpoint-blue}"
    typography: "{typography.label}"
    padding: "0"
  view-word-current:
    backgroundColor: "{colors.planner-white}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    padding: "0"
  sheet-page:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.planner}"
    padding: "0 12px 4px"
  kid-tab-tally:
    backgroundColor: "{colors.planner-white}"
    textColor: "{colors.pencil-grey}"
    typography: "{typography.label}"
    padding: "0"
  sheet-legend:
    backgroundColor: "{colors.planner-white}"
    textColor: "{colors.pencil-grey}"
    typography: "{typography.label}"
    padding: "12px 0 0"
  grade-cell:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.ink}"
    typography: "{typography.display}"
    rounded: "{rounded.planner}"
    padding: "0 12px 8px"
  sources-fold:
    backgroundColor: "{colors.planner-white}"
    textColor: "{colors.pencil-grey}"
    typography: "{typography.label}"
    padding: "0"
---

# Design System: Fridge Sheet

<!-- Captured by /impeccable document on 2026-09-29 (Assignments added 2026-09-30; the extract
     step recorded 2026-09-30; the polish after the re-critique of 2026-09-30 recorded the same
     day from the build, snapshots in .impeccable/critique/2026-09-30T03-23-44Z__*; the shell
     recorded 2026-09-30 from base.html, _header.html, _child_nav.html, app.css and app.js after
     the finish review's three fixes, renders in .impeccable/review/shell-*.png; Open work recorded 2026-09-30 from open.html,
     _item.html, routes/open.py and app.css after the finish review's three fixes, renders in
     .impeccable/review/open-*.png; a class's page recorded 2026-09-30 from course.html,
     _week_line.html, routes/kid.py and app.css after the finish review's four fixes, renders in
     .impeccable/review/class-*.png; Questions recorded 2026-09-30 from questions.html, _item.html,
     _answered.html, routes/questions.py and app.css, renders in .impeccable/review/questions-*.png; Settings recorded 2026-10-01 from settings.html, the two
     editors, _update_button.html and app.css, renders in .impeccable/review/settings-*.png; Trends recorded 2026-10-01 from trends.html and app.css,
     renders in .impeccable/review/trends-*.png; Changes recorded 2026-10-01 from changes.html,
     _change_rows.html, routes/changes.py, app.js and app.css, renders in .impeccable/review/changes-*.png) from fridgesheet/tokens.py (the one token source: COLORS, ROOT,
     TIERS, PRINT, CHART), fridgesheet/web/static/app.css whose :root and [data-tier] lines are
     generated from it, the planner templates (_must_finish, _item, _plan_panel,
     checkin, dashboard, _child_nav, _answers, base, kid, _weeks, _week_line, _verdict_sections),
     the review renders in .impeccable/review/ (the Plan, today-desktop / today-mobile, and
     assignments-desktop / -mobile / -kid-early-mobile / -folded-desktop), fridgesheet/sheet.py
     and fridgesheet/web/charts.py. Scan mode: this records The Student Planner as it shipped on a
     child's Plan page (seed 5d8bc5ca), on Today (seed 484d9aac, "the week strip") and on a
     child's Assignments page (seed d4a7b45f, "the weekly pages"), and the shell as the planner's
     index tabs (surface brief .impeccable/surfaces/fridgesheet-web-templates-base-html.md), and Open work
     as the sheet on a screen (2026-09-30, seed 169d6a89, "one page at a time"; surface brief
     .impeccable/surfaces/fridgesheet-web-templates-open-html.md), and a class's page as the
     class's record (2026-09-30, seed 2254cef2, "the grade strip"; surface brief
     .impeccable/surfaces/fridgesheet-web-templates-course-html.md), and Questions as the
     parent's answering page (2026-09-30, seed a3a53837, "the household's list"; surface brief
     .impeccable/surfaces/fridgesheet-web-templates-questions-html.md), and Settings as the
     household's setup page (2026-10-01, seed 40e594fb, "ruled sections, one Save each"; surface
     brief .impeccable/surfaces/fridgesheet-web-templates-settings-html.md), and Trends as the year
     so far (2026-10-01, seed c137f15a re-roll 1, "the report card page"; surface brief
     .impeccable/surfaces/fridgesheet-web-templates-trends-html.md), and Changes as the planner's
     log (2026-10-01, seed 52af38ac, "each day with its tally"; surface brief
     .impeccable/surfaces/fridgesheet-web-templates-changes-html.md). Where the build departs from the direction contract, the
     build is what is written here. The frontmatter colours are held equal to tokens.COLORS and
     tokens.TIERS by tests/test_tokens.py. -->

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
Impeccable's pick over The Teacher's Gradebook, seed 5d8bc5ca), Today followed the same day as
the family's planner week (seed 484d9aac), a child's Assignments page followed as the planner
turned back a week at a time (2026-09-30, seed d4a7b45f), the item line carried it to every
page, and the shell followed the same day as the planner's edge (the maintainer's pick of three
shell forms, "the planner's index tabs"): the pages are index tabs down the rail, the current one
pulled forward onto the page, the status is the page's ruled "as of" line in pencil, and a child's
three pages are the same tabs turned sideways. Open work followed the same day as the sheet on a
screen (the maintainer's pick of three surface forms, "one page at a time"): the kids as tabs on
the ruled line, the chosen kid's sheet beneath as one paper page in the sheet's order, its lines
read-only. A class's page followed as the class's record (the maintainer's pick of three surface
forms, "the grade strip"): the grade's history as a strip of small boxes across the top, the
newest on the highlighter, over the class's assignments as the weekly pages; the last work table
went with it. Questions followed as the parent's answering page ("the household's list"): one
ruled list for the whole house in the order the school's deadlines close, the kid named first on
each line, answered in place in the parent's voice. Settings followed as the household's setup
page ("ruled sections, one Save each"): the planner's blocks in order, each topic a ruled
section with its fields on the ruling, three forms parted by the printed rule, each closing on a
Save that names its file. Trends followed as the year so far ("the report card page"): one paper
page labelled THE YEAR SO FAR, the hand-in record its first line, the charts its figures with the
numbers folded, the longest open in pencil at its foot. Changes followed as the planner's log ("each day with its
tally"): the window's days newest first, each a day row carrying its tally over ruled lines, one
per thing that moved, the choices as words. Reports, Runs, Schedules and Diagnostics now sit
inside the planner's shell but keep their own incumbent content (cards, chips, tables) until
each is brought into the world on its own.

Confirmed visual rejections: dashboard chrome, gradients as decoration, cards floating on shadows,
and colour used as the only carrier of meaning.

**Key Characteristics:**
- A planner spread: two printed day boxes side by side (stacked on a phone, Tonight first), each a
  stack of checkbox lines under hairlines, on warm planner white with a faint ruling behind.
- The day box is the only box on the planner; a line has no border, no left rule and no fill.
- Status is a word in a colour, carried as a highlighter stroke in that colour's family, never a
  colour alone and never a filled button.
- One accent (ballpoint blue) for links, the default answer's stroke, the question count beside
  a tab, the focus ring and, elsewhere in the app, the page's single filled action.
- The shell is the planner's edge: the pages are index tabs down a planner-white rail with the
  day-box rule as its edge, no fill and no pill at rest, the current one paper white with the box
  rule on three sides and open toward the page; on a phone one ruled row with a Menu fold whose
  tabs wrap beneath it.
- Three reading tiers redefine every token together, so the youngest reader gets a larger,
  warmer, higher-contrast page with the same rows.
- Flat at rest, with one motion: 180ms ease-out on the checkbox fill and the strike.
- On Today the week is a strip of five small day cells with tonight's day word on the yellow
  highlighter (its overdue rows named, "Sam 2 late"), and each child gets a day box of tonight's
  lines labelled with their name, spoken in the parent's voice; on a phone the week comes first
  and the sheet's controls fold to one line.
- On Assignments every week the work was due is a printed week box, newest first, this week's
  word on the yellow highlighter; a week with nothing shown folds to its label and tally, and
  the day rows inside a week are small labels in the same pencil.
- On Open work the kids are tabs on the ruled line and the chosen kid's sheet is one paper page:
  the sheet's heading along the top edge, STILL FIXABLE then COMING DUE as day rows parted by the
  printed rule, every line read-only with the sheet's word and "Until Wed 10/7" in pencil, the
  trailer at the foot and the sheet's legend once beneath.
- On a class's page the grade's history is a strip of small boxes, one per refresh that moved
  it, the official number first and the newest date on the highlighter; the teacher and the
  sources fold are pencil lines beneath, "How it moved" and Notes quiet folds, and the class's
  assignments the same weekly pages as Assignments, the class name a plain word in each meta.
- On Questions every question in the house is one ruled list, in the order the deadlines close,
  the kid's name first in each line's pencil meta; who has nothing to ask is one pencil line under
  the title; beneath the list, per kid, the let-go sentence as a pencil line with its button and
  the waiting lines and unpaired twins as quiet folds. No box around any of it.
- On Settings every topic is a ruled section with its fields label over control and its help in
  pencil; the three forms are parted by the printed rule and each ends in a Save that names the
  file it writes, each Save filled as its form's one primary; a fieldset is a
  hairline with a day-row label, an editor's row a ruled line with its buttons at the right, a
  notice a line under a hairline. No card on the page.
- On Trends the year is one paper page, THE YEAR SO FAR · last 8 weeks along its top edge: the
  Kid and Weeks choices as one pencil line in the sort line's grammar above it; inside, ON-TIME
  HAND-INS, GRADES, WORK DUE EACH WEEK and OPEN THE LONGEST as day rows over the record line,
  the charts drawn flat on the page, "The numbers" as a pencil fold and the longest open as
  pencil lines under hairlines.
- On Changes the log is the window's days, newest first, each a day row with its tally ("WED
  9/30 · 12 changes · 1 grade posted · 1 now missing") over ruled lines, one per thing that
  moved: the time in pencil, the kind as a word at 650, the item's name a link that opens its
  record in a slot under the line, the kid and class in the pencil meta, the detail in ink; the
  Window, Kid and Kind choices are words in the sort line's grammar. No table, no chip.

## Colors

A near-monochrome planner with five ink colours that each mean one thing, four highlighter fills
that carry them, and a printed blue-grey for every rule and box.

**Tokens.** Every value below lives once, in `fridgesheet/tokens.py`: `COLORS` is this palette by
its pen-and-stamp name; `ROOT` maps the page's roles onto it as the CSS custom properties
(`--ink`, `--muted`, `--control`, `--rule`, `--box`, `--paper`, `--wash`, `--accent`, `--warn`,
`--ok`, `--late`, `--check`, `--warn-wash`, `--hl-due`/`-red`/`-check`/`-late`, the three
`--type-*` sizes, `--page-max`, `--measure`, `--rail`, `--pad`, `--radius`, `--s1` to `--s6`);
`TIERS` and `TIER_TOKENS` are what a reading tier moves; `PRINT` is the sheet's type ramp in
points and its colours by the same roles; `CHART` is the Trends strokes. The `:root` line and the
three `[data-tier]` lines of `app.css` are generated from it by `scripts/tokens_css.py`
(`--check` to verify); `sheet.py` and `charts.py` import it. To change a value, edit
`tokens.py`, run `python scripts/tokens_css.py`, and update the frontmatter here;
`tests/test_tokens.py` fails until the four agree. The printed sheet's colours are the page's:
a word is the same red, amber, blue or purple on the fridge as on the screen.

### Primary
- **Ballpoint Blue** (#1f5fa8): links (the status line's Update and running-job words among
  them), the default answer's 2px stroke, the question count beside a tab (never a tab's open count: on Open work
  that is a Pencil Grey tally), the focus ring, the
  current filter chip, and the one filled primary button on the
  pages that have one ("Print now" on Today, "Finish check-in" on Check-in). On the Plan and on
  Assignments nothing is filled blue: the primary lives on the check-in page, and the Open /
  Everything choice on Assignments is words, the unchosen one a Ballpoint Blue link. As the sheet's DUE word it sits on
  Highlighter Yellow. Early #0b5cab, middle #14539b.

### Secondary
- **Red Pen** (#b3261e): the school says it is not in. The MISSING and ZERO words on Highlighter
  Red, a zero or missing grade cell, the danger button, the stale-data banner, a warn notice, the
  "revisit this date" word on a step. Early #a3170f, middle #a81d14.
- **Checkmark Green** (#2e7d32): done. The filled checkbox with its drawn tick on an answered line,
  a done-line's glyph, a source that answered "OK", the on-time series on Trends. Early #1d6b27,
  middle #24702c.

### Tertiary
- **Amber Pencil** (#b8860b): late, as a stroke: the late series and the "late" outcome on
  Trends. As a word it is too light (3.3:1), so the LATE word and its checkbox rule on screen,
  and the LATE word on the printed sheet, use **Amber Pencil Ink** (#8a5200: 5.2:1 on
  Highlighter Amber, the pair the word is read in, and 6.4:1 on white; `--late`, the same at
  the early tier, middle #915600). The re-critique of 2026-09-30 found the earlier #9a5b00 at
  4.40:1 on the highlighter, under AA for a 16px bold word.
- **Purple Stamp** (#6b3fa0; `--check`, early #5f3594, middle #653a9a): "check on paper". The
  PAPER — CHECK, IN CLASS — CHECK and HAC — NO GRADE words on Highlighter Purple, the checkbox
  rule under them, the fourth chart series. Work the school cannot see, so neither red nor green.
- **Teal Pencil** (#00707f) and **Brown Pencil** (#8a6d3b): chart-only strokes, in
  `tokens.COLORS` but not in this frontmatter because no page role wears them. Teal Pencil is the
  sixth series stroke on Trends; Brown Pencil is the "unknown" outcome. Neither may colour a word,
  a rule or a fill anywhere else.

### Neutral
- **Ink** (#1c1c1c): all body text and headings. Early #10151b, middle #161b22.
- **Pencil Grey** (#595959): the family's own writing and everything secondary: the steps under
  "Our next steps", meta lines, the day-box label, the status line, the rail's group names and
  its App / More fold tabs and the Menu tab's marker, stamps, quiet section heads, a
  struck-through name, the "nothing due tonight" line (and the day pair's "Nothing due tonight
  or tomorrow" on a phone), the week strip's per-child counts and the
  family line in a kid's day box on Today; on Assignments the sort line and its drawn chevron,
  a week's label and its tally, the day rows and "Nothing due this week"; on Open work the tabs'
  tallies ("Alex · 6"), the page's as-of line, STILL FIXABLE and COMING DUE, the "Until Wed 10/7"
  sub-line, the trailer and the legend's text; on a class's page the strip cells' "whose" lines
  ("HAC average · as of 9/26", "Canvas current"), the other gradebook's number, the teacher line
  and the sources sentence; on Questions the quiet-kid line, the let-go sentence, the kid's name
  in a line's meta (at 650) and the waiting lines. Early #4a5568, middle
  #5a6474.
- **Stroke Grey** (#8a8a8a): the 1px stroke on buttons, selects and inputs, so a control reads as
  a control against the planner's lighter rules.
- **Ruled Grey** (#c9d3dd; `--rule`): the planner's blue-grey hairline under every line, the card
  and table borders, the status line's hairline, the hairline the state line under the child
  tabs closes on and, at 40% over transparent, the faint ruling behind the planner page. Early #b9c6d4, middle #ccd5de.
- **Day-box Blue-grey** (#8fa3b8; `--box`): the printed rule. The 1.5px border of a day box and
  its label's underline, the 2px stroke of an untoned checkbox, the rail's edge (its right edge
  beside a page, its bottom edge on a phone), the three sides of the current index tab and of
  the current child tab, the rule the child tabs stand on, the ruled header line in kid mode
  (where there are no tabs) and under "Our next steps", and on Open work the kids' tabs' rule, the page box,
  its label's underline and the printed rule above COMING DUE. Darker than Ruled Grey so a box reads as printed on the
  page rather than ruled into it. Early #7f95ad, middle #8aa0b5.
- **Paper White** (#ffffff): a day box, a card, a table, an input, the current index tab pulled
  forward from the rail and the current child tab, the empty checkbox.
- **Planner White** (#fffdf6; `--wash`): the page itself and the rail, warm; the hover on a
  button (a tab underlines instead), an inset quoting the record, a badge's fill, the sticky save bar. Early #fffaee, middle
  #fffcf4: a touch warmer for the younger tiers.
- **Red Pen Wash** (#fdecea; `--warn-wash`): the fill behind a warn notice or the stale banner,
  always with Red Pen text.
- **Highlighter Yellow** (#fff1a8; `--hl-due`), **Highlighter Red** (#ffd9d4; `--hl-red`),
  **Highlighter Purple** (#ead9ff; `--hl-check`), **Highlighter Amber** (#ffe4b8; `--hl-late`):
  the four strokes behind the sheet's word, one per colour family, the same at every tier. They
  exist only under a word and are never a fill on their own. The words not in their family's
  ink are the week strip's TONIGHT and the Assignments page's THIS WEEK, Ink on Highlighter
  Yellow: a day or a week is not a status, so it takes the stroke and not the blue.

### Named Rules
**The Word Beside the Colour Rule.** Nothing is conveyed by colour alone. What is red is red *and*
says "not done", "0" or "Missing"; what is green is green *and* has a checkmark or the word
"done". This is the accessibility requirement and the age requirement at the same time.

**The One Voice Rule.** Ballpoint Blue fills at most one button per form, the form's main action
(a page is one form, unless the printed rule parts several, as Settings' three Saves are), and
marks at most one current choice per control group. Everything else it touches is a stroke,
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
the page or a filled button. A word with no colour is ink on the bare page. The week strip's
day word and a week box's label borrow the yellow stroke for tonight and this week only, in Ink.

**The Only-Blue Rule.** On the planner only links and the default answer's stroke are Ballpoint
Blue. The family's steps are written in Pencil Grey; the checkbox of a due line is blue because the
sheet's word is, not because the family wrote it.

**The Whole-Tier Rule.** A reading tier redefines every colour token at once, never some of them,
so no page inherits a colour nobody designed for that tier.

## Typography

**Display Font:** system-ui (with -apple-system, "Segoe UI", sans-serif)
**Body Font:** system-ui (the same stack)
**Print Font:** Helvetica (Helvetica-Bold, Helvetica-Oblique) in the PDF sheet, at the sizes
in `tokens.PRINT`

**Character:** The device's own text face, set plainly, with hierarchy carried by size and a
slightly heavy 650 weight rather than by a second family. The one typographic flourish is the day
box's label: small capitals tracked like a printed agenda. The printed sheet uses Helvetica at
sizes chosen for a child reading standing at a fridge.

### Hierarchy
The frontmatter sizes are the root's. Headline, Title and Subtitle are set as multiples of the
tier root (`--type-root`: 16px at the root, 16 / 18 / 20px on the older / middle / early tiers),
so a heading is never smaller than the body it heads: Headline 1.5×, Title 1.125× (a report title
1.25×), Subtitle 1×.
- **Display** (600, 28px): the tally numeral in a kid's day box on Today, the grade in a class
  page's strip cells (the Headline size on a phone, where three cells share the row) and the kid
  chooser's heading. The
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
  line, the foot links, the status line, badges, chips, the record inset, and on Open work the
  as-of line, the "Until Wed 10/7" sub-line and the legend. The rail's tabs are
  body size, not label size: a page's name is not a meta line. Tiers raise it to 15px
  (middle) and 16px (early) so the lines a child is asked to judge are never the smallest text.
- **Day label** (650, `--type-small`, .08em tracking, uppercase, Pencil Grey): the rail's group
  names (WORK, TIME, APP) and "DUE TONIGHT",
  "DUE TOMORROW", "ON PAPER, NO GRADE YET" along a day box's top edge; on Today a kid's name and
  "· BY TOMORROW" along their box's edge (the name a link in the label's own grey), and the week
  strip's day word and date, and on Assignments a week's label ("THIS WEEK · MON 9/28", "WEEK
  OF MON 8/31") with its tally after it at 400, untracked and in sentence case, and on Open work a
  kid's page label ("ALEX — OPEN WORK · 6 open", the name a link in the label's grey), and on a
  class's page a grade cell's label (OFFICIAL, MON 9/28, CANVAS; the newest date on the yellow
  stroke). Never smaller
  than the line it heads, because it is set from the same tier token as the meta. On a phone
  the week strip's label alone drops to Caption size with .04em tracking so five cells share
  one row.
- **Day row** (650, `--type-small`, .04em tracking, uppercase, Pencil Grey): "TUE 9/29" over the
  lines due that day inside a week box on Assignments; the day label's lighter-tracked sibling
  for a head inside a box rather than along its edge. On Open work the two halves of a kid's
  sheet are day rows ("STILL FIXABLE · 3", "COMING DUE · 3", the tally at 400 in sentence case).
- **Caption** (400, 12px, `--type-tiny`): stamps, legends under tables, provenance. 13px (middle),
  14px (early).
- **Print heading** (Helvetica-Bold 16pt/19), **print group head** (Helvetica-Bold 11pt/13,
  a table print's group), **print cell** (Helvetica 10pt/12, bold for the status word),
  **print small** (8.5pt/10.5) and **print tiny** (8pt/9.5) for the sheet's sub-lines, and a
  7pt footer: the (size, leading) pairs of `tokens.PRINT` (`h1`, `group`, `cell`, `small`,
  `tiny`, `footer`), read by `sheet.py`. 10pt cells and 8pt sub-lines are the floor: two
  children still fit one page.

### Named Rules
**The Measure Rule.** Prose, intros and forms are bounded to 760px (`--measure`, about 75
characters at body size); tables, cards and charts fill the 1600px content column, and the planner
spread takes 1100px because two day boxes need more than a measure; Today's week strip and kids'
spread and Assignments' weekly pages take the same 1100px. Inside any wide box on a planner page
(`.planner-main`) the prose keeps to the measure while the sheet's word stays at the right: a
line's facts and ask line, an inset, a section's lead, the "asked the school" line, the review
line and an empty day's line (the re-critique of 2026-09-30 measured the Plan's facts at 1,070px
on a 1440px screen). The ruled header line is the one full-width sentence.

**The Never-Smallest Rule.** On a tiered page the secondary sizes and the headings move with the
body size. A fact a child must judge ("Canvas shows 0 of 10") is never rendered at the page's
smallest size, and the head of a section or a day box is never smaller than the sentence under it.

**The Strike Rule.** An answered line is struck through in place, its name in Pencil Grey, the
checkbox filled green with a drawn tick; the line keeps its place, its meta and its Undo. Nothing
is removed from the child's spread by an answer; the school's record removes it on the next
refresh.

## Layout

One shell, one content column. On a wide screen a 220px rail (`.rail`) sits at the left on
Planner White with the 1.5px Day-box rule as its right edge, holding the wordmark and the pages as
index tabs; the status line, an optional stale banner and the page stack in the second column.
Under 1024px (the sidecar keeps the breakpoint's old name, `strip`) the rail is one ruled row
with the 1.5px Day-box rule beneath it: the mark and the wordmark at the left, Menu at the right
as a 44px tab; open, the tabs wrap beneath the row as a list (`.rail nav { display: flex;
flex-wrap: wrap }`), group names dropped, and a fold in the row (the family's App, the kid's More)
is `display: contents` with its summary one more tab in the row and its contents wrapping
beneath. Nothing scrolls sideways and there is no fade. The Menu is `details.rail-menu[data-phone-fold]`
shipped open, its summary hidden beside a sidebar; `app.js` closes every
`details[data-phone-fold][open]` under 1024px on load, so the page works without script and a
phone starts folded. Kid mode's row hides the wordmark (`.rail:has(nav.kid) .brand-name`) and
shows Plan, Assignments and More beside the mark, "Not Sam?" appearing with the fold's contents.
A phone held sideways puts the row and the status line on one row. Under 1280px the status line
drops its two reassurance items and two-column workspaces such as the check-in stack.

Every page is the same blocks in the same order: status line, page head (crumb, title in the rail
link's words, actions at the right, one intro sentence bounded to the measure), notices, then the
content column, a ceiling of 1600px with 24px gutters (16px under the strip). The content column is
a stack of sections 32px apart. A section is an h3, a count, one lead sentence and its own controls
at the right; a folded section draws the same head as its summary; a fold with nothing in it is
one quiet line at body size ("Completed steps · nothing here yet"), its marker gone and its pointer
off. Under the strip a page action ("Print plan") and a section's control ("Check Canvas again",
"Add a step") are text links, not boxes between the title and the first line.

**The planner spread** (a child's Plan and Check-in): the child tabs standing on a 1.5px Day-box
rule, then one state line (the last check-in, its dates bold, what was agreed in Pencil Grey)
closing on a 1px Ruled Grey hairline (`.child-nav + .tab-hint`); in kid mode, where the rail is
the child's tabs and the page has none, the same line keeps the 1.5px rule as the ruled header
line. Then "Must finish" and its spread: a two-column grid with 16px gaps in which Tonight and
Tomorrow are day boxes side by side, printed whether or not anything is in them, and every other
section (Later, Overdue but still fixable, On paper, Waiting) takes the full width beneath as a
box of its own; under 1024px the grid is one column, Tonight first, and when Tonight and Tomorrow are both
empty the two boxes give way to one day pair (`.mf-spread.both-empty > .day-pair`, drawn only
under the strip) labelled "DUE TONIGHT · DUE TOMORROW" over "Nothing due tonight or tomorrow",
so an empty evening costs a child one box, not two; a wide screen keeps the pair of boxes. A day
box is 0 12px 4px inside with its label bleeding to the edges; the lines in it are 8px 0 8px 30px, the 30px being the
checkbox's column, under 1px hairlines, the last line without one. "Our next steps" follows as
lines under a ruled head, grouped by h4 (Work to do, Blocked, Waiting), a step's name at 600 and
its text in Pencil Grey. Behind all of it `.planner-main` draws a faint ruling pitched to the line
height (`--line` = 1.45 × root, Ruled Grey at 40%), and the day boxes are Paper White on top of it.
Under the steps the Plan closes on one review line (`p.review-line`, 16px above and 8px below:
"2 more on the school's list · Browse all work to plan something outside this list.") and the
sources legend; the check-in page keeps the full review queue beneath the same heading.

**The family's week** (Today): the page is three blocks in one wrapper (`.today-pages`, which
is `display: contents` on a wide screen): the sheet strip, the week block and the kids' block.
Under the page head the sheet strip, a `section` ruled top and bottom with the 1.5px Day-box
rule, 8px inside, 24px below: the last sheet's line (or "No sheet built today yet." in Pencil
Grey) and, inside `details.print-controls[data-phone-fold]` shipped open with its summary not
drawn, one wrapping row of the sheet's controls (Refresh now, the Refresh-first tick, Preview,
the Print two-step). Then, on the ruled page, the week strip: an
ordered list of five day cells in a five-column grid with 8px gaps, each a small day box whose
label is the day word, a separator and the date (TONIGHT · TUE 9/29, TOMORROW · WED 9/30, then
the bare date) over one Label-size line of per-child counts ("Alex 2 · Sam 2") or "nothing due"
in Pencil Grey; tonight's cell names the overdue-but-fixable rows beside the count ("Sam 2 late",
"Alex 1, 2 late") rather than folding them into it, so the strip and the Plan's DUE TONIGHT box
never disagree. Then the kids' spread: the planner spread's grid re-filled as
`repeat(auto-fit, minmax(320px, 1fr))`, one day box per child side by side, each box's label
the child's name; inside, two tally lines, a hairline, tonight's lines, the family line, three
links, the School record fold. Under 1024px the five cells stay in one row with 4px gaps on
`1.3fr 1.3fr 1fr 1fr 1fr` tracks (the two named days get the room their words need), the
separator vanishes and the day word stacks over the date, no sideways scroll; the kids' boxes
stack one to a row. On a phone `.today-pages` becomes a flex column with the week block first,
then the sheet strip folded to one 44px link-styled line ("▸ Print or preview", `app.js` closes
the `data-phone-fold` on load under 1024px; the markup ships it open so the page works without
script), then the kids, so the planner is the first thing under the title. Cancel on the Print
two-step returns focus to its summary. Today speaks in the parent's voice: a kid's box passes
`voice=''` to `_item.html`, so its ask line and answers are the household phrasing whatever the
child's tier, while the sheet's word keeps the child's words because it is the word on their sheet.

**The weekly pages** (a child's Assignments): under the child tabs and the ruled header line
("Done so far: 1 of 5 due · 1 on time."), one section, "All assignments" with its count, its
controls in the head (the view as words, the Class select when the child has more than one
class, otherwise folded behind More filters, and the More filters fold) and one lead
line with the question count ("1 question about your work" / "Nothing to answer."). Then, on the
ruled page, a run-in sort line ("Sort by Due · Assignment · Where it stands", 8px above and 12px
below) and the weeks: a one-column grid with 24px gaps so the ruling shows between the pages,
one week box per week the shown work was due, newest first, this week printed even when empty
("Nothing due this week"). Sorted by due date a week is day rows 12px above their lines, each
line saying only its hour ("by 11:59pm"); sorted any other way the lines keep their dates. A
line on a week carries its ask line and answers only when the app is asking (`only_asked`); the
school's list is not a second Plan, and "Plan a step" in the foot is the way to plan the rest.
A week with nothing shown is a fold whose summary is the label line with a tally ("· 1 not done ·
2 unknown"), the box closing on its label's rule. The sources legend, then the quiet verdict
sections (Settled by the records, Waiting) follow under the pages. On a phone the head's
controls wrap and the sheet's word drops to its own line as on the Plan.

**The sheet on a screen** (Open work): under the page head the kids as tabs (`.child-nav.kid-tabs`,
the child tabs capped at 1100px like the pages beneath), each name followed by its open count as a
Pencil Grey tally ("Alex · 6"), "Every kid" as one more tab in pencil at the right (`margin-left:
auto`); the first kid's tab is pulled forward by default, `?kid=<key>` turns the page and `?kid=all`
makes "Every kid" current. Then, on the ruled page, `.planner-main.open-sheets`: a one-column grid
with 24px gaps at 1100px holding one `section.sec.kid` per kid, every kid's page in the markup and
the ones not chosen `hidden`, so a tier never hides a row. A page is the day box holding a kid's
sheet: Paper White, 1.5px Day-box rule, 2px corners, 0 12px 4px inside, its label along the top
edge in Day label type ("ALEX — OPEN WORK · 6 open", the name a link in the label's grey, the
tally at 400 in sentence case), then the as-of line in Pencil Grey label type ("Wed 9/30 · next 14
days plus overdue within 14"). STILL FIXABLE · 3 as a day row, then its lines soonest-closing
window first (the first ruled above), the 1.5px Day-box rule above COMING DUE · 3 (the line before
it drops its hairline, so one rule parts the halves), then its lines by due date. An empty half is
one Pencil Grey line ("Nothing past due that can still be fixed.", "Nothing coming due in the next
14 days."); a kid with nothing open gets "Nothing open. Nice work." The trailer ("Not shown: 1 past
the late-work window or more than 14 days overdue (10 pts) · 2 handled") is Pencil Grey label type
at the page's foot, each count a link to the set it counts on Assignments. Under the pages, once,
the sheet's legend (`.sheet-legend`): a wrapped row of keys in label type, the sheet's capitals on
their highlighters. A tab is an htmx swap of `#open-pages` (tabs and pages together) and a plain
link without script. The lines are read-only (see The planner line): the name opens the record in
place, and that is the page's one interaction.

**The class's record** (a class's page): under the crumb and the class's name (the long name in
pencil after it), `.planner-main.class-record` at 1100px holds the grade strip: Today's week
strip turned to the grade (`.week-strip.grade-strip`, `repeat(auto-fill, minmax(150px, 1fr))`
with 8px gaps), one small day box per observation of this course's own number (Canvas' current
score or HAC's average), oldest first, the label along the top edge the refresh date, the value
at Display size in ink with the letter beside it, and under the newest cell one pencil line
naming whose number it is ("Canvas current", "HAC average · official"); the other gradebook's
number from the class's twin stands first in an OFFICIAL cell when it is the family's official
source, else last in a cell named for its gradebook, in pencil, its own date said as "as of
9/26". On a phone every cell stays on one row (`grid-auto-flow: column`), the numeral at the
Headline size. Beneath the strip two Pencil Grey label-size lines: the teacher, the email and
the twin ("Also in HAC as …"), then the sources fold (`details.sources-fold`) whose summary is
the sentence "Sources for this class: Canvas for scores, HAC for the average · change", "change"
the one link word; open (and held open by a rule of the class's own), the two selects and a
default Save on one wrapping row. Then two quiet folds, "How it moved" (the chart, its count of
refreshes) and "Notes" (open when there are any). Then "Assignments" with its count, the sort
line and the weekly pages exactly as on Assignments, every row from both gradebooks printed on
its week (a record folds nothing), the class name a plain word in each line's meta because every
line is this class, and the sources legend beneath.

**The household's list** (Questions): under the title and intro, one Pencil Grey label-size
line per kid with nothing to ask ("Nothing to ask about Sam's work.", drawn only while someone
has a question); then one section, "To answer" with the house's count, and on the ruled page
(`.planner-main.to-answer`, 1100px) the questions as planner lines under hairlines (the first
ruled above), in the order the school's deadlines close (the late-work window's last day, else
the due date), each line's pencil meta opening with the kid's name at 650 ("Alex · Honors
English 9 · 10 pts"), the facts, the ask line and the answers; an answered line becomes the
done-line in place, naming the kid ("Participation · Alex: Asked the teacher on 9/30 · Email the
teacher · Undo"). With nobody to ask, one line: "Nothing to ask about anyone's work tonight."
Beneath the list, per kid: the let-go sentence as a `form.let-go` pencil line at label size
("2 of Alex's assignments are too late for credit: …", the names in Ink at 650, the default
"Let all 2 go" button at its end; afterwards "Let go: …" with a link-button Undo in its place);
"Waiting on the teacher · Alex" and "Can't pair these · Alex" as quiet folds (`details.sec.quiet`)
at the list's width, the waiting lines under hairlines inside with no box. The page speaks in
the parent's voice (`voice=''`), as Today does, and so do the cards and done-lines swapped into
its `q-` slots.

**The setup page** (Settings): under the title and its one intro line ("Set up once; each part
saves to the file it names."), the first form (`form.settings-form`, a grid of sections 24px
apart at 1100px): School login, Printing and the report window, Where you are, Gradebook
sources, Network and Updates, each a `section.sec` with its `.sec-head` h3 at Title size, its
fields label over control on the ruling (`.settings-grid`, 220px tracks, the label at 550, the
control 1px Stroke Grey with 6px corners), its help as Pencil Grey label-size lines bounded to the
measure and an environment note the same in pencil; the form closes on the sticky Save bar
(`.settings-save-bar`, Planner White over a hairline, "Save config.toml" filled, "Test login"
beside it). Then `.settings-below`, parted from the form by the 1.5px
Day-box rule and 24px above and below each part: Gradebook overrides (still a table), the job
card when a job runs, Late-work rules and Days the sheet does not print as `form.sec` editors
with their `.sec-head`, their help, a fieldset drawn as a hairline above with the legend as a
day-row label (DEFAULT, QUARTERS, RULES), their folds closed on a fresh load and open after a
save or an error (`details.fold`, `details.skip-days`: a pencil line with the ▸ text marker), the
rows inside as ruled lines under hairlines with their inputs at the left and Remove, ↑ and ↓
pushed right (`.row`), and a filled "Save late-rules.toml" / "Save no-print-days.txt" at the end,
each form parted from the next by the printed rule; then About, a quiet fold. Remove on a row is
the default stroke: a row edit is reversible, not a deletion. A notice ("Saved.") is one line in ink under a hairline; a warning
keeps the Red Pen Wash with Red Pen text. The incumbent's eight white cards, boxed fieldsets and
seam sentence are gone.

**The report card page** (Trends): under the title and intro, one run-in line in the sort line's
grammar (`p.sort.trend-words`: "Kid all · Alex · Sam — Weeks 4 · 8 · 16", the chosen words Ink
at 650 with no underline, the others Ballpoint links, the groups parted by an em dash; in kid
mode the Kid words are not drawn). Then `.planner-main.trends-page` at 1100px holding one
`section.sec.report-card`, the sheet page's box (Paper White, 1.5px Day-box rule, 2px corners,
0 12px 8px inside) labelled along its top edge in Day label type ("THE YEAR SO FAR · last 8
weeks · Alex", the tally at 400 in sentence case). Inside, the parts as Day row heads 16px
apart: ON-TIME HAND-INS over the record line in body type ("17% on time" at 650, the five
counts parted by "·", "not done" and "unknown" in Red Pen when not zero) and a pencil note;
GRADES over its caption and one chart per kid, each `.chart-holder` drawn flat on the page (no
border, no fill, no padding) with its key beneath; WORK DUE EACH WEEK over its caption, the
stacked bar and "▸ The numbers", a pencil fold (`details.fold.numbers`) holding the table;
OPEN THE LONGEST over `ul.longest`, pencil-parted lines under hairlines capped at the measure.
With no history at all the page is one sentence ("Not enough history yet …") and no box. The
Chart.js figures take the planner's hand through `Chart.defaults` (the page's font, pencil for
axis text and titles at 400, the planner's hairline for the grid) and a bar chart under a day
row drops its canvas title; the configs are untouched.

**The planner's log** (Changes): under the title and intro, one run-in line in the sort line's
grammar (`p.sort.change-words`: "Since yesterday · Last 3 days · Last week · Last month — Kid all
· Alex · Sam — Kind all · New · Grade posted · …", the chosen words Ink at 650, the others
Ballpoint links, the groups parted by em dashes; in kid mode the Kid words are not drawn; every
word a plain link, since the words sit outside the swapped log). Then `.planner-main.change-log`
at 1100px: the page's events grouped by the household's day, newest first, each day a Day row
head ("WED 9/30") with its tally after it at 400 in sentence case (the total, then each kind that
happened in the kinds' order: "· 12 changes · 1 grade posted · 1 now missing · 4 answers"), the
first line ruled above; each `.change` one ruled line under a hairline: the time in Pencil Grey
label type at a 5.5em minimum width, the kind as a word at 650 in Ink, the item's name a
Ballpoint link (`.subject`; `.item` is the planner line's own class), the kid (a link in the
pencil, 24px on a coarse pointer) and the class and gradebook in the pencil meta, the detail in
Ink capped at the measure. A name opens the record in `.detail-slot` under its line (hidden until
filled; app.js shows and clears it as it does a table's detail row; the record inside draws
without the planner's checkbox or its own hairline). An empty window is one pencil line
("Nothing has changed in this window."); a long window pages 500 at a time with "Showing 1–500
of 1,204 changes · Older ›" as a pencil line under the log.

The spacing scale is 4px steps: 4, 8, 12, 16, 24, 32 (`--s1` to `--s6`). Cards sit on a
`repeat(auto-fit, minmax(280px, 1fr))` grid with 16px gaps; form fields on a `minmax(220px, 1fr)`
grid label-over-control. Tables are full width with 6px 8px cells, rising to 10px 8px on a coarse
pointer and 12px 10px on the early tier. Under the strip a work list stops being a table: each row
is one box under a hairline and the header row becomes a row of sort links. A quiet fold carries
24px above its head and 12px below.

## Elevation & Depth

Flat at rest. Depth comes from paper on paper and from rules: a Paper White day box printed with a
1.5px Day-box rule on the Planner White page, the faint ruling behind the page, a hairline under
each line, an inset in the wash inside a box. The one `box-shadow` in the shipped stylesheet is
not a lift: the current child tab's `0 1.5px 0 var(--paper)` is a paper eraser laid over the rule
the tabs stand on, exactly the rule's own width and no blur, so the tab opens onto the page.

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
word, nothing else. Cards remain the container on the pages whose content is still the incumbent
composition (Reports) inside the planner's shell.

## Shapes

Printed stationery. The planner's corners are near-square (2px): the day box, the 18px checkbox
with its 2px rule, the highlighter stroke, a chart swatch, the rail's index tabs and the child
tabs and the Menu / App / More fold tabs. Controls keep 6px (buttons, inputs, selects), 8px on cards, insets and chart holders
(`--radius`), 10px pills on badges, chips and chart-key buttons, 12px on the kid chooser's large
buttons, 4px on the stale banner. Strokes are 1px Stroke Grey on controls, 1px Ruled Grey on
hairlines and cards, 1.5px Day-box Blue-grey on the day box, its label's underline, the rail's
edge, the three sides of a current tab, the rule the child tabs stand on and the ruled header
lines, 2px on the checkbox and the default answer. The checkbox's tick is drawn, not a
glyph: two sides of a rotated square in Paper White on the green fill. A grey line (nothing to do,
the school has it) draws its checkbox dashed. The wordmark's mark is a 28px square with 6px
corners. The one gradient in the system is functional, not decorative: the repeating ruling
behind the planner page (the family strip's right-edge fade went with the strip, 2026-09-30).

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
- **Two-step in the sheet strip (Today):** an action that spends paper asks in place, never in a
  browser dialog. "Print now" is a disclosure summary in the primary look; open, it steps back to the
  plain look and the question ("Print today's sheet on Kitchen Inkjet?") sits under it with the
  filled "Print" and a "Cancel" link button; Cancel closes the fold and puts focus back on its
  summary. A job's log then lives behind a "Details" fold.
- **Step done (the Plan):** a live step on "Our next steps" carries one secondary button in an
  `.answers` form ("Done"; "I did it" on the early tier, `a.step_done`) posting to the step's
  complete route, the planner's tick on the family's own line; its foot link is "Edit step", and
  the step's undo is "Edit or reopen" under Completed steps.
- **Link button:** no border or fill, Pencil Grey underlined text, for "Close" and "undo".
- **Button link (an `<a>` drawn as a button):** the secondary look with 8px 12px padding ("Print
  plan", "Add a step"); under the strip it is a Ballpoint Blue underlined link. A section's
  control that is a `<button>` ("Check Canvas again") follows it under the strip, drawn as the
  same underlined link but keeping its 44px height (`.sec-head .controls button`).
- **Chooser button:** the kid chooser's 22px text, 18px padding, 12px corners, Ruled Grey stroke;
  the grown-up's is 16px on the wash in Pencil Grey.

### Chips
- **Style:** Planner White fill, 1px Ruled Grey border, 10px pill, 1px 8px padding, label type,
  Ink text. Badges ("Must finish"-style flags in a meta line, "printed"), filter chips, the
  segmented Open/Everything choice and chart-key buttons share it.
- **State:** the one in force is filled Ballpoint Blue with white text; a linked badge's border
  turns Ballpoint Blue on hover; a chart series toggled off is Pencil Grey, struck through, its
  swatch at 30%. In the status line a badge is a word, not a chip (`header.status .badge {
  border: 0; padding: 0; background: none }`): a run's outcome in Checkmark Green or Red Pen, the
  update and a running job as plain Ballpoint Blue links.
- **As words (Assignments):** the Open / Everything choice sheds the pill: "Show" in Pencil Grey,
  the chosen word in Ink at 650 with no underline, the others Ballpoint Blue underlined links,
  8px apart; the radio stays hidden behind each word and the focus ring sits 2px out. A page in
  the planner world fills nothing.
- **Flag badge:** the family's answer as it stands ("let go 9/12") in a line's meta, the same
  neutral pill.
- **Question badge (Open work):** on a read-only line the app's question is a "question" link in
  the meta, the same pill, to the page that asks (`/questions?kid=…#q-<id>`); 44px on a coarse
  pointer like every linked badge.

### Cards / Containers
- **Day box (planner):** Paper White, 1.5px Day-box Blue-grey border, 2px corners, 0 12px 4px
  inside; its h4 label runs along the top edge in Day label type over a 1.5px rule of the same
  colour. Tonight and Tomorrow are always printed; an empty one holds one Pencil Grey line
  ("Nothing due tonight"). A folded section (Later, Waiting) opens onto a day box 8px below its
  summary.
- **Day pair (planner, phone only):** when Tonight and Tomorrow are both empty, one day box
  (`.mf-section.day-pair`) labelled "DUE TONIGHT · DUE TOMORROW" over the Pencil Grey
  "Nothing due tonight or tomorrow" (`.empty-day`, kept to the measure) stands in for the two
  under the strip breakpoint; the pair is in the markup only when both are empty and is never
  drawn on a wide screen.
- **Print-controls fold (Today):** `details.print-controls` around the sheet's controls, shipped
  open. On a wide screen its summary is not drawn and the controls are the strip's row; on a
  phone `app.js` folds it and the summary is one 44px Ballpoint Blue underlined line with the
  text marker ("▸ Print or preview", "▾" open), the controls 8px beneath when opened.
- **Review line (the Plan):** the check-in's review queue reduced to one body-size sentence
  (`p.review-line`) under the steps: the count in the phrase table's words ("2 more on the
  school's list", `copy.more_on_school_list`), a "Browse all work" link at 44px on a coarse
  pointer, and the sources legend after it. The check-in keeps the queue itself.
- **Card (incumbent shell: Reports, the job card, the check-in's "Agree and wrap up"):** Paper
  White, 1px Ruled Grey, 8px corners, 12px 16px inside, no shadow.
- **Inset:** anything quoted inside a box: the record, a witness line, the class's pace, the
  "school evidence changed" notice. Planner White, 8px corners, 8px 12px, label type, no left
  rule; the changed notice's lead is Ballpoint Blue 600.
- **Kid's day box (Today):** the day box with the child's name as its label, a link in the label's
  grey that underlines on hover, followed by "· BY TOMORROW". Its first lines are the two tallies
  (the Display numeral and its words, one link), then a 1px Ruled Grey hairline above the first
  planner line; the family line and the three links sit 8px apart under the last line, and the
  fold 8px below them. Boxes fill `minmax(320px, 1fr)` tracks, never spanning the row.
- **Week box (Assignments):** the day box holding a week: the same Paper White, 1.5px rule, 2px
  corners and 0 12px 4px inside, its label along the top edge ("THIS WEEK · MON 9/28", "LAST
  WEEK · MON 9/21", "NEXT WEEK", "WEEK OF MON 8/31"; the separator only parts two names), this
  week's word on the yellow stroke in Ink. Inside: day rows over their lines, each line at card
  density under a hairline (the first after a day row ruled above it, the last without one),
  prose capped at the measure. A week with nothing shown is the same box folded: its summary is
  the label with a text marker (▸ closed, ▾ open) and the tally, no rule and no padding beneath
  until it opens; this week is printed open even when empty.
- **Log line (Changes, `.change`):** one thing that moved as a ruled line under a hairline: the
  time in Pencil Grey label type, the kind as a word at 650, the item's name a Ballpoint link
  that opens the record in the `.detail-slot` beneath, the kid and class in the pencil meta, the
  detail in Ink. A day's lines sit under a Day row head carrying the day's tally.
- **Report card page (Trends):** the sheet page's box holding the year (`.trends-page >
  .report-card`): the label along the top edge, the parts as Day row heads, the record line, the
  charts flat on the page, the numbers fold, the longest-open lines. One box on the page.
- **Sheet page (Open work):** the day box holding a kid's whole sheet (`.open-sheets > .sec.kid`):
  the same Paper White, 1.5px rule, 2px corners and 0 12px 4px inside, its label along the top
  edge the way the sheet's heading reads ("ALEX — OPEN WORK · 6 open"), the as-of line in pencil,
  STILL FIXABLE and COMING DUE as day rows parted by the printed rule, read-only lines, the
  trailer at the foot. The pages not chosen stay in the markup, `hidden`.
- **Day cell (the week strip):** a day box shrunk to a label and one line: the same 1.5px rule
  and 2px corners, 0 12px 8px inside, the label along the top edge, one Label-size Pencil Grey
  line of counts. Tonight's cell carries its day word on the yellow stroke (Ink, 0 .35em, 2px
  corners). On a phone: 0 4px 4px inside, the label at Caption size.
- **Grade cell (a class's page):** the day cell holding a grade: the refresh date (or OFFICIAL, or
  the other gradebook's name) along the top edge, the value at Display size in ink with the
  letter beside it, one Pencil Grey label-size line beneath saying whose number ("Canvas
  current · official", "HAC average · as of 9/26"). The newest date sits on the yellow stroke;
  the other gradebook's cell is pencil throughout. On a phone the numeral drops to the Headline
  size and the line to Caption size so three cells share one row.
- **Sources fold (a class's page):** `details.sources-fold`, one Pencil Grey label-size sentence
  as its summary with "change" the only link word (no marker), the two selects and a default Save
  on one wrapping row when open; a rule of the class's own keeps it open. 44px on a coarse
  pointer.
- **Note:** one of the family's lines: body text under a 1px Ruled Grey hairline, its meta in
  Pencil Grey label type, no left rule and no fill (the Only-Box Rule; the left-ruled block went
  2026-09-30).
- **Lines list (Assignments' verdict sections):** Paper White, 1px Ruled Grey, 8px corners,
  0 16px, one action per row at the right, rows under hairlines. On Questions the waiting lines
  shed the box (`.waiting > .line`): lines under hairlines on the page, the Email link at the
  right, 44px on a coarse pointer.
- **Let-go line (Questions):** `form.let-go`, one Pencil Grey label-size sentence naming every
  assignment it will let go (the names in Ink at 650) with the default button at its end, 16px
  above; after it runs, "Let go: …" with a link-button Undo in its place (`role="status"`). No
  box, no fill.

### Inputs / Fields
- **Style:** Paper White, 1px Stroke Grey, 6px corners, inherits body type, 4px 6px padding
  (10px 14px on touch). Textareas 60px minimum, 88px in the plan form. Labels sit over their
  controls at 550 weight with Pencil Grey 13px help text beneath.
- **Focus:** a 3px Ballpoint Blue outline offset 3px, on every focusable thing including hidden
  radio chips.
- **Checkbox / radio:** 24px square on a coarse pointer (WCAG 2.5.8). The planner line's own
  checkbox is drawn, not an input: the answer buttons are the control.
- **Error / Disabled:** no distinct field error style; errors are said in a warn notice.
- **Fieldset (Settings, the report builder):** no box: a 1px Ruled Grey hairline above with the
  legend as a Day row label (650, `--type-small`, .04em, uppercase, Pencil Grey; its aside at
  400 in sentence case), 8px of room beneath, 12px below the group.
- **Editor row (`.row`, Settings):** one quarter, rule or no-print date as a ruled line: inputs
  at the left in a wrapping row, Remove (danger) and the ↑ ↓ buttons pushed right, a 1px Ruled
  Grey hairline beneath, the last row without one; "Add quarter" / "Add rule" / "Add date" a
  default button after the rows.
- **Notice:** what the last POST did, said once between the head and the content: one line in
  Ink under a 1px Ruled Grey hairline, bounded to the measure; a warning (`.notice.warn`) keeps
  the Red Pen Wash fill with Red Pen text and 4px corners. No left rule anywhere.
- **Sticky Save bar (Settings):** `.settings-save-bar`, Planner White over a 1px hairline, stuck
  to the viewport's bottom while the long first form scrolls, holding the page's one filled
  button ("Save config.toml") and "Test login"; the two editors below the printed rule each fill
  their own Save, named for its file.

### Navigation
- **Rail (`.rail`):** Planner White, the 1.5px Day-box rule as its right edge, 16px above, below
  and at the left, nothing at the right so a tab can reach the edge. The wordmark (the 28px mark
  with 6px corners plus "Fridge Sheet", 18px) then the pages as tabs. In family mode the tabs sit
  inside `details.rail-menu[data-phone-fold]`, shipped open, whose Menu summary is not drawn
  beside a page. On a child's page the rail folds everything but Today and that child under an
  App fold.
- **Index tab (`.rail nav a`):** body type in Ink, 6px 12px, a 1.5px transparent border with no
  right border, 2px corners, margin-right -1.5px so it sits over the rail's edge, no fill at rest;
  under the pointer the word underlines. A question count rides beside a child's name (or on Plan
  in kid mode) in Ballpoint Blue 600 at 13px.
- **Current tab (`.rail nav a.current`):** Paper White with the Day-box rule on its three drawn
  sides, open toward the page over the rail's edge, so it reads as the tab in front. The tab
  moves with the page; nothing else in the rail changes.
- **Group name (`.rail nav .group`):** Day label type (`--type-small`, 650, .08em, uppercase,
  Pencil Grey), 16px above and 4px below: WORK, TIME, APP.
- **Fold tab (`.rail nav .rail-more > summary`):** the family's App and the kid's More
  (`copy.more`) are one more tab in Pencil Grey, 12px above, marker hidden, a text ▸ (▾ open)
  spaced .3em before the word, underline on hover; open, the rest (`.rail-rest`) unfolds beneath.
  In kid mode More holds Check-in, Trends and Changes, opened on the page it holds; Plan and
  Assignments stand first, and "Not {name}?" is a Pencil Grey label-type foot 24px below.
- **Phone row (under 1024px):** the rail is one ruled row, `display: flex; flex-wrap: wrap`,
  8px 16px inside, the 1.5px Day-box rule beneath. The wordmark at the left; Menu at the right
  (`.rail-menu > summary`: `display: contents` on the fold, the summary an inline-flex 44px tab
  in Ink, 0 12px, the 2px corner, a Pencil Grey ▸/▾ marker .3em before it, underline on hover,
  `margin-left: auto`). Open, the nav takes the full row (`flex-basis: 100%`) and the tabs wrap
  beneath at 8px 10px, each with its 1.5px transparent border; the current tab's border turns
  Day-box (on a phone the tab is boxed on all four sides: the phone rule resets the border
  shorthand). Group names are hidden. A fold in the row is `display: contents`: App or More is
  one more tab in the row and `.rail-rest` wraps beneath at 100%. Kid mode hides the wordmark,
  lays Plan, Assignments and More in the row beside the mark, and shows "Not Sam?" only with the
  fold's contents (`.rail nav.kid .rail-more:not([open]) ~ a.foot { display: none }`).
- **Child tabs (`.child-nav`):** the index tabs turned sideways: three body-type Ink links at
  10px 14px, 4px apart, each with a 1.5px transparent border and no bottom border, 2px corners,
  margin-bottom -1.5px, standing on a 1.5px Day-box rule; underline on hover. The current one
  (`a[aria-current]`) is Paper White at 650 with the Day-box rule on three sides and a paper
  eraser over the rule beneath (`box-shadow: 0 1.5px 0 var(--paper)`) so it opens onto the page.
  No blue underline remains.
- **State line (`.tab-hint`):** under the tabs, one body-size line in Ink with its dates at 650
  and the agreement in Pencil Grey, 8px above and below, 24px beneath; after the child tabs it
  closes on a 1px Ruled Grey hairline (`.child-nav + .tab-hint`), and in kid mode, where there
  are no tabs, it keeps the 1.5px Day-box rule as the ruled header line; "Our next steps" draws
  the 1.5px rule under its head.
- **Sort line (Assignments):** one run-in line in Pencil Grey label type, "Sort by" then the three
  keys as links parted by "·"; the active key is Ink at 650 with no underline, followed by a
  drawn chevron (a 10-unit SVG path in the pencil colour at .6em, up or down for the direction)
  that the key's `aria-current` already says in words. 44px tall on a coarse pointer.
- **Kid tabs (Open work, `.child-nav.kid-tabs`):** the child tabs with the kids as pages: each
  name with its open count as a Pencil Grey 400 label-size tally ("Alex · 6"), never the blue
  question count; "Every kid" in Pencil Grey at the right (`margin-left: auto`), one more tab.
  The current one is pulled forward as any child tab; on `?kid=all` "Every kid" is current.
  Capped at 1100px so the row is the pages' own width. 44px on a coarse pointer.

### Status line (signature, the shell)
The page's ruled "as of" line (`header.status`): one wrapping line of Pencil Grey `--type-small`
type, 12px 24px 8px, closing on a 1px Ruled Grey hairline, the first thing written on the page:
when the data was refreshed, each source's state in Checkmark Green or Red Pen with the word "OK"
or the error, the last run's outcome as a word in its colour, a running job and an available
update as plain Ballpoint Blue links (a badge in this line has no border, padding or fill), and
the clock. Its links are 44px on a coarse pointer. Under 1024px it keeps the shorter texts
(`.short`) so it is one line at 390px with an update pending; below 1280px it drops its
reassurances and never its warnings. Below it, when the data is older than the runner will print
from, a Red Pen Wash banner with Red Pen text and a "Refresh now" link.

### The sheet strip (signature, Today)
The sheet's controls as the page's date header: one section ruled above and below with the
1.5px Day-box rule, holding what printed today (time, label, pages, per-child counts, a link to
the PDF) or the Pencil Grey "No sheet built today yet.", then one wrapping row of buttons with
8px 12px gaps: Refresh now, the Refresh-data-first tick, Preview, and the Print two-step whose
open answers sit 4px under the question. It is the only place on Today that Ballpoint Blue fills
anything.

### The planner line (signature)
One assignment, one line, app-wide. An 18px square checkbox at the left (2px Day-box rule, Paper
White, 2px corners) whose rule takes the line's tone: Ballpoint Blue for a question or a due line,
Red Pen for not in, Amber Pencil Ink for late, Purple Stamp for check-on-paper, dashed for a grey
line, and filled Checkmark Green with a drawn tick once answered or done. Head: the name (650,
linked to Assignments; on Assignments itself the name opens the record in place of the line, the
record keeping the line's checkbox colour and the sheet's word at its head from the one
`line_tone` filter the two share, and a "Close" link button at the head's right fetches the
line back, repeated at the record's foot because a record is tall on a phone), meta in Pencil
Grey label type
(class · kind · points · due; on Assignments the class is a link, kept to 24px with padding on a
coarse pointer, and the family's answer rides in it as a flag badge), and the
sheet's word pushed right as a highlighter stroke (700, ink of its family on its fill); on a phone
the word drops to its own line and hugs its width. Facts: one sentence from the verdict. Ask line
(600) and answers: the first answer in the default stroke, the two answers that close a line for
good behind a "More answers" fold inside the line, identically at every tier; on a week's line
on Assignments the ask line and answers appear only when the app is asking. Once answered, the
done-line takes the answers' place: the green glyph, the sentence flexing to the room (`flex: 1
1 auto; min-width: 0`), and the Undo form pushed right and never shrunk (`flex: none`, its button
`white-space: nowrap; overflow-wrap: normal`), so "Undo" is one word on one line on a phone. The family's layer:
one Pencil Grey label-size line each, no rule. Foot: "▸ Record" and "Plan a step" as blue links
and a Caption-size stamp pushed right ("New since Tue 9/29"). Inside a table's opened row or a
card the same line draws without the checkbox and without its hairline. A step on "Our next
steps" is the same line with its "Must finish · MISSING" word highlighted inside the meta. On
Open work the line is read-only (`read_only`): no ask line, no answers, no foot and no Edit on
the step; the name opens the record in place, a question is a "question" link in the meta, and a
still-fixable line's facts end with the sheet's sub-line in Pencil Grey ("Until Wed 10/7",
`copy.until`) where the working pages say the whole late-work sentence.

### The printed sheet (signature, paper)
Landscape Letter, 0.5in margins, one section per child. Helvetica-Bold 16pt heading, 10pt cells
with the status word bold in its colour, 8.5pt and 8pt sub-lines for the "until" date, the
follow-up marker and notes, an 11pt checkbox per row, a legend at the foot. Overdue first, then
coming due, then two trailer counts. Its colours are the page's, by role from `tokens.PRINT`:
the status words in Red Pen, Amber Pencil Ink, Ballpoint Blue and Purple Stamp (the same table
as the screen's, `STATUS_COLOR`), NEW in Checkmark Green, notes, "was" lines and the footer in
Pencil Grey, the header rule, the section rule and the checkbox in Ink, and the 0.25pt hairline
under each row in Ruled Grey. The reader is a child standing at a fridge; the Plan on screen is
this sheet's spread.

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
- **Do** give every button, control, tab and main link 44px on a coarse pointer (a line's name,
  its foot links, the done-line's Undo, the sort keys, the review line's link, a kid box's three
  links, the print-controls summary, the rail's tabs and its App / More / Menu fold tabs, the
  status line's links, the kids' tabs and "Every kid" on Open work, a class page's sources fold
  and the teacher's email, and a section's link-styled control under the strip); a
  secondary link inside a line or card keeps a 24px floor with 3px padding-block (the class in
  a line's meta, a step's Edit, a kid box's name; the maintainer's rule, 2026-09-29, measured at
  18px on the names 2026-09-30), and a checkbox or radio input is 24px.
- **Do** redefine every token when adding to a tier, and set secondary sizes and the day label
  from `--type-small` and `--type-tiny` so they move with the tier.
- **Do** render a fold with nothing in it as one quiet Pencil Grey line at body size, marker gone,
  not a heading over nothing.
- **Do** bound prose and forms to `--measure` (760px), the planner spread to 1100px, and let
  tables, cards and charts fill the column.
- **Do** build a new page from the same blocks: status bar, page head, notices, sections of
  `.sec` with `.sec-head`, and assignments as `_item.html` at card, detail or line density; a
  page that is a planner wraps its spread in `.planner-main` for the ruling and deals its boxes
  as `.mf-section` inside `.mf-spread`, or as `.mf-section.week` inside `.weeks` when the boxes
  are weeks.
- **Do** label a week or a day the way the planner prints it: the box's label along the top
  edge in Day label type, the day row inside it in Day row type, this week's word on the yellow
  stroke in Ink, and a tally in sentence case at 400 after a folded label.
- **Do** use the 4px spacing scale (`--s1` to `--s6`) and the 2px / 6px / 8px / 10px radius set.

### Don't:
- **Don't** convey state by colour alone, and don't make a past due date red on its own; red is for
  what the school recorded as not in.
- **Don't** fill the sheet's word as a button or stretch its highlighter into a bar; the stroke
  hugs the word.
- **Don't** add shadows to boxes, lines or anything at rest; a shadow may lift only a sticky bar,
  an open menu or the chooser's buttons, and no heavier than the provisional ambient lift.
- **Don't** animate anything but the checkbox fill and the strike (180ms ease-out).
- **Don't** introduce a second value for a status colour. The printed sheet, the charts and the
  page read one source (`fridgesheet/tokens.py`); a colour that differs between the fridge and
  the screen is a bug, not a variant.
- **Don't** use gradients, glows, or decorative imagery; the only gradient is the planner's
  ruling.
- **Don't** give a tab a fill, a pill or a rounded hover at rest, and don't scroll a row of tabs
  sideways: a tab underlines under the pointer, the current one is pulled forward in Paper White
  with the Day-box rule, and on a phone the tabs wrap beneath the ruled row behind Menu.
- **Don't** put a card, a left rule or a box inside a day box; the inset is the one thing quoted
  inside a line.
- **Don't** hide a row or an action from a child by tier; fold navigation and secondary fields if
  you must, identically at every tier.
- **Don't** hard-code a colour or a type size in a template, in `sheet.py`, `charts.py` or
  `app.js`, or in `app.css` outside its generated token lines; every value in this file is a
  name in `tokens.py` to reach for (`tests/test_web_colour_and_type.py` and
  `tests/test_tokens.py` hold the line). Edit `tokens.py`, run `scripts/tokens_css.py`, and
  update this frontmatter; never edit the `:root` or `[data-tier]` lines by hand.
- **Don't** fill more than one button per page, and don't fill an answer: the first answer on a
  line is the Ballpoint Blue default stroke.
- **Don't** set a count beside a name in Ballpoint Blue unless it is the question count; a tab's
  open count on Open work is a Pencil Grey tally ("Alex · 6").
- **Don't** link a line's class to the page it is already on: on a class's page the class name in
  every meta is a plain word (`on_class_page` in `_week_line.html`).
- **Don't** change tier line by line: a page that lists several kids' lines (Questions) speaks in
  the parent's voice and names the kid in each line's meta (`kid_label`).
- **Don't** box a form's parts: a fieldset is a hairline with a day-row label, an editor's row a
  ruled line, a notice a line under a hairline; a page with three forms parts them with the
  printed rule and fills one Save per form, named for the file it writes.
