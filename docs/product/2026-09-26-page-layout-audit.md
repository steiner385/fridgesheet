# Every page against one layout: the audit

Date: 2026-09-26. Asked for by the maintainer: *"audit each page of fridgesheet to ensure
we're maximizing use of screen real estate across all platforms/viewport types/sizes and
following a consistent standard page layout across the entire app."* The standard that came
out of it, developed by three simulated reviewers, is
`docs/superpowers/specs/2026-09-26-page-layout-standard-design.md`. This is the audit: how
every page measured before, what was wrong, and how it measures after the alignment.

## 1. How it was measured

- `scripts/layout_audit_seed.py` builds a throwaway home from the test fixture household
  (`tests/web_fixtures.py`: two children, three refreshes, dates shifted so the fixture's
  "today" is this machine's), sets Alex to the older tier and Sam to the early one, adds a
  finished check-in with two steps, two runs and the four starter reports, and the app is
  started on it (`fridgesheet web --port 8577`).
- `scripts/layout_audit_measure.py` renders all 21 pages (every rail link, both children's
  three pages at two tiers, the step form, a class, the report builder and view, the two
  print pages, a 404) at seven viewports — phone 390×844 and 844×390, tablet 768×1024 and
  1024×768, laptop 1280×800, desktop 1920×1080, wide 2560×1440 — and records the rail's
  box, where `<main>` starts and how wide it is, the rightmost pixel any content reaches
  and so the share of the viewport left blank, the status bar's height, where the first
  heading and the first content land, page height in screens, horizontal overflow, and
  how many targets are under 44 px. Screenshots sit beside the JSON.
- Chromium only, via Playwright. Nobody was watched using it; the personas in the spec are
  simulated (kids' UX audit, F1, still stands).

## 2. What was found

Twelve findings, ranked by how many viewports and pages they touch.

### L1. A third of a desktop screen, half of a wide one, sat blank — high

`main { max-width: 1100px }` on every page but the check-in (1600 px).

| viewport | content column | blank at the right |
|---|---|---|
| 1280 laptop | 1060 px | 1.9 % |
| 1920 desktop | 1100 px | **32.5 %** |
| 2560 wide | 1100 px | **49.4 %** |

The kid table's three columns, the Runs table's seven and the Settings grid all stopped
at 1100 px with room beside them. **Now:** one ceiling, `--page-max: 1600px`, on every
page; blank at 1920 is 6.5 %, at 2560 29.8 % (the ceiling is the standard's, section 1).

### L2. A quarter of a phone's first screen went to chrome — high

At 390 px the strip (61 px) plus a two-line status bar (67 px; 106 px with an update
badge) put the first content 210–249 px down an 844 px screen, before the page had said
anything. The clock and "Last run OK" were two of the three lines. **Now:** the two quiet
items are dropped under 1280 px, the bar is one line (28 px), and the first content lands
at 117 px: 14 % of the screen, not 25–30 %.

### L3. Every page opened differently — high

Six heading patterns across nineteen pages: an eyebrow tagline over a 27 px title (Today,
check-in), a bare 22.5 px `<h2>` (most), a back link over the title (step form, class),
a title inside a print-controls row (the two print pages), messages as bare green or red
paragraphs (Reports, Settings, Schedules) or as a `.notice` (check-in), and the page's own
action as a badge (Reports' "New report"), a paragraph with a button (Diagnostics) or a
right-aligned row (check-in). The tagline eyebrow shared its style with the class name
above every card. Today's title ("What needs our attention?") was not the word on the rail
("Today"). **Now:** `_page_head.html` on every page — crumb, title in the rail's words at
24 px, actions at the right, one intro sentence — and `.notice` for what a POST did.

### L4. A phone held sideways got the desktop layout — medium-high

The strip breakpoint was 800 px, so 844×390 drew a 220 px sidebar (986 px tall, taller
than the screen) beside a 624 px column, and the check-in in two columns of 350 and
250 px. **Now:** strip under 1024 px, two-column check-in only from 1280 px.

### L5. A report table ran off its card on a phone — medium

`_report_preview.html`'s table sat in a card with nothing to scroll: at 390 px the Due
and Points columns were cut at the card's edge (`usedRight` 447 against a 390 px
viewport). Runs, Changes, Trends' week table and the class's grade history relied on a
phone-only `display: block` rule on the table itself, which the report view did not get.
**Now:** every `table.items` is inside `.table-wrap`, on every page, at every width.

### L6. Wide tables put the second column off the eye line — medium

Open work's fixed layout gave the date column 22 % of the table: 350 px at the new page
width. **Now:** `min(22%, 8rem)`.

### L7. Three cards in five tracks — medium

`.cards` used `auto-fill`, so at 1600 px Today's three cards took three of five 300 px
tracks and left two empty. **Now:** `auto-fit`; three cards fill the row.

### L8. The strip gave no sign it scrolled — medium

Fourteen links in a strip with a hidden scrollbar ended at "O…" with nothing to say
there was more. **Now:** a 32 px fade at the strip's right edge.

### L9. Day-of-week boxes under the target minimum — medium (touch)

Checkboxes and radios were 22 px under a coarse pointer; Schedules has 56 of them and
WCAG 2.2's floor is 24 px. **Now:** 24 px.

### L10. A select wider than the phone — low

On the Assignments page the Class filter's `<select>` took the width of its longest option
("Honors English 9 S1-2027-Hoch"), 423 px on a 390 px page. **Now:** capped at 100 %.

### L11. The status bar wrapped beside a tablet's sidebar — low

At 1024×768 the sidebar left 804 px, and the full bar took two lines (71 px). Fixed by
L2's rule, which is why that rule is at 1280 px rather than the strip's 1024 px.

### L12. Not layout, but found on the way — a class's page lists every row twice

`/kids/<kid>/courses/<id>` shows each assignment of a class with a HAC twin twice, with
the plain test fixture as well. The route appends the peer course's rows that
`items.list_items` had already merged. Filed as
[#183](https://github.com/steiner385/fridgesheet/issues/183); not touched here.

## 3. After the alignment

Same script, same seed, same viewports. Phone is 390×844 with touch.

| page | first content, phone (px down) | blank right, 1920 | blank right, 2560 | head pattern |
|---|---|---|---|---|
| Today | 210 → **117** | 32.5 % → **6.5 %** | 49.4 % → **29.8 %** | eyebrow + h2 → page head |
| Assignments (older) | 214 → 117 | same | same | h2 → page head |
| Assignments (early) | 234 → 117 | same | same | h2 → page head |
| Check-in | 156 → 117 | 6.5 % → 6.5 % | 29.8 % → 29.8 % | eyebrow + h2 + actions → page head |
| Plan | 156 → 117 | 32.5 → 6.5 | 49.4 → 29.8 | same |
| Step form | 156 → 117 | 32.5 → 6.5 | 49.4 → 29.8 | back link + h2 → crumb in the head |
| Class | 156 → 117 | 32.5 → 6.5 | 49.4 → 29.8 | back link + h2 → crumb + subtitle |
| Open work | 210 → 117 | 32.5 → 6.5 | 49.4 → 29.8 | h2 → page head |
| Questions | 210 → 117 | 32.5 → 6.5 | 49.4 → 29.8 | h2 → page head |
| Reports | 210 → 117 | 32.5 → 6.5 | 49.4 → 29.8 | h2 + badge → head with action |
| Report builder | 210 → 117 | 32.5 → 6.5 | 49.4 → 29.8 | h2 → crumb + head |
| Report view (print) | 12 → 12 | 32.5 → 32.5 (720 px print column) | | print-controls → head, hidden on paper |
| Plan print | 12 → 12 | same | | print-controls → head, printed as the title |
| Schedules | 210 → 117 | 32.5 → 6.5 | 49.4 → 29.8 | h2 → page head (intro left for #180) |
| Changes | 210 → 117 | 32.5 → 6.5 | 49.4 → 29.8 | h2 → page head |
| Trends | 210 → 117 | 32.5 → 6.5 | 49.4 → 29.8 | h2 → page head |
| Runs | 210 → 117 | 32.5 → 6.5 | 49.4 → 29.8 | h2 → page head; table wrapped |
| Settings | 249 → 148¹ | 32.5 → 6.5 | 49.4 → 29.8 | h2 → page head; notices |
| Diagnostics | 249 → 117 | 32.5 → 6.5 | 49.4 → 29.8 | h2 + button → head with action |
| Not found | 249 → 117 | 32.5 → 6.5 | 49.4 → 29.8 | h2 → page head |

¹ Settings measured with an update badge in the bar, which wraps it to two lines on a
phone; the badge is one of the items that must show at every width.

Other numbers, before → after:

| measure | before | after |
|---|---|---|
| status bar height, phone / tablet sideways / laptop | 67 / 71 / 32 px | 28 / 32 / 32 px |
| check-in columns at 844×390 | 350 + 250 px | one column |
| check-in columns at 1024×768 | 460 + 330 px | one column |
| report view table at 390 px | cut at the card's edge | scrolls in its box |
| Open work date column at 1600 px | 350 px | 128 px |
| heading patterns across the pages | 6 | 1 |
| checkbox under a coarse pointer | 22 px | 24 px |
| pages with a table outside `.table-wrap` | 7 templates | 0 |

What did not change, on purpose: every row and every action on every page (the parity
rule); the tier palettes and type tokens (Sam's pages still render at 20 px); the printed
PDF sheet; the Schedules controls (PR #180 is rewriting that page — only its heading moved
into the page head); the 720 px print column on the two print pages.

## 4. Follow-ups, as issues

What the audit measured but this alignment did not take on, each filed so it is not lost:

| issue | what |
|---|---|
| [#183](https://github.com/steiner385/fridgesheet/issues/183) | A class's page lists every row twice (L12; a route bug, not layout) |
| [#185](https://github.com/steiner385/fridgesheet/issues/185) | Schedules: one intro sentence, notices, forms to the measure — after #180 lands |
| [#186](https://github.com/steiner385/fridgesheet/issues/186) | Settings is 5.1 screens on a phone: fold About and the late-rules editor |
| [#187](https://github.com/steiner385/fridgesheet/issues/187) | Runs (472 px) and Changes (421 px) still ask a 390 px phone for a sideways swipe |
| [#189](https://github.com/steiner385/fridgesheet/issues/189) | Check-in on a phone: the plan is five screens below the queue (6.7 screens; 11.5 sideways) |
| [#190](https://github.com/steiner385/fridgesheet/issues/190) | Check-in opens with three instruction sentences (tab hint, sources hint, intro) |
| [#191](https://github.com/steiner385/fridgesheet/issues/191) | Card titles and Open work's kid sections are `<h2>`, the page title's level |
| [#192](https://github.com/steiner385/fridgesheet/issues/192) | Three filter patterns (chips, radios and selects, inline selects); a chip's current state is unstyled |
| [#193](https://github.com/steiner385/fridgesheet/issues/193) | Reports: six controls per saved-report row, three lines of buttons on a phone |
| [#194](https://github.com/steiner385/fridgesheet/issues/194) | Report builder is the one form still laid out inline |
| [#195](https://github.com/steiner385/fridgesheet/issues/195) | The update badge wraps the phone's status bar back to two lines (28 → 59 px) |
| [#196](https://github.com/steiner385/fridgesheet/issues/196) | A phone held sideways gives 31 % of its height to the strip and the bar |
| [#197](https://github.com/steiner385/fridgesheet/issues/197) | Decision recorded: 30 % blank at 2560 px behind the 1600 px ceiling |

## 5. What holds it

`tests/test_web_page_layout.py` (24 tests): the tokens, the one ceiling, the measure on
prose and forms, the page head on every page template with the title before any other
`<h2>`, the rail label as the page title on every parent page, the child's name and tabs
on the three child pages, crumbs and subtitles on sub-pages, actions in the head, notices
rather than bare coloured lines, every `table.items` in a `.table-wrap`, the pinned date
column, the 1023 px strip block with its fade, the 1279 px blocks (and that the check-in's
stacking rule sits *after* the two-column rule it overrides — the first draft had it
before, and Chromium drew two columns on a 390 px phone), the quiet status items, the
24 px boxes, and the print pages' head. `test_ui_audit_batch_b.py` and
`test_web_trends_page.py` were updated for the moved breakpoint and the rail token.

To re-measure: seed and start as in section 1, then
`env -u PYTHONPATH .venv/bin/python scripts/layout_audit_measure.py` (set
`VIEWPORTS=phone,desktop` to run fewer).
