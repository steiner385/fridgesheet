# What moves the grade: guidance on the levers a family actually has

Date: 2026-10-04. Status: design approved in discussion ("go with your recommendations");
awaiting review of this document. Asked for by the maintainer, as the sequel to the report
card (`2026-10-03-report-card-and-grade-account-design.md`): *"our next suite of capabilities
will be offering guidance to kids/families on understanding the grade and what opportunities
there are to improve the grade."*

The report card says what a class average is and how it is built. This design says what would
move it: which rows are worth the most, what the next scores have to be to reach or keep a
letter, and, just as plainly, when a letter is out of reach from anything the school has posted.
One pure engine computes it from the account; three surfaces say it in the kid's words.

## 1. What the data says

Run on 2026-10-04 over the household's live snapshot through `grading.account_hac`:

| Lever | Example | Size |
|---|---|---|
| Blank work HAC already counts as zero | Concert Band: 25 points | filled in, 87.54 → 95.74 (B to A) |
| | Honors Algebra II: 25 points | filled in, 70.88 → 75.68 (still C) |
| Work Canvas marks missing that HAC has not counted | Adv Social Studies 7: 21 items, 274 points | the class is 21 perfect points from a B |
| Posted work not yet scored | Band 150, Health 115, Algebra 80, Biology 40 points | what the next scores are worth |
| Distance to the next letter, in perfect points | Honors Biology: 3.4 | one good lab |
| | Adv Science 7: 31; Adv Social Studies 7: 21 | within posted work |
| | Honors Algebra II: 237 | more than everything posted: out of reach |

Three kinds of lever, then, and two distances (to the next letter, and the slack under the
current one). Every figure above is a hundredth-exact consequence of the straight-points account;
none exists where the account reads `off` or has no breakdown.

## 2. Decisions taken in discussion

1. **Where it lives: one engine, three surfaces.** The report card line gains a second sentence
   naming the single best lever (or the reach, when there is nothing to turn in). The class page
   gains a "What moves it" section: the reach or slack line, then the levers as item lines ranked
   by how many average points each is worth. Must-finish rows carry a worth badge, annotated
   only: the list is never reordered and nothing is added to it (spec 2026-09-27 §4.1, §14).
   Not chosen: the class page alone; a separate "Raise it" page.
2. **Reach is stated honestly and never extrapolated.** Only work the school has posted counts
   as "the next points". In the older and middle tiers the app says "a B needs 31 of the next
   31 points; 20 are posted so far" and, when the need exceeds the posted work, "more than the
   20 points posted so far". The early tier says what keeps or raises the grade and never
   "can't". Not chosen: extrapolating the marking period from pace; never discussing reach.
3. **Late credit follows the family's late rule.** A lever is worth "up to N points" at full
   credit unless the matching late rule's credit text names a percentage, in which case the
   credited worth is shown. A row past its late deadline, or flagged Too late or Let it go (or
   Done or Excused), is not a lever at all. Not chosen: always full credit; asking the family
   to enter a credit per class first.

## 3. Terms

- **Account**: `grading.Account` for the class's official source (spec 2026-10-03 §4).
  Guidance is **sound** only when `account.match == "exact"`; otherwise it names points, never
  average points, and states no reach.
- **Lever**: one open row a kid can still act on, with the points it holds and what earning
  them is worth on the average. Three kinds:
  - `zero`: a blank HAC row the gradebook already counts as zero (its points are inside the
    account's `possible`). Earning it raises `earned` with `possible` fixed.
  - `missing`: an overdue row, still inside the late window, not yet counted (Canvas-missing
    with no HAC zero, or a blank HAC row beyond what the subtotals show as zero). Earning it
    adds to both `earned` and `possible`.
  - `upcoming`: a posted row not yet due. Adds to both, at full credit.
- **Worth**: the average points a lever would add if earned at its credit:
  - `zero`: `100 × credit × points ÷ possible`
  - `missing`, `upcoming`: `100 × (earned + credit × points) ÷ (possible + points) − rebuilt`
- **Credit**: `1.0`, or the fraction in the late rule's credit text when it names a percentage
  (`late_rules.credit_fraction`, the parser `verdicts._credit_fraction` is today). The seeded
  default credit `"?"` reads as full credit, and the lever's note says the credit is unknown.
- **Reach**: for the next letter above the current one, the perfect points needed on
  not-yet-counted work once every `zero` lever is filled at its credit:
  `needed = (floor/100 × possible − earned′) ÷ (1 − floor/100)`, with
  `earned′ = earned + Σ zero levers' credit × points`; `posted` = Σ points of `missing` and
  `upcoming` levers; **reachable** when `needed ≤ posted`; **zeros alone** when `needed ≤ 0`.
- **Slack**: for the current letter, the points of posted work that may be lost and keep it:
  `can_miss = earned′ + posted − floor/100 × (possible + posted)`; negative means the letter
  needs `−can_miss` of the next `posted` points to hold.
- **Allocation of zeros to rows.** The account knows per category how many blank points HAC
  counts as zero (`Line.zero_points`, a new per-line field alongside the account's total) but
  not which rows. HAC enters zeros for work past due, so within a category the blank,
  unexcused, past-due rows are taken as counted at zero oldest-due first until their points
  reach the category's `zero_points`; the rest are `missing`. A heuristic, named as one in the
  module docstring; it decides only whether a row's points are already in `possible`.

## 4. The engine: `fridgesheet/guidance.py`

Pure, like `grading.py`; the web store and the MCP server both call it.

```python
@dataclass(frozen=True)
class Lever:
    item_id: int | None
    name: str
    kind: str                 # "zero" | "missing" | "upcoming"
    points: float
    credit: float             # 1.0 unless the late rule names a percentage
    credit_known: bool        # False when the rule's credit text is "?" or blank
    worth: float | None       # average points if earned at `credit`; None when the account is not sound
    deadline: datetime | None # late_until for zero/missing, due for upcoming
    category: str

@dataclass(frozen=True)
class Reach:
    letter: str; floor: float
    needed: float             # perfect points of not-yet-counted work, after zeros are filled (≤ 0: zeros alone)
    posted: float             # points of missing + upcoming levers
    reachable: bool

@dataclass(frozen=True)
class Slack:
    letter: str; floor: float
    posted: float
    can_miss: float           # may be negative: the letter needs −can_miss of the next `posted`

@dataclass(frozen=True)
class Guidance:
    sound: bool
    letter: str               # the scale's letter for the reported number
    levers: tuple[Lever, ...] # worth descending (points descending when not sound), then deadline
    best: Lever | None
    reach: Reach | None       # None at the top letter, or when not sound
    slack: Slack | None       # None when not sound
    zero_points: float        # Σ zero levers' points (what "blank work" means in the sentences)

def guide(account: grading.Account, rows: list[dict], scale: grading.GradeScale) -> Guidance
```

A `row` is `{item_id, name, category, points, due, late_until, credit_text, overdue: bool,
upcoming: bool, hac_blank: bool}`; the store builds rows from the open-work view (§6) so the
engine never decides what is open. `guide` sorts rows into kinds (allocation above), computes
worth, reach and slack, and ranks. With `account.reported is None` or `match != "exact"`,
`sound` is False: levers keep points and credit, `worth` is None, `reach` and `slack` are None.

## 5. The sentences: `gd.*` in `phrasing.PHRASES`

Numbers formatted first (`grading.fmt_points`, worth to one decimal with a sign). Older tier:

| Key | When | Older |
|---|---|---|
| `gd.zeros_reach` | zeros alone reach the next letter | "Turn in the {zero_points} points of blank work and it's a {letter}." |
| `gd.best` | a lever exists | "Best move: {name} ({points} pts), worth up to +{worth}." |
| `gd.reach` | reachable, `needed > 0` | "A {letter} needs {needed} of the next {posted} points." |
| `gd.reach_far` | not reachable | "A {letter} needs {needed} points: more than the {posted} posted so far." |
| `gd.keep` | slack ≥ 0 | "Keeping the {letter}: you can miss up to {can_miss} of the next {posted} points." |
| `gd.hold` | slack < 0 | "Keeping the {letter} needs {need} of the next {posted} points." |
| `gd.nothing_posted` | no levers, no posted work | "Nothing posted to turn in or come; the next work the teacher posts decides it." |
| `gd.not_sound` | not sound, levers exist | "{n} rows still open, {points} points. HAC's number does not rebuild from what we see, so these are points, not average points." |
| `gd.lever_zero` | a zero lever's note | "Blank, counted as zero now · accepted until {until}{credit_note}" |
| `gd.lever_missing` | a missing lever's note | "Not counted yet · accepted until {until}{credit_note}" |
| `gd.lever_upcoming` | an upcoming lever's note | "Due {due} · not counted yet" |
| `copy.gd_credit_at` | credit named | " at {credit}" |
| `copy.gd_credit_unknown` | credit "?" | " · late credit unknown, ask" |
| `badge.worth` | Must-finish badge | "+{worth} on the average" (early: "worth +{worth}") |

Early-tier versions say the same facts in fewer words and never "can't": `gd.reach_far` early
is "A {letter} would take {needed} points. There aren't that many posted yet. Keep going and
ask your teacher what's coming." Middle sits between.

**The report card's second sentence** (`stores/guidance.sentence_for`): in order, `gd.zeros_reach`;
else `gd.best` followed by `gd.reach` when reachable; else (no levers) `gd.reach` / `gd.reach_far`
when there is a next letter and posted work, `gd.keep` / `gd.hold` at the top letter, or
`gd.nothing_posted`; not sound: no second sentence (the first already says it does not add up).

## 6. Reading it: `web/stores/guidance.py`

```python
def rows_for(work: items.OpenWork, course_ids: set[int], rules, student, course_name, peer_name) -> list[dict]
def for_class(conn, student, course, account, work, rules, scale) -> Guidance
def by_item(conn, student, work, prefs, rules, scale) -> dict[int, Lever]      # the Plan's badges
def sentence_for(line: grades.ReportLine, g: Guidance) -> tuple[str, dict] | None
```

- Rows come from `items.open_work(...)`'s `fixable + upcoming` (spec 2026-09-27 §4.1: the one
  definition of what is still to do), filtered to the class's two course ids. Handled flags,
  past-window rows and excused rows are already outside that list. `hac_blank` is true when the
  row's latest HAC observation has no score; `credit_text` is the resolved late rule's credit;
  `late_until` is the view's.
- `for_class` calls `grades.account_for` for the official source's course and `guidance.guide`.
  A Canvas-official class is sound only when its groups rebuild exactly, which in this
  household they do not; it gets points, not average points.
- `by_item` runs `for_class` once per class a kid has open work in and maps `item_id → Lever`.

## 7. The surfaces

### 7.1 The report card line

`li.report-line` gains `<p class="lever">` after `.how`, holding the sentence(s) from
`sentence_for`, in the kid's tier. Absent when `sentence_for` returns None. The parity test
still sees one row per class.

### 7.2 The class page: "What moves it"

After `section.sec.grade-account`, `section.sec.what-moves-it` with a `.sec-head` ("What moves
it", count "{n} levers"), a `.lead` holding the reach or slack line (or `gd.not_sound`,
or `gd.nothing_posted`), then `ol.levers` of `_item.html` lines (density `line`, read-only, the
class page's own `on_class_page` rule for the meta) with `badges = ["+4.8"]` (sound only) and
`says` = the lever's note. Sorted as the engine ranks them. A class with nothing open and no
posted work is the one `gd.nothing_posted` sentence. Only the official source's account feeds it.

### 7.3 Must-finish badges

`_must_finish.html` appends `badge.worth` to a row's `badges` when the route passes
`worth_by_item` and the row's lever is sound with `worth ≥ 0.05`. The Plan and Check-in route
(`routes/checkin.py::_context`) and Today (`routes/dashboard.py`) compute `by_item` once. Rows,
order and groups are unchanged (`test_open_work_parity`, tier parity).

### 7.4 MCP

`grades()` gains `"guidance": asdict(Guidance)` per class from the snapshot, with the
snapshot's own rows (Canvas assignments with `missing`/unsubmitted and HAC blank rows, late
rules from `late_rules.load`), so Claude can answer "what should she do first in Algebra" from
the same arithmetic. The docstring repeats the sound gate.

## 8. Storage and configuration

None. Everything derives from `item_observations`, `category_observations`, `grade_observations`,
the late rules file and the scale.

## 9. Tests

- `tests/test_guidance.py`: the §1 cases as fixtures. Band (25 zero points reach the A: `zeros
  alone`), Biology (B needs 3.4, reachable; `gd.reach`), Algebra II (zeros fill to 75.68, B needs
  237 > posted: `gd.reach_far`), Adv Social Studies 7 (missing levers at 274 posted points, B
  needs 21: reachable), a class at the top letter (slack), a negative slack, a late rule with
  "50%" halving worth, credit "?" marked unknown, a not-sound account (worth None, no reach),
  the zero allocation (oldest-due first within a category, a not-yet-due blank row stays
  `upcoming`), ranking.
- `tests/test_web_guidance_store.py`: rows from the shared fixture's open work; English's
  Participation (blank HAC, overdue, inside the window) is a `missing` lever worth +2.0; the
  Canvas upcoming rows are `upcoming`; `sentence_for` picks `gd.best` + `gd.reach` for English
  (A needs 10 of the next N); a class with nothing open gives `gd.nothing_posted`.
- `tests/test_web_report_card.py`: the `.lever` line present for English, absent for the class
  whose how is `rc.no_breakdown`; one row per class in every tier.
- `tests/test_web_class_page.py`: the section, its lead, a lever line with its badge and note;
  the not-sound lead on a rows-basis class; the empty-state sentence.
- `tests/test_web_checkin.py` / `test_web_plan_*`: a Must-finish row carries `+2.0 on the
  average`; rows and order unchanged (`test_open_work_parity` untouched).
- `tests/test_phrasing.py` covers the keys by construction; `tests/test_server_tools.py`: the
  `guidance` field for the graded fixture.

## 10. Documentation

- `docs/user-guide.md` §6.5: a "What moves it" subsection with the three lever kinds and the
  reach sentence, and §6.2 Plan: the worth badge. `docs/outcomes.md`: one sentence on worth.
- `DESIGN.md`: the report card paragraph gains the `.lever` line; the class page's section;
  the badge. `.impeccable/surfaces/` briefs for report_card and course gain the section.
- `docs/product/features/report-card.md`: a "What moves it" paragraph and the sound gate.

## 11. Not in this design

- **Reordering Must-finish by worth**, or a "sort by worth" control: the Plan's order is the
  school's deadlines (spec 2026-09-27). A later design may add a sort.
- **Extrapolating unposted work**, "if you keep this pace" projections, or any letter forecast.
- **Category weights** and classes whose account reads `off`: they get points, not worth, until
  a weights follow-up lands.
- **Canvas-official classes' worth**: the Canvas account is a check, not a model of Canvas's
  grading (omit-from-final, zero-point extra credit, late penalties); sound only when exact.
- **A per-class credit editor**: the late rules' credit text is the one place credit lives.
- **Retakes and replacement policies** ("the retake replaces the test"): not modelled; a retake
  row is an upcoming lever like any other.

## 12. Risks

- **The zero allocation is a heuristic.** It decides whether a row's points are already in the
  denominator, which changes a lever's worth by at most the difference between the two worth
  formulas (small for one row in a 300-point class). Named in the docstring and tested; a
  category whose blank rows exceed its zero points lists the newest as `missing`.
- **Pressure.** A worth badge on every Must-finish row could read as a scoreboard to a child.
  The badge is in the planner's badge style, the early tier says "worth +2.0" and nothing about
  letters, and reach sentences in that tier never say what cannot be done.
- **A sentence that ages.** "A B needs 3.4 of the next 40 points" is true at the last refresh;
  the page's "as of" line already dates every number on it.

## 13. Amendments from the final review (2026-10-04)

- **The zero budget is spent by every blank past-due row first**, not only the open ones: rows
  past their late window or answered (Let it go, Too late, Done) ride along as `counted_only`,
  use their category's budget oldest-due first, and are never levers. Without this a newer
  blank row inherited budget HAC spent on an older one, and `gd.zeros_reach` could promise a
  letter the kid would not get.
- **An explicit zero is a `zero` lever** (HAC's 0, or Canvas's where HAC has no row): its
  points are already in `possible`, and it needs no budget.
- **Worth never goes below zero**, and a `missing` lever also carries `cost`: what the zero it
  becomes would take off the average shown (`rebuilt − 100·earned ÷ (possible + points)`).
  Levers rank by `stake = worth + cost`, so work about to become a zero comes first.
  Sentences: `gd.best_missing` ("…worth up to +2.0 now, and left blank it would cost 14.7"),
  `gd.protect` when it cannot raise the number ("Don't leave Essay (10 pts) blank: … a zero would
  cost 16.7"), and the lever note's `copy.gd_cost`. A best move worth less than 0.05 in stake is
  not said; neither is a "+0.0" badge.
- **Sentence order** after the best move: `gd.reach` or `gd.reach_far` whenever there is a next
  letter and posted work; `gd.hold` whenever the current letter is at risk; `gd.keep` at the top
  letter. (§5's "no levers" branch made `reach_far`, `keep` and `hold` unreachable.)
- **A cut at 100 or above is never a reach** (a family scale with "A+ = 100" divided by zero).

## 14. Weighted classes (2026-10-04, approved in discussion)

A read-only capture of the household's HAC Classwork pages found why four classes (Math Plus
5th, Adv Math 7, ELA Plus 5th, Adv Language Arts 7) showed no category table: HAC weights them,
and a weighted class's category table has six columns (Category, Student's Points, Maximum
Points, Percent, Category Weight, Category Points). The scraper kept only four-column rows.
With the weights read, all four rebuild to HAC's number exactly as the weighted average of their
category percents (each weight 1.00 here); the two total-points classes checked alongside are
unchanged.

- `hac.parse_row` reads both tables; a category row carries `weight` (None for total points).
- Schema 12 adds `category_observations.weight`; a change of weight is a new set.
- `grading`: a class whose every subtotal has a weight has basis `weighted`; `rebuilt` is
  `100 × Σ(weight × earned ÷ possible) ÷ Σ weight` over categories with anything possible, and a
  line's `share` is its weight's share. The class page says "the average of its category
  percents, each counted by its weight, not total points", and the check line "Adds up: the
  average of N category percents, as HAC weights them" (`rc.adds_up_weighted`).
- `guidance`: in a weighted class a lever moves only its own category's percent, so its worth
  and cost come from that category (ten points of a 17-point Quiz are worth +4.36 in Math Plus;
  ten of a 40-point Assignments +0.33). A lever in a category the table does not list has no
  worth. The reach is the **ceiling** the posted work allows (every posted lever earned at its
  credit, every zero filled), never a point count: `gd.ceiling` ("Full marks on the 10 points
  posted would take it to 90.93: an A") or `gd.ceiling_far` ("…short of an A"). No slack line.
