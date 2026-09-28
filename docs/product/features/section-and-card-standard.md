---
slug: section-and-card-standard
title: Section and Card Standard
state: live
parent: browser-app
links:
  - kind: related
    project: fridgesheet
    feature: page-layout-standard
  - kind: related
    project: fridgesheet
    feature: all-work-table-ux
---

Below the page head, every page is a stack of one section block, and every assignment is one card with five slots, so a parent or a kid reads the same shape on every page and never reads the same fact twice.

## Problem

The page layout standard made the chrome identical and stopped at "sections of cards". Every spec after it invented its own section and its own card: seven box styles and four heading treatments on one page, one assignment drawn three times (a card at the top, a table row, and a card inside a card when the row opened), four lines of prose before the first thing to do, and a second green palette on Check-in and Plan. Inside the cards, six containers drew an assignment in six orders, the head said "in class · due 9/20" and the sentence under it said it again, and the school's record, the app's reading, the family's layer and the actions interleaved with no hierarchy.

## Target users

Everyone who reads a kid's page: the weeknight triager scanning for what needs an answer, the kid on their own plan, the second caregiver who opens a row to see the record.

## Desired outcome

One section: an h3, a count, one lead sentence, the section's own controls at the right; folded and quiet variants draw the same head. One card, five slots owned by one layer each: head (identity, once: name, class, kind, points, the one word about time at the right), says (the app's one sentence), ask (the question and its one-tap answers), ours (our step, our note), foot (Record, History, Notes, Plan a step, More, and the provenance stamp, tiny). Three densities from one partial: a line, a card, and the card opened as a detail with the record open and Close in the head. Emphasis is a left rule and a word: accent needs an answer, red the school says not in, green done, grey nothing to do. One inset for anything quoted. One radius, a named gap scale, the accent on every page. The line under a kid's tabs is state (Done so far; the last check-in), not instruction. The glossary sentence is said once per page, as the table's legend.

## Success metrics

- `tests/test_web_section_and_card.py` holds it: the tokens, the section head, each density's slots in order, the facts sentence never restating the due date, the glossary at most once per page, no retired class in any template or rule, and every radius a token.
- Doug's Assignments tab, which prompted this, draws MakeMusic #4 once as a card, once as a row, and the row opens flat.
- The parity rule still holds: the tier tests and kid mode render the same rows, forms and buttons.

## Non-goals

- Which rows a page shows and which answers a verdict offers (`docs/outcomes.md`, the verdict table).
- The printed PDF sheet and the paper side of the two print pages.
- The status bar's wording.

## Notes

- Designed in `docs/superpowers/specs/2026-09-28-section-and-card-standard-design.md` from rendered mockups (`2026-09-28-sections-and-items-mockups/`); planned in `docs/superpowers/plans/2026-09-28-section-and-card-standard.md`.
- Supersedes the kids' UX audit's F3 tab hint: the section heads and their leads carry the orientation now.

## Evidence

- `fridgesheet/web/templates/_item.html` (the one partial), `_verdict_sections.html`, `kid.html`, `_child_nav.html`, `_must_finish.html`, `_plan_panel.html`, `checkin.html`, `questions.html`, `_record.html`, `_source_facts.html`
- `fridgesheet/web/static/app.css` (`--radius`, `--s1…--s6`, `.sec`, `.item`, `.inset`, `.lines`)
- `tests/test_web_section_and_card.py`
