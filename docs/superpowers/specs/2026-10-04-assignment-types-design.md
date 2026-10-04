# Assignment types: what kind of work each row is, and what that unlocks

Date: 2026-10-04. Status: design approved in discussion, section by section; awaiting review of
this document. Asked for by the maintainer: *"is it possible for fridge sheet to characterize
assignments by type like homework assignment vs test vs lab vs ___? does canvas provide that
capability?"*, then *"there's value in [labels], [advice] and [trends]"*, choosing five of
fourteen brainstormed capabilities for this design: the type on every row (1), a type filter
(2), Must-finish ranked by type and worth (5), where a class's points are (8), and each kid's
average by type over time (10). The other nine are §11.

Canvas has no assignment type. This design infers one from what the app already stores, lets a
grown-up correct it item by item or class by class, and reads it on four surfaces.

## 1. What the data says

Run on 2026-10-04 over the household's live snapshot (`/tmp/type-coverage-probe.log`), with a
throwaway keyword classifier:

| Source | Items | Typed from a signal | By signal |
|---|---|---|---|
| Canvas | 299 | 136 (45%) | assignment group 77, item name 32, `online_quiz` 27 |
| HAC | 296 | 196 (66%) | category 144, item name 52 |

- **The type signals are teacher-named and inconsistent.** Canvas groups seen: `Assignments`
  (179), `Imported Assignments` (19), `Homework Completion`, `Homework`, `Quiz`, `Assessments`,
  `Total Points`, `Homework Graded`, `Playing/Written Work`, `Class Work`, `Final Exam`,
  `Quizzes & Tests`, `Pre-Tests`, `LABS`, `HMWK`, `Performances`. HAC categories add `Daily`,
  `Labs`, `Test`, `Project`, `Participation`, `Concert Attendance`.
- **Generic buckets dominate.** `Assignments`, `Imported Assignments` and `Total Points` say
  nothing; they are what a straight-points class needs and no more.
- **What no signal names is everyday work.** Every unlabelled item sampled was a worksheet,
  notes, questions, a tracker or a journal (`WS #2-4 A`, `Video Notes`, `Evidence Tracker`).
  None was a hidden test: teachers who give tests either file them in a named bucket or name
  them plainly. "Nothing matched" is evidence, not a gap.
- **`submission_types` is format, not purpose**, except `online_quiz`. And `kind_of`
  (`open_items.py`) folds `online_quiz` into `online`, so today the app loses it at ingest.
- **The weights are points.** Spec 2026-10-03 §1: HAC's average is straight total points in
  every class with a category table (13 of 13), and Canvas uses no group weights. A type's
  share of the possible points is its weight in the grade.

## 2. Decisions taken in discussion

1. **Four families, not fine types.** `assessment` (tests, quizzes, anything assessed),
   `practice` (homework, classwork, worksheets, and everything unmatched), `lab_project`,
   `participation` (participation, attendance, performances, concerts). Each is a different
   conversation with a kid and each stays reliable. Not chosen: about nine fine types
   (Homework vs Classwork is a coin flip, and "Other" would be a third of all items); storing
   fine types and showing families.
2. **Corrections per item and per class.** A grown-up can change one item's family, and can
   make that change a class rule in the same step. Not chosen: no correction; per item only.
3. **Rules are made from a correction**, never from a blank form. The class page lists them
   with Remove. Not chosen: a rules editor in Settings; both.
4. **Classify at read time.** A pure function over stored facts; only the corrections, rules
   and one new ingest fact are stored. Improving the keyword list or adding a rule relabels
   every item, past ones included, with no backfill. Not chosen: a family column written at
   ingest (stale on every rule change, needs backfills); a cached column (YAGNI).
5. **Everyday work wears no word.** It is the default and most rows; the meta line already
   leaves `online` unsaid while saying `paper` and `outside Canvas`.
6. **Must-finish ranks within the same deadline** (option B). The deadline stays the first
   sort key; among rows sharing it, the one worth more on the average comes first. This is the
   "later design may add a sort" spec 2026-10-04 (what moves the grade) §11 left open. Not
   chosen: annotate only; a sort toggle.
7. **Trends average per class, then across classes**, equally. Not chosen: pooled points,
   where one class's 500-point tests drown the rest and Simpson's paradox can show a kid
   worse overall while better in every class.

## 3. Terms

- **Family**: one of `FAMILIES = ("assessment", "practice", "lab_project", "participation")`.
- **Facts**: what classifying an item reads: its name, its Canvas group and HAC category
  (`item_categories`, either may be absent), and `items.online_quiz`.
- **Typed**: `family_of`'s answer, `Typed(family, rung, reason)`. `rung` is which step of the
  ladder (§4.2) answered, 1 to 6; `reason` is a `phrasing` key and its values, so the detail
  card can say why.
- **Generic name**: a group or category that names no type: `assignments`,
  `imported assignments`, `total points`, and the empty string. Compared case-folded.
- **Correction**: an `item_types` row. **Rule**: a `type_rules` row.

## 4. The classifier (`fridgesheet/types.py`)

Pure, like `grading.py` and `guidance.py`: no database, no clock.

### 4.1 Keywords

One ordered tuple of `(family, pattern)`, first match wins, matched case-insensitively on word
boundaries. Order matters: "Lab Quiz" is an assessment, "Project Presentation Rubric
Participation" a project.

| Family | Words |
|---|---|
| assessment | test, exam, final, midterm, quiz, quizzes, pre-test, pretest, assessment, assessments, checkpoint, summative |
| lab_project | lab, labs, project, presentation, research, essay |
| participation | participation, attendance, concert, performance, performances, playing, seminar |
| practice | homework, hmwk, hw, classwork, class work, daily, warm-up, bell ringer, exit ticket, worksheet, ws |

`open_items.ASSESSMENT_WORDS` becomes the assessment row; `open_items` and `web.ingest` stop
computing `is_assessment` from it once §6.4 lands.

"Test Corrections", "Test Review" and "Quiz Retake" are deliberately left to the keywords (they
read as assessment); a family that disagrees corrects them once with a name-prefix rule.

### 4.2 The ladder

`family_of(facts, rules, correction) -> Typed`. The first rung that answers wins:

1. **Correction** on this item.
2. **Rule** for the item's class that matches (§5.2).
3. **`online_quiz`** → assessment.
4. **Gradebook name**: the HAC category if it is not generic and matches a keyword, else the
   Canvas group on the same terms. HAC first because it is the official gradebook and the more
   descriptive in §1.
5. **Item name** matches a keyword.
6. **Otherwise** → practice, reason "no type named; read as everyday work".

### 4.3 Coverage

`coverage(typed: list[Typed]) -> dict[int, int]`: count per rung, for Diagnostics (§6.5).

## 5. Storage (schema 12)

### 5.1 Migration

```sql
ALTER TABLE items ADD COLUMN online_quiz INTEGER NOT NULL DEFAULT 0;
CREATE TABLE item_types (
    item_id INTEGER PRIMARY KEY REFERENCES items(id),
    family TEXT NOT NULL CHECK (family IN ('assessment','practice','lab_project','participation')),
    set_at TEXT NOT NULL
);
CREATE TABLE type_rules (
    id INTEGER PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES courses(id),
    field TEXT NOT NULL CHECK (field IN ('group','name_prefix')),
    value TEXT NOT NULL,
    family TEXT NOT NULL CHECK (family IN ('assessment','practice','lab_project','participation')),
    created_at TEXT NOT NULL,
    UNIQUE (course_id, field, value)
);
```

`online_quiz` is set at Canvas ingest from `"online_quiz" in submission_types`, on the `items`
row beside `kind` and `is_assessment` (never on `item_observations`: a new observed field
rewrites every row on the first refresh and Changes reads it as the school moving, the reason
`item_categories` is its own table). Existing rows read 0 until the next refresh, which is one
refresh of rung 3 missing, then self-healing.

The item merge (`db.py`, where `item_categories` is carried) carries `item_types` the same way:
the surviving item keeps its own correction if it has one, else takes the merged item's.

### 5.2 Rule matching

`value` is stored case-folded and stripped. A `group` rule matches when either gradebook's name
for the item equals it. A `name_prefix` rule matches when the case-folded item name starts with
it. When several rules match: a `group` rule beats a `name_prefix` rule; among prefixes the
longest wins; ties go to the newest.

## 6. Labels, filter and corrections (capabilities 1 and 2)

### 6.1 Reading

`stores/items.py` loads the student's corrections and every rule for their classes once per
request and sets `ItemView.family` and `ItemView.family_reason` alongside the other derived
fields. `ItemView.is_assessment` becomes a property, `family == "assessment"`; the
`items.is_assessment` column stays until a later schema drops it.

### 6.2 The word on the row

In `_item.html`'s meta line, where `paper` and `outside Canvas` already sit (the line density's
`line_meta` and the card head's meta span): `phrasing` keys `type.assessment`,
`type.lab_project`, `type.participation`, with no key for practice. Default copy in every tier:
"test/quiz", "lab/project", "participation". The child tier may word it differently later; the
key per tier is what the parity tests need.

The printed sheet (`reports/open_work.py`, `server.py`'s sort) prints the same word where it
prints the assessment mark today, and sorts by family rank (§7.1) in place of
`not is_assessment`. Words only, no colour, per the tiered-sheet decision.

### 6.3 The filter

The kid page and the class page take `?type=<family>`, beside the kid page's `?outcome=`; the
two combine (`?type=assessment&outcome=not_done` is "missed tests"). Above the list, a row of
links with counts in the dashboard's outcome-link style: "All 48 · Tests & quizzes 9 · Everyday
31 · Labs & projects 5 · Participation 3". A family with no items is left out of the row. An
unknown `?type=` value is ignored, as an unknown `?outcome=` is.

### 6.4 Correcting

Grown-up tiers only, on the item detail card (`_item_detail.html`): one line, "Type: {family}
· {reason} · Change". Change opens a small form, `POST /items/<id>/type`:

- the four families as radio buttons, the current one checked;
- **"Also every item in {class} filed under '{group}'"**, offered when the item has a non-generic
  group or category, or when the chosen family is practice (where a generic group is exactly
  what a family wants to pin);
- **"Also every item in {class} whose name starts with '{prefix}'"**, where `prefix` is the
  name's text before its first digit, trimmed, offered when it is at least two characters and
  matches at least two other items in the class;
- each checkbox shows "changes N items", computed by running `family_of` over the class's items
  with the draft rule added and counting the ones whose family moves.

Saving writes the correction and any checked rule, then re-renders the card (htmx, as the flag
menu does). Choosing the family the ladder would give anyway, with no rule, deletes the
correction rather than storing a redundant one.

The class page gains a short "Type rules" list, one line per rule ("Name starts with 'WS #' →
Everyday work · Remove", `POST /courses/<id>/type-rules/<rule>/remove`), shown only when the
class has rules.

### 6.5 Diagnostics

A "Types" table, one line per class: items, then the count answered at each rung (correction,
rule, online quiz, gradebook name, item name, default). A class at 100% default is one whose
teacher's names defeat the classifier: the cue to add a rule.

## 7. Advice (capabilities 5 and 8)

### 7.1 Must-finish ranked within a deadline

`must_finish` (`stores/items.py`) keeps its six sections and their rows. Inside each section
the sort key becomes `(existing deadline key, -rank_worth, family_rank, -points, existing
tiebreak)`:

- the existing deadline key is what each section sorts by today (due for tonight, tomorrow and
  later; `late_until` then due for overdue), reduced to a date, so it still decides first;
- `rank_worth` is the row's lever `stake` from `stores/guidance.by_item` when that class's
  account is exact, else 0;
- `family_rank`: assessment 0, lab_project 1, practice 2, participation 3.

Rows due the same day, or losing credit the same day, therefore read most-worth first; nothing
moves across a date. `test_open_work_parity` (ids) is untouched; a new test pins the order.
`needs_you_now` inherits the order through `must_finish(...).red`.

### 7.2 Where the points are (class page)

A section after "What moves it", `.sec`/`.sec-head`, headed "Where the points are". Rows come
from the class's official account rows (the ones `stores/guidance.rows_for` builds, item ids
attached), grouped by family:

| Column | Value |
|---|---|
| Type | the family word; practice reads "Everyday work" here |
| Share of the grade | family `possible` / account `possible`, whole percent |
| Earned | `earned / possible`, counting HAC's blank-zero rows as the account does |
| Percent | `earned / possible` |
| Still open | points of the family's open levers (missing + upcoming), or "—" |

One sentence above, `phrasing` `where.*` per tier: names the largest-share family, and the
lowest-percent family when it differs by at least 10 points from the best. Earned sums to the
account's earned, so the table agrees with HAC's number.

When `account.match != "exact"`, or the class has no category table, the Share header reads
"Share by points" and a note under the table says "HAC may weight this class differently";
the sentence names shares by points and makes no weight claim. A class with one family shows
the table and no sentence. A class with no account shows nothing.

## 8. Trends by type (capability 10)

### 8.1 The section

On Trends, per kid, after the grade chart: "By type".

| Type | Year so far | Last 4 weeks | Not done |
|---|---|---|---|
| Tests & quizzes | 79% (14 scored) | 74% | 0 of 14 |

- **Year so far**: for each class, the family's `earned / possible` over scored rows due so far;
  a class counts toward a family only with at least 2 scored rows of it; the cell is the
  unweighted mean across counting classes, with the total scored rows in brackets.
- **Last 4 weeks**: the same over rows due in the last 28 days; "—" when no class qualifies.
- **Not done**: `outcomes.tally`'s not done over due rows of the family, "N of M".

A sentence above, `phrasing` `trends.by_type.*`, only when two families differ by at least
10 points year-so-far and each has at least 5 scored rows: "Tests run 15 points under everyday
work, in 4 of 6 classes." The "in N of M classes" counts classes where the same gap holds with
both families counting. Otherwise no sentence.

### 8.2 The chart

One line per family with a value, x = due week, y = year-to-date percent as of that week (the
§8.1 per-class mean, recomputed cumulatively). Built on the shared chart stack
(`charts.py`, `_chart_canvas.html`) and following the dataviz skill for colour and marks. A
note under it: "By the week it was due. Types as currently labelled: a correction relabels the
whole year."

### 8.3 The filter

Trends takes `?type=<family>` and filters the hand-in record line and the weekly outcome chart
by it, with the same link row as §6.3.

## 9. Testing

- `tests/test_types.py`: a table of real names from §1 with expected families; one case per
  ladder rung; HAC beating Canvas at rung 4; generic names skipped; rule precedence (group over
  prefix, longest prefix, newest); case folding.
- Schema 11 → 12 migration; ingest sets `online_quiz`; merge carries `item_types`.
- Row word present for three families and absent for practice, in every tier; the sheet word
  and sort.
- `?type=` counts and combination with `?outcome=`; unknown value ignored.
- Correction endpoint: write, redundant-correction delete, rule creation, prefix suggestion
  (two-character minimum, two-other-items minimum), "changes N items", rule removal; child
  tiers get no form.
- Must-finish order within a deadline (worth, then family rank, then points) and never across
  dates; parity ids unchanged.
- Where the points are: shares sum to 100, earned sums to the account, the not-exact label,
  sentence thresholds.
- Trends: per-class mean differs from pooled on a crafted case and the mean is shown; the 2-row
  and 5-row thresholds; 28-day window; `?type=` on the record line and weekly chart.
- New pages use `.sec` and `_item.html`; new `phrasing` keys exist per tier.

## 10. Delivery

Three PRs, each releasable alone, in this order:

1. **Foundation, labels and filter**: §4, §5, §6 (including the sheet and Diagnostics).
2. **Advice**: §7. Needs 1.
3. **Trends**: §8. Needs 1.

## 11. Not in this design

The other brainstormed capabilities, for later designs on this foundation: a "coming up:
tests" strip on Today (3); type in the printed sheet's grouping beyond the word and sort (4);
a study prompt pairing an upcoming test with recent quiz scores (6); check-in questions by type
(7); late rules by type (9); missing rate by type as its own view (11, partly covered by §8.1's
Not done); pace by type (12); the cross-class pattern as its own finding (13, partly covered by
§8.1's sentence); a by-type line on the report card (14).

Also out: fine types; a rules editor in Settings; children correcting types; a stored family
column; HAC category weights beyond the straight-points finding.
