# How Fridge Sheet decides what happened to an assignment

Canvas and Home Access Center each tell part of the story, in different words. This is the
one table the app uses to turn those words into an answer a parent can act on — and it is
the same table whether you are reading a kid's card on the Dashboard, the Kid page, the
Trends page or the printed sheet. The code is `fridgesheet/web/outcomes.py`; if the two
ever disagree, the code is wrong.

## Why one table is needed

Canvas's **Missing** is a flag, not a fact. Canvas sets it in two cases only: a teacher
clicks "missing", or the course's late policy is set to *automatically apply missing
status* and the work is past due, unsubmitted and **online**. It is never set for paper or
in-class work — Canvas has no way to know a worksheet was not handed in — and many
teachers enter a **0** rather than click the flag.

So on one real day: Canvas's dashboard said **4 missing**; the gradebooks actually held
**11 not done** (4 flagged, 6 zeros, 1 unflagged online item never submitted) plus **8
unknown** (paper work with no grade anywhere yet). Neither "flagged missing" nor "past due
and not submitted" is what a parent means by *missed*. Each source is right about what it
records; the app's job is to read all of it.

## The outcomes

Every assignment either source has mentioned gets exactly one of these. The checks run in
this order and the first that applies wins — that is the order of certainty.

| outcome | what it means | how it is decided |
|---|---|---|
| **excused** | The teacher excused it. | Canvas `excused`. Counted nowhere. |
| **unpublished** | The teacher unpublished it. Not work the kid can do. | Canvas `published = 0`. Counted nowhere. |
| **not done** | The work was not done. | Any one of: Canvas flagged it **missing**; a **score of 0** was entered (in Canvas or HAC, with or without a submission — a blank hand-in scored 0 is not done); or it is **online** work, **past due**, with no submission and no grade. |
| **late** | Handed in after the deadline. | Canvas has a submission and marks it `late`. Whatever it was then graded, it was late. |
| **on time** | Handed in by the deadline. | Canvas has a submission, not marked late. |
| **done on paper** | Done, but not through Canvas. | A grade above zero — in Canvas or HAC — with no online submission. Paper or in-class work handed in and marked by hand, or online work the teacher graded from a physical copy. Its timing is unknowable, so it is neither on time nor late. |
| **unknown** | Nobody has said yet. | Past due, nothing handed in online, no grade in either source — and it is paper or in-class work, so Canvas could not have seen it. **This is the list to ask teachers about.** |
| **not due yet** | Nothing has happened. | Due in the future (or no due date) and not handed in. |

Two consequences worth knowing:

- **A teacher's 0 counts as not done**, on purpose. In practice it is how many teachers
  record a missed assignment, and it costs the grade exactly as a missing flag would.
- **Work done on paper is not "not done"**, on purpose. Canvas lists it as unsubmitted
  forever; the grade is the proof it was done. The old Status column called these
  "Missing" and was wrong about them roughly a dozen times per kid.

## Where each outcome shows up

| place | what you see |
|---|---|
| **Dashboard, each kid's card** | *N on time · N late · N not done · N on paper · N unknown · of N due so far.* Each number links to the rows behind it. "Due so far" is the five settled outcomes; not-due, excused and unpublished are not on the record. |
| **Kid page, Outcome filter** | Every row's outcome; filter by one. Choosing an outcome shows *all* matching rows, including those past their late-work window — "not done" means not done, whether or not it can still be fixed. |
| **Open work page** | The sheet's two questions on a screen, per kid: *Still fixable* is the actionable rows (below), soonest-closing late-work window first, each with the day it closes and the credit the register promises; *Coming due* is unsubmitted Canvas work due within the Days ahead setting. What is open but past its window, and what you flagged handled, are counted underneath with links, not listed. It is not row-for-row identical to the PDF: the sheet additionally drops a row more than `overdue_days` past due, which this page does not, so a long-abandoned item can show here and not on paper. |
| **Kid page, Handed in and Grade columns** | The raw facts the outcome was decided from, kept separate: Handed in is the submission (Yes / Late / No / Excused / — for paper, in-class and HAC-only work); Grade is the gradebook (the score, a 0 in red, the teacher's Missing, "Not yet" for handed in and unmarked). |
| **Trends, "How the work due each week came out"** | The five settled outcomes per week of *due date* — the same numbers as the card, spread over the calendar. By due week, not refresh week, so the chart shows the year so far from the first day. |
| **Trends, "On-time hand-ins"** | *on time ÷ (on time + late + not done)* over work due so far. "Done on paper" is left out because its timing is unknowable; "unknown" is left out because it is unknown. |
| **Reconcile** | Not an outcome — a *reason the outcome is uncertain*: the two sources disagree, only one source knows the item, it is turned in but ungraded, it is paper work with no grade (the "unknown" outcome, with a button to ask), it is still open past its credit window, or a flag you set has been overtaken. |
| **"open"** (Kid page filter, Reconcile, *Open the longest*) | *not done* or *unknown*, plus *late* until it is graded. Defined from the outcome, so paper work the gradebook has marked is settled — it used to count as open forever because Canvas never sees a paper hand-in. |
| **The printed sheet** | Only what is still open: MISSING, ZERO, LATE, PAPER — CHECK, HAC — NO GRADE, and DUE TODAY / DUE TOMORROW / DUE *day*. These are the same facts, shouted, and limited to what a kid can still do something about. Paper or in-class work with a grade in HAC is *done on paper* and does not print; a teacher's own MISSING flag or 0 still does. |
| **"actionable"** (Dashboard, Kid page) | Also not an outcome: *not done* or *unknown* work that is still inside its late-work credit window (`late-rules.toml`) and that you have not flagged as handled. It is the short list for tonight; the record line is the long one for the quarter. |
| **How it is worded** | Every child sees every row and every action. A `[kids].grades` entry changes type, density, colour and vocabulary only (`fridgesheet/web/tiers.py`, `fridgesheet/web/phrasing.py`) — never which rows appear, which `tests/test_web_tier_parity.py` holds. No child phrase states a time, date or number its adult equivalent does not. |

## Which source is the source of truth

Neither, for everything — each is authoritative for something the other does not have.

- **HAC is the gradebook of record.** It is what the report card is computed from, and its
  *marking-period average* is the kid's actual grade in the class. It also lists work that
  Canvas never has: weekly participation and effort grades, labs, in-class quizzes,
  worksheets graded by hand. On one real day it held **36 assignments Canvas did not** for
  one kid, **16** and **31** for the other two — nearly all of them graded.
- **Canvas is where online work lives.** It is the only source that knows whether and when
  something was *handed in*, whether it was *late*, and whether the teacher marked it
  *missing* or *excused*. It also has work HAC has not posted yet, or never will (ungraded
  practice, "check-ins"). Its *current score* is computed over Canvas assignments only, so
  for a class that is mostly HAC-graded work it is not the grade — HAC's average is.

So the app pairs the two by course and then by assignment, and reads both: submission and
marks from Canvas, and the score from the family's chosen source. Pairing is by title, with a
fallback for titles the two teachers typed differently — the same due date, the same points,
exactly one candidate, and every number in the two titles agreeing — because an assignment
that fails to pair shows up **twice**: once as *done on paper* from HAC and once as *unknown*
from Canvas.

### Choosing the source

By default assignment scores come from **Canvas** and class averages from **HAC**. Both can be
changed for the whole family on Settings, and for one kid or one class on the class's page
(`[sources]` in `config.toml`). The chosen source wins when both have a number; the other still
fills in what it lacks, so a class Canvas never lists still shows HAC's work and a kid whose
school uses one system still shows that system. Submitted, late and excused always come from
Canvas, because HAC does not record them. Under a HAC preference a HAC score settles the item:
a HAC 48/50 is *done on paper* even where Canvas says *missing*, and a HAC zero is *not done*
even where Canvas shows a score. The Reconcile page still lists every disagreement.

Paper work is not a reason on its own to prefer HAC. In this household's data on 2026-09-21,
20 of 27 past-due paper assignments were graded in Canvas. The real conflicts were one
teacher's online quizzes, auto-scored in Canvas and finalised in HAC — which is what a
per-class rule is for.

### Two assignments with the same title

Pairing joins one Canvas item to one HAC item. It never joins two Canvas items to each
other, and that is deliberate. A teacher may enter the same title twice in one course —
seen live as `Cool-down: Find the Volume of a Figure`, Canvas assignments **2571430** and
**2571431**, same course, same 4 points, same due date, both unsubmitted — and those are two
pieces of work, not one listed twice. `items.key` is `canvas:<id>`, the source's own
identity, so the app has no way to confuse them and no licence to merge them: collapsing the
pair would under-count the work and let a kid finish one of the two and appear done.

The fallback matcher inherits the same caution from the other side. It pairs a HAC row to a
Canvas item only when **exactly one** candidate fits the date and the points, so when a
course holds two identical Canvas assignments, a HAC grade that matches both is attached to
neither and stays a HAC-only row. An ambiguous match is left visible rather than guessed.

Pinned by `test_two_canvas_assignments_with_the_same_title_stay_two_items` and
`test_a_hac_row_will_not_guess_between_two_identical_canvas_assignments`.

## What the sources actually provide

| signal | Canvas | HAC |
|---|---|---|
| submission and when | `submitted_at`, `late` | — (HAC records grades, not submissions) |
| the teacher's marks | `missing`, `excused` | — |
| score | `score` / `grade` | `score` / percent |
| published | `published` | — |
| kind of work | submission types → online / paper / in class | — (assumed paper when only HAC lists it) |
| due date | yes | yes |

Which is why a HAC-only item can be *done on paper*, *not done* (a 0), *unknown* or *not
due yet* — but never *on time* or *late*: HAC cannot say.
