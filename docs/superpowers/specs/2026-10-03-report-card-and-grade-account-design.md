# The report card, and the account of a class average

Date: 2026-10-03. Status: design approved in discussion ("go with your recommendations");
awaiting review of this document. Asked for by the maintainer: *"I want fridgesheet to have a
report card view. and I want it to have a better understanding of the current class average and
how it is calculated. our next suite of capabilities will be offering guidance to kids/families
on understanding the grade and what opportunities there are to improve the grade."*

This design does two things. It gives every kid a **Report card** page that reads like the paper
one, every class on one line with its official average and a letter. And it gives the app an
**account** of each average: the category subtotals the gradebook shows, what they add up to,
and whether that matches the number the gradebook reports. The account is the foundation the
next suite (guidance: what would move the number, and by how much) stands on, so its data is
stored, not recomputed from the snapshot, and its arithmetic lives in one pure module both the
web app and the MCP server call.

## 1. What the data says

Checked on 2026-10-03 against the household's live snapshot (three kids, seventeen HAC classes,
nineteen Canvas courses), before any design was fixed.

- **HAC's marking-period average is straight total points.** For every class where HAC shows
  category subtotal rows, the average equals total points earned over total points possible
  across every category, to the hundredth: thirteen of thirteen. Two classes (Honors Algebra
  II, Concert Band) look weighted when the average is rebuilt from the assignment rows alone;
  the gap is HAC counting blank-scored rows as zero inside its subtotals (25 points of blank
  work in Algebra II). One class (Honors Biology) has a category (Final Exam, 12 of 12) with
  rows but no subtotal row; adding those rows to the subtotals makes it match exactly.
- **Four classes show no category subtotal rows at all** (two math classes, two language arts
  classes), though every row carries a category. Two of them rebuild from their rows to a number
  HAC does not report (Math Plus 5th: 90.24 rebuilt, 86.57 reported; Adv Math 7: 92.51 reported,
  96.45 rebuilt, with one "I - Incomplete" row). Either HAC weights those classes, or it counts
  rows the scraper does not see. The app cannot tell, and must say so rather than invent.
- **Canvas uses no group weights anywhere** (every `group_weight` is 0.0). Its `current_score` is
  computed over graded work only and its `final_score` counts unsubmitted work as zero. The
  two differ by up to 84 points in this household (Soc Std 5th: 100 current, 15.97 final). Seven
  of nineteen Canvas courses hide the grade entirely.
- **None of this is stored.** `hac.classwork()` scrapes the category subtotals and each row's
  category; `canvas.assignments()` fetches each assignment's group. Ingest keeps only the
  headline averages (`grade_observations`) and reduces category to a boolean `is_assessment`.
  The MCP server's `grades()` tool is the only code that exposes `hac_categories`, straight
  from the snapshot.
- **A letter is almost never given.** HAC shows none. Canvas's `current_grade` is set for one
  of nineteen courses.

## 2. Decisions taken in discussion

1. **Shape.** A Report card page per kid, every class one line with its official average, a
   letter and a one-line "how"; and a "How it's figured" section on each class's existing page
   holding the category table and the check against the reported number. Not chosen: breakdowns
   inline on the report card as folds (the class's page is already the class's record), or the
   class-page section alone (no page reads like the report card).
2. **Audience.** The kid's page too: a fourth tab beside Plan, Assignments and Check-in, with
   its copy in all three reading tiers. Same rows in every tier (`test_web_tier_parity`).
3. **Letters.** A configurable scale in `config.toml`, defaulting to the ten-point scale
   without plus or minus: A at 90, B at 80, C at 70, D at 60, F below. Canvas's own letter,
   when it has one, still shows in the grade strip as today; the report card's letter is the
   scale's, so every class's letter is on the same footing.

## 3. Terms

- **Reported average**: the number the gradebook shows. HAC's marking-period average; Canvas's
  current score (graded work only) and final score (unsubmitted as zero).
- **Official**: the reported average from the source the family chose for class averages
  (`sources.py`; HAC unless changed), falling back to the other source when that one has none.
  Unchanged by this design.
- **Subtotal**: one of HAC's category rows: category, points earned, points possible, percent.
- **Rebuilt average**: 100 × total earned ÷ total possible across the account's lines.
- **Account**: everything the app can say about how a reported average was arrived at: its
  lines, its total, the rebuilt average, the check, and what the gap (if any) is made of.
- **Share**: a category's possible points as a fraction of all possible points. In a
  straight-points class this *is* the category's weight, and it is what the next suite will
  use to say what a row is worth.

## 4. The account: `fridgesheet/grading.py`

A new pure module with no database and no HTTP. Both `web/stores/grades.py` and `server.py`
call it, so the browser and Claude read the same arithmetic.

```python
@dataclass(frozen=True)
class Line:
    category: str
    earned: float
    possible: float
    rows: int                 # scored rows seen in this category (0 when only the subtotal is known)
    from_rows: bool           # True when HAC gave no subtotal and this was summed from the rows
    @property percent -> float | None      # 100 * earned / possible, None when possible is 0
    @property share(total_possible) -> float

@dataclass(frozen=True)
class Account:
    source: str               # "hac" | "canvas"
    reported: float | None    # HAC average, or Canvas current
    lines: tuple[Line, ...]   # category order as the gradebook lists them, from_rows lines last
    earned: float
    possible: float
    rebuilt: float | None     # None when possible is 0
    basis: str                # "subtotals" | "rows" | "none"
    match: str                # "exact" | "off" | "unknown"
    zero_points: float        # HAC: points of unscored work counted as zero inside the subtotals
    excused: int              # rows the gradebook excused (never count)
    final: float | None       # Canvas final_score; None for HAC
    hidden: bool              # Canvas hides this grade
    missing: int              # Canvas rows marked missing (what final counts as zero)
```

**`account_hac(reported, subtotals, rows) -> Account`.**
- `subtotals` are HAC's category rows as scraped. `rows` are the class's HAC assignment rows:
  `(category, score, points, excused)`.
- Lines are the subtotals, in HAC's order. A category that has scored rows but no subtotal
  row gets a line summed from its rows with `from_rows=True` (the Biology Final Exam case).
- `basis` is `"subtotals"` when HAC gave any subtotal row; `"rows"` when it gave none and
  every line is summed from scored rows; `"none"` when there is nothing to sum.
- `zero_points` is summed per category in the subtotals basis: for each category with a
  subtotal, the smaller of (subtotal possible − Σ points of its scored rows, floored at 0) and
  (Σ points of its unscored, unexcused rows). The first is how much of HAC's denominator the
  scored rows do not explain; the second caps it at the blank work that could explain it, so a
  category whose rows the scraper did not see cannot be read as blank work counted at zero. It
  is 0 in the rows basis, where the app cannot know.
- `match` is `"exact"` when `|rebuilt − reported| ≤ 0.011` (HAC prints two decimals, and a
  rebuild from two-decimal subtotals drifts by at most a hundredth); `"unknown"` when either
  number is None; `"off"` otherwise.

**`account_canvas(current, final, hidden, rows) -> Account`.**
- `rows` are the course's Canvas assignments: `(group, score, points, excused, missing, state)`.
- Lines are one per assignment group, summed from graded rows. `reported` is `current`,
  `final` is carried, `basis` is `"rows"`. `match` compares the rebuild to `current` the same
  way; Canvas's own rounding is to two decimals as well.
- `hidden` is as the collector reports it.

**`GradeScale`.**

```python
@dataclass(frozen=True)
class GradeScale:
    cuts: tuple[tuple[str, float], ...]     # (letter, floor), highest floor first
    def letter(self, value: float | None) -> str   # "" for None; the lowest letter ("F") below every floor
TEN_POINT = GradeScale((("A", 90), ("B", 80), ("C", 70), ("D", 60)), below="F")
def scale_from_doc(doc: dict) -> GradeScale
```

`scale_from_doc` reads `[grading] scale`, a table of letter to floor, e.g.
`scale = { A = 90, B = 80, C = 70, D = 60 }`, with an optional `below = "F"`. Any other shape
warns and keeps `TEN_POINT`, the way a bad `[sources]` value does. Letters sort by floor, so
plus and minus grades (`"A-" = 90, "B+" = 87`) work without special cases.

The module carries a docstring stating the finding in §1 and that it is a finding about one
district, not a rule: the account always *checks* the straight-points rebuild against the
reported number and never asserts it.

## 5. Storage: schema version 10

Two additions, one migration, no backfill (the first refresh after the upgrade fills both).

```sql
-- HAC's category subtotal rows for one class, as the gradebook showed them at a refresh:
-- what the marking-period average is built from. A set is written only when it differs from
-- the class's latest set, the way grade_observations is written only when the number moves,
-- so the table is the history of the breakdown and the latest set per course is its state.
CREATE TABLE category_observations (
    id INTEGER PRIMARY KEY,
    refresh_id INTEGER NOT NULL REFERENCES refreshes(id),
    course_id INTEGER NOT NULL REFERENCES courses(id),
    category TEXT NOT NULL,
    earned REAL,
    possible REAL,
    percent TEXT,                    -- as printed ("91.354%"), for the diagnostics page
    UNIQUE (refresh_id, course_id, category)
);
CREATE INDEX category_observations_course ON category_observations(course_id, refresh_id);
-- Which category (HAC) or assignment group (Canvas) each gradebook files an item under. One
-- row per item and source, overwritten each refresh: the name is a label, not a history, and
-- a Canvas item and its HAC twin are filed under different names by the two gradebooks.
CREATE TABLE item_categories (
    item_id INTEGER NOT NULL REFERENCES items(id),
    source TEXT NOT NULL CHECK (source IN ('canvas', 'hac')),
    category TEXT NOT NULL,
    PRIMARY KEY (item_id, source)
);
```

Why not a `category` column on `item_observations`: `_observe` writes a row when any observed
field changes, so adding a field means every row rewrites on the first refresh after the
upgrade (the `_hac_values` comment records the same trap for `excused`), and Changes would
read the rewrite as the school moving. A separate label table has no history to disturb.

Why not on `items`: an item has two sources with two names for its category, and the HAC name
is the one the HAC average is built from.

**Ingest** (`web/ingest.py`):
- `_observe_categories(conn, refresh_id, course_id, subtotals)`: load the course's latest set
  (rows at its max `refresh_id`); if the new set of `(category, earned, possible)` differs,
  insert the new rows under this refresh. Called once per HAC class with `h["categories"]`.
- `_file_category(conn, item_id, source, category)`: `INSERT OR REPLACE` into
  `item_categories`. Called for every Canvas assignment with a group, and for every HAC row
  (twin or HAC-only) with a category. An empty category writes nothing.
- `IngestResult` gains `n_categories` (subtotal rows written), shown in the refresh log line
  beside the other counts.

The `_fold_item` migration helper moves `item_categories` rows along with observations and
flags, so a future re-key does not strand them.

## 6. Reading it: `web/stores/grades.py`

A new store beside `students.py`; `students.latest_grades`, `grade_history` and `grade_lines`
stay where they are.

```python
def latest_subtotals(conn, course_id) -> list[sqlite3.Row]        # the latest set, in insertion order
def subtotal_history(conn, course_id) -> list[list[sqlite3.Row]]  # every set, oldest first (for the next suite)
def account_for(conn, course, grade_row) -> grading.Account
    # HAC course: latest_subtotals + the course's HAC rows (latest hac observation per item,
    # with items.points and item_categories.category) -> grading.account_hac
    # Canvas course: latest canvas observations with group -> grading.account_canvas
def report_card(conn, student, prefs, scale) -> list[ReportLine]
```

```python
@dataclass(frozen=True)
class ReportLine:
    course_id: int            # the page to link: the Canvas course when paired, else the lone course
    short_name: str
    name: str
    official: float | None
    official_source: str      # "hac" | "canvas" | ""
    letter: str
    as_of: str                # HAC's last_updated without the year, or the refresh date for Canvas
    account: Account | None   # the official source's account
    other: Account | None     # the other source's account, when it has a number
    how: tuple[str, dict]     # the phrasing key and values for the one-line "how" (§8)
```

`report_card` pairs courses the way `students.course_options` does (a Canvas course and its
HAC peer are one class), picks the official source with `prefs.resolve(...)` and `pick_value`,
and sorts by `short_name` as the sheet does. A class with no number from either source is
still a line (`official=None`, `how=("rc.no_grade", {})`): the report card hides nothing.

The "how" key is chosen from the official account in this order:

| Condition | Key | Values |
|---|---|---|
| no account, or `reported is None` | `rc.no_grade` | |
| canvas, `hidden` | `rc.canvas_hidden` | |
| canvas, `final` set and `final < reported` | `rc.canvas_partial` | `current`, `final`, `missing` |
| hac, `basis == "subtotals"`, `match == "exact"`, `zero_points > 0` | `rc.adds_up_zeros` | `earned`, `possible`, `zero_points` |
| `match == "exact"` | `rc.adds_up` | `earned`, `possible` |
| hac, `basis == "rows"`, `match == "off"` | `rc.rows_dont_add_up` | `rebuilt`, `reported`, `rows` |
| `match == "off"` | `rc.dont_add_up` | `rebuilt`, `reported` |

Numbers in the values are formatted before they reach the phrase (`fmt_points`: an integer when
whole, else two decimals; `fmt_avg`: two decimals), because `test_phrasing` forbids a phrase
inventing a number and the parity tests want identical rows across tiers.

## 7. The pages

### 7.1 The Report card page: `GET /kids/{key}/report-card`

New router `web/routes/report_card.py`, registered in the `app.py` tuple. Renders
`report_card.html` with `current="kid:<key>"`, `workspace="report"`, the kid's tier, and
`lines = grades.report_card(...)`.

Page head: crumb back to the kid, `page_title = "Report card"` (the rail link's exact words,
`test_a_page_title_is_the_rail_label`), subtitle the kid's nickname and "marking period so
far", `page_actions` holding one `data-print` button ("Print") as the report view does. The
intro is one tiered sentence (`copy.rc_intro`: the official source's name and that the number
is the marking period so far).

Body, the planner's vocabulary (DESIGN.md, The Student Planner): `.planner-main.report-card-page`
(not `.report-page`, which is the print pages' class) holding one `section.sec.report-lines` with a `.sec-head` (`h3` "Classes", `.count` "7
classes") and an `ol.report-lines`, one `li.report-line` per class:

```
┌ li.report-line ──────────────────────────────────────────────────────────────┐
│ Honors Algebra II                                        70.88  C            │  .class (link) · .avg .big · .letter
│ HAC average · as of 10/1                                                     │  .whose (pencil)
│ Adds up: 368.91 of 520.5 points. 25 points of unscored work count as zero.   │  .how (tiered)
└──────────────────────────────────────────────────────────────────────────────┘
```

Each line sits under a hairline like the Changes log's rows; the class name links to its page;
the number is Display size in ink with the letter beside it at body weight. A class with no
number shows "—" and `rc.no_grade`. Below the list, one quiet fold `details.sec.quiet.how-figured`
("How averages are figured") holding two tiered paragraphs: `copy.rc_how_hac` (total points,
blanks count as zero once the teacher enters them, excused never count) and `copy.rc_how_canvas`
(graded work only; the final if missing work stays missing; some teachers hide it). The fold is
the only prose on the page.

The page prints: `@media print` already hides the rail and the page actions; the lines and the
fold's text print as they stand. No new print stylesheet.

**Navigation.** Kid mode (`base.html`, `nav.kid`): a fourth top-level tab "Report card" after
Assignments and before the More fold, `current` when `workspace == 'report'`. The grown-up
shell (`_child_nav.html`): a fourth tab after Assignments, `aria-current` on `report`. The
report card also lists in `_child_nav`'s order on every kid page, so a parent on a class page
is one tap from it.

### 7.2 The class page: "How it's figured"

In `course.html`, after `section.sec.grade-record` and before the "How it moved" fold, one
`section.sec.grade-account` with a `.sec-head` (`h3` "How it's figured", `.count` "5
categories"). The route (`routes/kid.py::course`) adds `account` (this course's own) and
`other_account` (the twin's) to the context, plus `scale`.

Body, for the official source first and the other beneath under an `h4` naming the gradebook:

```
┌ section.sec.grade-account ──────────────────────────────────────────────────────┐
│ How it's figured                                                   5 categories  │
│ HAC's marking-period average is total points: everything earned over everything  │  .lead (tiered)
│ possible, across all categories.                                                 │
│ ┌ div.table-wrap > table.categories ──────────────────────────────────────────┐ │
│ │ Category        Earned   Possible   Percent   Share of the grade            │ │
│ │ Assignments        9.5       12.0    79.17%        3%                        │ │
│ │ Daily             88.5      100.0    88.50%       29%                        │ │
│ │ …                                                                           │ │
│ │ Final Exam        12.0       12.0   100.00%        3%   (from the rows)      │ │  .from-rows pencil note
│ │ Total            278.53     349.0    79.81%                                  │ │  tfoot
│ └─────────────────────────────────────────────────────────────────────────────┘ │
│ ✓ Adds up. HAC says 79.81.                                                       │  p.check (tiered; .warn when off)
│ 6 unscored rows: 0 points counted as zero yet. 3 excused rows never count.        │  p.check-detail (pencil)
│ Canvas                                                                           │  h4
│ Canvas current 68.8 counts graded work only; 51.1 if the 4 missing rows stay at  │  p.check (tiered)
│ zero. Canvas hides the letter.                                                   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

- `table.categories` is a plain table in `.table-wrap` (the layout test's rule is for
  `table.items`; this is not an items table). Columns right-aligned for numbers; the Share
  column is the line's `share` as a whole-number percent. Share is the column the next suite
  will point at ("a 25-point zero in a 520-point class costs 4.8 points").
- A `from_rows` line carries a pencil note "from the rows" and the table's `.lead` says, when
  any exists, that HAC's own table leaves that category out.
- `p.check` reads `rc.adds_up` / `rc.adds_up_zeros` / `rc.dont_add_up` / `rc.rows_dont_add_up`
  with a ✓ or, when off, Red Pen text (the one colour that means "the school's record and
  what we see disagree"). In the rows basis the lead says HAC showed no category table for
  this class and the table is summed from its rows.
- The Canvas part is one or two sentences, no table, unless Canvas is the official source, in
  which case the table is Canvas's groups and HAC's part is the sentence. A hidden Canvas grade
  is one sentence. A class only one source knows shows one part.
- With no numbers at all from either source the section is one sentence ("No grade yet from
  either gradebook.") and no table.

### 7.3 Diagnostics

The Diagnostics page gains one planner line per kid in its checks: "Averages add up: 15 of 17
classes" with the Runs word, listing the classes that are `off` or `rows`. This is where a
scraper regression (a category table that stops parsing) shows up first.

## 8. Phrasing

New `copy.*` and `rc.*` keys in `phrasing.PHRASES`, all three tiers, placeholders identical
across tiers, no digits in any phrase (`test_phrasing`). The "how" line keys from §6:

| Key | older |
|---|---|
| `rc.no_grade` | "No average yet." |
| `rc.canvas_hidden` | "Canvas hides this class's grade." |
| `rc.canvas_partial` | "Canvas counts graded work only: {current} now, {final} if the {missing} missing stay at zero." |
| `rc.adds_up` | "Adds up: {earned} of {possible} points." |
| `rc.adds_up_zeros` | "Adds up: {earned} of {possible} points. {zero_points} points of unscored work count as zero." |
| `rc.rows_dont_add_up` | "HAC says {reported}; the {rows} scored rows we can see add up to {rebuilt}. HAC may weight categories or count work we cannot see." |
| `rc.dont_add_up` | "The categories add up to {rebuilt}; HAC says {reported}." |

Early tier for the same ideas: "Your points: {earned} out of {possible}." / "HAC says {reported}.
The work we can see adds up to {rebuilt}. Ask your teacher how it is figured." The middle tier
sits between. Page copy: `copy.rc_intro`, `copy.rc_how_hac`, `copy.rc_how_canvas`,
`copy.rc_lead_hac`, `copy.rc_lead_hac_rows`, `copy.rc_lead_canvas`, `copy.rc_excused`
("{excused} excused rows never count"), `copy.rc_unscored` ("{n} unscored rows: {zero_points}
points counted as zero so far").

## 9. Configuration

`[grading]` in `config.toml`, read in `settings_from_doc` into `Settings.grading: GradeScale`
(default `TEN_POINT`), with the same tolerance for bad shapes as `[sources]`:

```toml
[grading]
scale = { A = 90, B = 80, C = 70, D = 60 }   # the floor of each letter; below the lowest is F
below = "F"
```

Not on the Settings page in this design (§13). Documented in the user guide beside Gradebook
sources.

## 10. The MCP server

`grades()` gains `"account"` per class: `dataclasses.asdict(grading.account_hac(...))` built
from the snapshot's `marking_period_avg`, `categories` and `assignments`, and
`"canvas_account"` likewise. `hac_categories` stays for compatibility. The docstring says what
`match` means so Claude does not assert a rebuild that is `off`.

## 11. Tests

- `tests/test_grading.py`: the §1 findings as fixtures. Algebra II (subtotals exact with 25
  zero points), Biology (a from_rows line makes it exact), Math Plus 5th (rows basis, off),
  an excused row, an empty class (basis none, match unknown), Canvas with final below current
  and with hidden; `GradeScale.letter` at every floor, on None, with a plus/minus scale from
  a doc, and a malformed `[grading]` keeping the default.
- `tests/test_web_db.py` / migration: a v9 file migrates to 10 and both tables exist; a v10
  file refuses an older build (existing test extended).
- `tests/test_web_ingest.py`: subtotals written once, not rewritten when unchanged, rewritten
  when one changes; `item_categories` filled for a Canvas item, its HAC twin (two rows, two
  names) and a HAC-only item; `_fold_item` carries the rows.
- `tests/test_web_report_card.py`: the page renders one line per class with the official
  number and letter; a paired class is one line linking the Canvas page; a class with no
  number is a line; the "how" key chosen per the §6 table; the rail tab and the child nav
  tab, with "Report card" as both label and title; prints without the rail.
- `tests/test_web_class_page.py` extended: the "How it's figured" section with the table,
  from_rows note, check line, Canvas sentence; the rows-basis lead; the one-sentence empty
  state; no retired classes (`test_web_section_and_card`).
- `tests/test_web_tier_parity.py`: `/kids/Alex/report-card` added to the parametrised paths;
  one row id per class in every tier.
- `tests/test_phrasing.py` covers the new keys by construction.
- `tests/test_server_tools.py`: `grades()` carries `account.match` for a fixture class.
- `tests/web_fixtures.py`: Alex's English gains two HAC subtotal rows and an excused row;
  Alex's Algebra gains none (the rows basis); Sam's Science gains a Canvas final below
  current. The snapshot fixture is shared, so the extensions are additive and existing
  assertions are checked, not rewritten.

## 12. Documentation

- `DESIGN.md`: Trends's nickname "the report card page" becomes "the year so far page"
  (its own words); a new "The report card" paragraph after the build, recording the lines and
  the account section the way the other surfaces are recorded; the frontmatter untouched.
- `.impeccable/surfaces/fridgesheet-web-templates-report_card-html.md`: a surface brief in the
  existing form. The world is settled; the brief records composition. The class page's brief
  gains the new section under Scope.
- `docs/user-guide.md`: a "Report card" section after Trends, and `[grading]` under Settings.
- `docs/product/features/report-card.md`, and a line in `canvas-hac-ingestion.md` for the two
  tables.
- `docs/outcomes.md` §"HAC is the gradebook of record": one sentence that the app now checks
  HAC's number against its own subtotals and says when it cannot.

## 13. Not in this design

- **Guidance.** What would move the number, by how much, which rows are worth the most, what
  a retake or a late hand-in would do. The next suite; this design stores and exposes `share`,
  `zero_points`, `missing` and `final` so it can be built without another schema change.
- **Category weights entered by the family.** No class checked needs them. If the two
  unexplained math classes turn out to be weighted, a `[[grading.weights]]` rule is the
  natural shape; the account's `match == "off"` is how the household will find out.
- **The scraper.** Why four classes show no subtotal rows (and Biology's Final Exam row is
  missing) needs the page's HTML; `hac.classwork()` is unchanged here. Follow-up with a saved
  Classwork page as evidence. The account's `basis` makes the gap visible meanwhile.
- **Past marking periods.** HAC shows the current one; so does the report card.
- **A Settings field for the scale**, and a Trends chart of category subtotals over time.

## 14. Order of work

1. `grading.py` with its tests (pure; TDD).
2. Schema v10, ingest, fixtures, migration tests.
3. `stores/grades.py` with `account_for` and `report_card`, tested through the stores.
4. Config `[grading]` and `Settings.grading`.
5. The class page section, its copy, its tests.
6. The report card page, the two navigations, parity, print.
7. The MCP `grades()` field; Diagnostics line.
8. Docs and DESIGN.md; the surface brief; the full suite (`test_rebrand` scans new files).

One branch, one PR: the report card without the account is a list of numbers the app already
shows, and the account without the page has nowhere to be read.

## 15. Risks

- **The straight-points finding is one district's.** The design never asserts it; it checks
  and reports. A household whose HAC weights categories sees `off` on every class and the
  honest sentence, which is the cue for the weights follow-up.
- **HAC's table can change shape.** The `basis` field and the Diagnostics line make a parsing
  regression visible as "rows" rather than silent.
- **Rounding.** The match tolerance is a hundredth plus a thousandth. If HAC ever prints one
  decimal, every class reads `off`; the tolerance is one constant in `grading.py`.
- **Page count on the kid's rail.** A fourth tab narrows the others on a phone; the rail's
  tabs already wrap to one ruled row there. Checked in the build with the phone viewport.
