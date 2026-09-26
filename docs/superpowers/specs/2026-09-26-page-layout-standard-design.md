# One page layout for every page: the standard

Date: 2026-09-26. Asked for by the maintainer: *"audit each page of fridgesheet to ensure
we're maximizing use of screen real estate across all platforms/viewport types/sizes and
following a consistent standard page layout across the entire app. Use design, UX/UI,
psychologist personas to develop the standard first, then align the entire app to it."*

This is the standard. The audit that produced it, with the measurements before and after,
is `docs/product/2026-09-26-page-layout-audit.md`. The mechanism is section 5; the tests
that hold it are section 6.

## 1. Who drew it up

Three simulated reviewers, each given the measurements and every screenshot, each asked
for the rules they would refuse to ship without. These are personas, not user research;
the household's own reading is still the maintainer's to do (kids' UX audit, F1).

**Mara, product designer.** Owns the visual system: one spacing scale, one type scale, one
container, the same block in the same place on every page. Her test for a rule is *"can I
tell which page this is with the content blurred out?"* If the answer is yes, the pages are
consistent enough; if every page looks the same with the content blurred, they are.

**Devin, interaction designer.** Owns the phone and the kiosk: what a thumb reaches, what
the first screen shows, what a swipe reveals and whether anything says so. His test is the
first screen at 390 px: *"how far down is the first thing I came here for, and what is above
it that I did not?"*

**Dr. Okafor, cognitive psychologist (reading and attention).** Owns the reader: line
length, orientation, where the eye lands, what the layout says about the reader's
competence. Her rules come from the reading research: a comfortable measure is 45–75
characters, the F-pattern puts the first fixation top-left, orientation cues that move
between pages cost a re-orientation each time, and every element that is not the task is a
distractor the reader pays for. Her test is *"does the page tell the reader where they are
and what to do, in the same place, every time?"*

### Where they disagreed, and what was decided

- **Fill the screen, or bound the line?** Mara and Devin wanted the content column to grow
  with the window (the 1100 px ceiling leaves a third of a 1920 px screen blank, half of a
  2560 px one). Dr. Okafor would not accept prose or a three-column table running 1,500 px
  wide. **Decided:** the *container* is fluid to 1600 px, the same on every page; *prose and
  forms* are bounded at a measure (760 px, about 75 characters at body size); *tables,
  cards and charts* fill the container, and a table's first column is pinned narrow so a
  wide table does not push its second column off the reader's eye line.
- **Taglines.** Mara liked the two eyebrows ("A little clarity for today", "One step at a
  time"). Dr. Okafor pointed out that on every other page `.eyebrow` means *the class name*
  above a card, so the same style carries two meanings, and that a page title should be the
  same words as the rail link that got the reader there (recognition, not recall).
  **Decided:** the page title is the rail label; the tagline becomes the page's one intro
  sentence where it says something ("What needs our attention?"), and is dropped where it
  does not.
- **The status bar on a phone.** Devin measured it: two lines, three when an update is
  available, so with the navigation strip the first content sits 210–250 px down a
  844 px screen, a quarter to a third of the first screen spent before the page starts.
  Dr. Okafor: the clock and "Last run OK" are reassurance, not information, on a device
  that has its own clock. Mara wanted it identical everywhere. **Decided:** one bar, same
  content order everywhere; below 1280 px (where a tablet's sidebar leaves the bar two
  lines) the two quiet items (the clock, and the last run *when it succeeded*) are not
  shown. A failed run, a running job, a warning and an available update still show on
  every width.
- **Where the sidebar becomes a strip.** 800 px today, so a phone held sideways (844 px)
  gets a 220 px sidebar beside a 624 px column and a check-in in two columns of 350 and
  250 px. **Decided:** the strip below 1024 px; two-column workspaces (the check-in) need
  1280 px; a tablet held upright gets the strip, held sideways gets the sidebar.

## 2. The anatomy of a page

Every page renders these blocks in this order. A block that has nothing to say is
absent, never an empty box.

```
┌ rail ─────┬───────────────────────────────────────────────────────────────┐
│ Fridge    │ status bar: Refreshed · Canvas · HAC · [Last run] · [job] · … │  one line
│ Sheet     ├───────────────────────────────────────────────────────────────┤
│ Today     │ ⚠ stale banner                                  only when stale│
│ Alex 1    ├───────────────────────────────────────────────────────────────┤
│ Sam       │ ← crumb                                    only on a sub-page │
│ WORK      │ Page title                               [page actions, right]│
│ …         │ One intro sentence, bounded to the measure.                   │
│           │ [Check-in · Plan · Assignments]           only on a child page │
│           ├───────────────────────────────────────────────────────────────┤
│           │ notice: Saved. / a problem, in a sentence      only after a POST│
│           ├───────────────────────────────────────────────────────────────┤
│           │ content: sections (h3) of cards, tables, forms, charts        │
└───────────┴───────────────────────────────────────────────────────────────┘
```

- **Rail.** 220 px sidebar from 1024 px up; one horizontal strip that scrolls sideways
  below that, with a fade at its right edge so a reader can see there is more. The current
  page is highlighted on both. A child's page folds the parent tools under "App" (kids' UX
  audit F5); that is the only permitted difference between pages.
- **Status bar.** One line, 13 px, `--muted`. Order: refreshed, sources, last run, job,
  update, warnings, clock. Under 1280 px the clock and a *successful* last run are hidden;
  everything that asks for attention stays.
- **Page head.** One partial, `_page_head.html`, on every page: optional crumb (a sub-page's
  way back, "← Alex's check-in"), the title as `<h2>` at 24 px, optional actions at the
  right (the page's own actions: "Print plan", "New report", "Run diagnostics"; never a
  row's), optional intro of **one sentence** bounded to the measure. The title is the words
  on the rail link, or the child's name on a child's page, or the record's name on a
  record's page (a class, a report).
- **Child tabs.** Only on a child's three pages, directly under the page head.
- **Notices.** The outcome of the last POST, as `.notice` (or `.notice.warn` with
  `role="alert"`), between the head and the content. Not as a bare coloured paragraph.
- **Content.** Sections headed by `<h3>`; cards, tables, forms and charts as below.

## 3. Space

| token | value | what it bounds |
|---|---|---|
| `--page-max` | 1600 px | the content column on every page, sidebar or strip |
| `--measure` | 760 px | prose (intros, hints, legends) and forms |
| `--rail` | 220 px | the sidebar |
| `--pad` | 24 px from 1024 px up; 16 px below | the page's side gutters |
| gap scale | 4 · 8 · 12 · 16 · 24 · 32 · 48 px | every margin and gap |

- **Tables** fill the container inside `.table-wrap`, which scrolls sideways on its own
  when the columns do not fit, so a table never overflows a card or the page. The first
  column of a work list is pinned to at most 8 rem (dates, times) so the assignment column
  stays beside it at any width.
- **Cards** lay out in a grid of `minmax(280px, 1fr)`: as many across as fit, stretched
  to fill the row. A grid of one card fills the container.
- **Two-column workspaces** (the check-in's review queue beside its plan) need 1280 px;
  below that they stack, the queue first, with the plan reachable by its in-page link.
- **Charts** take the container's width and a fixed height from the template.
- **Print pages** (a plan, a report view) have no rail or status bar, a 720 px centred
  column on screen and no chrome on paper; their tables still sit in `.table-wrap`.

## 4. Type and touch

| role | size | weight |
|---|---|---|
| page title (`.page-head h2`) | 24 px | 700 |
| section (`h3`) | 18 px | 650 |
| card title (`.card h2`, `.card h3`) | 16 px | 600 |
| body | 15 px root; 16 / 18 / 20 by tier on a child's page | 400 |
| secondary | `--type-small` (13 px root; tiered) | |
| status bar, eyebrow, stamp | `--type-tiny` (12 px root; tiered) | |

Everything a finger meets is at least 44 px tall under a coarse pointer, and a checkbox or
radio box is 24 px (WCAG 2.2, 2.5.8). The tier tokens and the parity rule from the
age-appropriate UI spec are unchanged: this standard moves chrome, never rows or actions.

## 5. Mechanism

- `static/app.css`: the tokens above at `:root`; `.shell` grid `var(--rail) minmax(0, 1fr)`;
  `main { max-width: var(--page-max); padding: 16px var(--pad) 48px }`; `.page-head`,
  `.page-head h2`, `.page-actions`, `.page-intro`, `.crumb`; the narrow block at
  `@media (max-width: 1023px)` (strip, fade, `--pad: 16px`); the workspace blocks at
  `@media (max-width: 1279px)` (`.status .quiet { display: none }`; `.checkin-layout`
  stacks, placed after the two-column rule it overrides); the coarse-pointer block
  unchanged except for the 24 px boxes. `main.wide` is gone: the check-in's width is every
  page's width. `.cards` uses `auto-fit`, so three cards fill a row instead of three of
  five tracks.
- `templates/_page_head.html`: `{% with title=…, intro=…, crumb=…, crumb_href=… %}`, with
  the actions passed as a captured block (`{% set page_actions %}…{% endset %}`). Every page
  template includes it in place of its own `<h2>`.
- `templates/_header.html`: the clock and a successful last run carry `class="quiet"`.
- Every `<table class="items">` sits inside `<div class="table-wrap">`; the
  `table.items:not(.work) { display: block }` phone rule is retired with it.

## 6. Tests

`tests/test_web_page_layout.py` holds the standard the way `test_web_tier_css.py` holds
the tiers: the tokens exist; the shell reads them; `main` has no other ceiling and no
template asks for `main.wide`; every full page template includes `_page_head.html` (the
two print pages included); every `table class="items"` in a template sits in a
`.table-wrap`; the narrow block is at 1023 px; the 1279 px blocks hide `.status .quiet` and
stack the check-in, the latter after the rule it overrides; coarse-pointer boxes are 24 px. `scripts/layout_audit_measure.py` is
the browser check, rerun by hand against `scripts/layout_audit_seed.py`.

## 7. Not in this standard

- Colour, the tier palettes, the phrase table and the outcome contract.
- Which rows a page shows (`docs/outcomes.md`, the parity rule).
- The printed PDF sheet (`sheet.py`), which has its own audit (kids' UX audit F11).
- The Schedules page's controls beyond its page head: PR #180 is rewriting that page.
