# Product

<!-- impeccable:product-schema 1 -->

Durable product truth for Fridge Sheet, read by the Impeccable design skill before any UI
work. It records who the product is for and what must be preserved; it does not describe the
visual system (that is DESIGN.md's job, when one exists) and it never overrides
`docs/outcomes.md`, which is the one rule table every count on every surface derives from.
The three answers marked *(maintainer, 2026-09-29)* were given in the init interview; every
other line is evidenced in the repository.

## Platform

web

## Users

**Primary: one household, the maintainer's own, first.** *(maintainer, 2026-09-29: "your
household first, others welcome")*. Three children in Lakota Local Schools (Ohio), parents and
caregivers on a Windows PC in the house and on phones over the home network. Other households
are welcome and the README supports any district that runs Canvas and Home Access Center behind
OneLogin, but nothing is built to recruit or onboard strangers; setup assumes a parent who can
follow `docs/user-guide.md`.

The situations the product is used in, in order of how often they happen:

1. **The sheet on the fridge.** Read standing up, by anyone in the house, every school day. It is
   printed on a schedule with nobody at the computer.
2. **A parent's nightly phone check** (about five minutes): what is still fixable tonight, and the
   few Questions only a parent can answer.
3. **A short weekly parent–child check-in** at the computer that ends with a plan both own, then
   the child's Plan page during the week (the child's own device opens on it in kid mode).
4. **A second caregiver** who uses it occasionally and needs to know whose words they are reading
   (steps and agreements carry a free-text "recorded by"; there are no accounts or logins).
5. **The maintainer as operator**: Settings, Schedules, Diagnostics, the command line, and the
   same data in Claude Desktop through the MCP server.

**Children are users too.** Every child sees every row and every action; a child's grade
(`[kids].grades` in `config.toml`) selects a reading tier that changes type size, density,
colour tokens and vocabulary only: **early** (K–5), **middle** (6–8), **older** (9–12), and an
unset tier that renders exactly what shipped before tiers existed.

## Product Purpose

Fridge Sheet signs in to OneLogin with the parent's login, reads every child's work from Canvas
(where teachers post and collect work) and Home Access Center (HAC, the official gradebook),
pairs each assignment across the two, and gives every assignment one **outcome** from one
written rule table (`docs/outcomes.md`). It then keeps the short list of what can still be fixed
in front of the family: printed on the fridge, on the web app, and in Claude.

Success is a correct, readable sheet on the fridge every school day without anyone touching the
computer, and a check-in that ends with a plan. The named failure (persona review, 2026-09-25) is
*no sheet on day 2*: a household that installed it and never got a second sheet.

## Positioning

- **One definition of done, everywhere.** Canvas's *missing* is a flag, not a fact; "past due and
  unsubmitted" is not what a parent means by missed either. Fridge Sheet reads both gradebooks
  and one table decides: a teacher's 0 is *not done*; paper work with a grade is *done on paper*;
  a HAC grade beats Canvas's automatic missing flag. Today, each child's pages, Trends, the
  printed sheet and the MCP tools all show the same numbers, and the code is wrong if the docs
  and the code ever disagree.
- **It asks only what the family can act on.** A *verdict* on top of the outcome **decides** what
  the records settle, **waits** on what time will settle, and **asks** only when a parent or
  child can do something (a HAC zero on work handed in online; HAC lower than Canvas; a grade
  missing longer than that class usually takes). Too late for credit is a status, not a question.
- **Nothing leaves the house.** Runs on the family's own computer; talks only to OneLogin, Canvas
  and HAC, plus a once-a-day GitHub check for a newer version that sends nothing and can be
  turned off. The password lives in the OS credential store, and Claude never sees it.
- **It remembers the family's side.** Answers ("handed in on paper"), notes, flags, check-in
  agreements and plan steps survive every refresh; a refresh never overwrites them.

## Operating Context

- **Machines.** A Windows PC via a signed-less installer (about 900 MB with its own Chromium; a
  logon task keeps the server up); Linux with a systemd user unit; a headless Linux server for
  the technical parent. The server listens on port 8433, reachable by address on the home network
  from phones and tablets; a hostname needs `[web] extra_hosts`.
- **The printed sheet.** One section per child, on the school days and at the time the family
  chose, honouring no-print days and quarter ends. Built as a PDF by `fridgesheet/sheet.py`
  (reportlab, not HTML or CSS), printed through SumatraPDF on Windows, archived, and reprintable
  from the Runs page. Overdue first, then coming due; a legend; the sheet's own status words
  (MISSING, ZERO, LATE, PAPER — CHECK, IN CLASS — CHECK, HAC — NO GRADE, DUE TODAY / TONIGHT /
  TOMORROW / *day*), tiered by vocabulary only per child section.
- **Refresh.** Signing in and reading both systems takes one to three minutes in a real Chromium;
  the computer must be on and signed in. Schedules run from the app's own clock, once a minute,
  in the configured time zone; a slot missed while the server was down is caught up once. A
  deadline in the first hour of a day belongs to the evening before.
- **Sources and their roles.** Canvas alone knows whether and when something was handed in, late,
  missing or excused, and holds online work; HAC is the gradebook of record (marking-period
  average is the real grade) and lists paper, in-class and participation work Canvas never sees.
  Per-class late-work windows and credit live in `late-rules.toml`; district addresses in `.env`;
  everything else in `config.toml`, which Settings and Schedules edit.
- **Claude.** The same snapshot is served to Claude Desktop as a local MCP server (`grades`,
  `missing_work`, `upcoming`, `assignments`, `hac_classwork`, `list_students`, `status`,
  `refresh`) for weekly check-in reports.

## Capabilities and Constraints

- **Pages.** Today (household dashboard with each child's card and the sheet's controls); per
  child Check-in, Plan and Assignments; Open work; Questions; Reports and the report builder;
  Schedules; Changes; Trends; Runs; Settings; Diagnostics; the print views for the sheet and a
  child's plan; `/who` for kid mode.
- **Stack.** Python 3.11+, FastAPI and Jinja2 templates, htmx and a small vanilla `app.js`,
  Chart.js on Trends, one stylesheet (`fridgesheet/web/static/app.css`), no build step, the
  system font stack. Vendored libraries are listed in `static/VENDOR.md`. Tests run on Ubuntu and
  Windows; the suite asserts page structure, retired class names, tier parity and touch sizes,
  so a design change is also a test change.
- **The parity rule.** A tier never changes which rows or actions a child sees
  (`tests/test_web_tier_parity.py`). Navigation and secondary form fields may fold, identically
  at every tier, as long as everything stays in the page. No child phrase states a time, date or
  number its adult equivalent does not.
- **Voice by page.** Assignments is the child's page and says "you"; Check-in and Plan say "we";
  caregiver-only fields say "(a grown-up helping · optional)". All child-facing copy goes through
  `phrasing.PHRASES` (`copy.*` keys), never raw template prose.
- **Current layout standards** (code standards with tests, not brand commitments): the page
  layout standard (status bar, page head, notices, one content column; `--page-max`,
  `--measure`) and the section-and-card standard (every content block a `.sec`, every assignment
  one five-slot `_item.html` card at line, card and detail densities). They can be replaced, but
  only together with their tests and the feature-map pages under `docs/product/features/`.
- **Touch and colour.** Every button, control, tab and the main link in a row or card is at
  least 44px under a finger; a secondary link inside a row or card (the class under an
  assignment, the counts on the record line) keeps WCAG 2.5.8's 24px floor with padding
  *(maintainer, 2026-09-29, settling the 44-versus-24 question the re-critique raised)*. A
  phone gets one column under the strip breakpoint. Nothing is conveyed by colour alone: what
  is red is red *and* a word.
- **Terminology** (use these words, not synonyms): *outcome* (excused, unpublished, not done,
  late, on time, done on paper, unknown, not due yet); *verdict* (decides, waits, asks);
  *still fixable* (not done or unknown, inside its late-work window, not flagged handled);
  *open*; *Questions*; *Must finish*; *check-in*, *plan*, *step*, *agreement*.
- **Explicitly open product questions** (persona review 2026-09-25, not yet decided; do not
  resolve them inside a design task): one label table for answers (#129); the three overlapping
  names *Open*, *Open work* and *still fixable*; whether four "handled" answers belong on the
  first menu; a per-child reading-level control on Settings instead of `config.toml`.

## Brand Commitments

*(maintainer, 2026-09-29: "name, mark, and the reading-tier system")*

- **The name "Fridge Sheet."** The product was rebranded from a district-specific name so any
  parent could install it (`docs/product/features/product-rebrand-migration.md`); the old command
  name is a shim for one release. Do not reintroduce the district into the product's identity.
- **The mark.** `fridgesheet/web/static/mark.svg`, with `mark-32.png`, `mark-180.png`,
  `mark-192.png`, `mark-512.png` and `favicon.svg`. It is the icon in the rail, the tab and on
  a phone's home screen (the web app manifest names the 192 and 512).
- **The reading-tier system as a mechanism.** One page, three densities and vocabularies, each
  tier redefining every token so no page inherits a colour nobody designed, colour never alone.
  The specific colours and type sizes in each tier are not binding and may change.

Not binding: the current neutral system-font, paper-white palette and type may be replaced by a
later redesign. Voice, evidenced in every shipped string rather than decided here: plain,
concrete, family-facing sentences; the school's record stated as facts; "why" explained in prose.

## Evidence on Hand

- **Real household data**, quoted in `docs/outcomes.md`: on one day Canvas's dashboard said 4
  missing while the gradebooks held 11 not done and 8 unknown; HAC held 36, 16 and 31 assignments
  Canvas did not, per child; on 2026-09-21, 20 of 27 past-due paper assignments were graded in
  Canvas. These are the numbers to reason from; do not invent others.
- **Product research**: the kids' UX audit (`docs/product/2026-09-24-kids-ux-audit.md`), the
  four-persona user-guide review (`docs/product/2026-09-25-user-guide-persona-review.md`: Dana,
  Marcus and Priya, Maya and Leo, Sam; personas, not real people) and the page-layout audit
  (`docs/product/2026-09-26-page-layout-audit.md`). The feature map is
  `docs/product/features/*.md`; the user guide is `docs/user-guide.md` (version 0.5).
- **Approved mockups**: `docs/superpowers/specs/2026-09-27-plan-fills-itself-mockups/` (Today
  and Plan, parent and kid, desktop and phone; `/who`) and
  `docs/superpowers/specs/2026-09-28-sections-and-items-mockups/` (cards, Assignments, Plan).
  Their specs sit beside them.
- **Backlog**: GitHub issues on `steiner385/fridgesheet` (#120–#154 from the persona review;
  #212–#215 follow-ups to the section-and-card standard).
- **Absent, and not to be fabricated**: testimonials, other households' data, district
  partnerships, usage numbers, a marketing site. The public face is the GitHub README and the
  Releases page.

## Product Principles

1. **The sheet is the product; the screens serve it.** *(maintainer, 2026-09-29)* When a design
   choice trades off, the printed sheet's correctness and readability at fridge distance win,
   and the web app's job is to feed it, fix its inputs and show the same list.
2. **One rule table, everywhere.** Every count, colour and word derives from `docs/outcomes.md`.
   A surface that computes its own answer is a bug.
3. **Every child sees every row.** Tiers change presentation and vocabulary, never information or
   actions. A child is never one tap from a sibling's page or Settings, but nothing is hidden
   from them.
4. **Ask only what the family can act on.** Decide what the records settle, wait on what time
   will settle, and put a question in front of a parent only when they can do something about it.
5. **This household's routine first, others welcome.** Fit the fridge, the nightly phone check
   and the weekly check-in before a stranger's first run; make the general path work without
   letting it dictate the design.

## Accessibility & Inclusion

- **Readers from about age eight to adult** on the same pages: the early tier raises the root size
  to 20px and the secondary sizes with it, so the lines a child is asked to judge are never the
  smallest text on their page; wording is age-tiered through the phrase table.
- **Touch first on phones**: 44px on every button, control, tab and main link; 24px with padding
  on secondary links inside rows and cards; coarse-pointer padding floors in tables.
- **Never colour alone**; live-region announcements (`#announce`, `aria-live="polite"`) for
  htmx swaps; `lang="en"`; screen-reader-only text where the visual carries the meaning.
- **Reading at a distance**: the printed sheet is read standing at a fridge, so it favours large
  status words and short rows over detail.
- No formal standard (such as a WCAG level) has been adopted; the rules above are the product's
  own, held by its tests.
