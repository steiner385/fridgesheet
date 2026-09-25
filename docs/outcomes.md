# How Fridge Sheet decides what happened to an assignment

Canvas and Home Access Center each tell part of the story, in different words. This is the
one table the app uses to turn those words into an answer a parent can act on — and it is
the same table whether you are reading a kid's card on Today, a kid's Assignments tab, the
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
| **excused** | The teacher excused it. | Canvas `excused`, or HAC's **EXC** in the score column. Counted nowhere, never asked about, never printed. |
| **unpublished** | The teacher unpublished it. Not work the kid can do. | Canvas `published = 0`. Counted nowhere. |
| **not done** | The work was not done. | Any one of: Canvas flagged it **missing** (unless HAC has a grade above zero — see below); a **score of 0** was entered (in Canvas or HAC, with or without a submission — a blank hand-in scored 0 is not done); or it is **online** work, **past due**, with no submission and no grade. |
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
- **A HAC grade beats Canvas's automatic "missing"**, whichever source the family prefers.
  When HAC has a score above zero, the work counts as done on paper even if Canvas still
  shows it missing: Canvas's late policy sets that flag by itself, and a HAC grade is the
  teacher's assessment. The one exception is a missing mark (or a zero) Canvas recorded
  *after* HAC's grade, in a later refresh; then the app asks instead of deciding. Example:
  Quiz 1, missing in Canvas and 28/30 in HAC, both seen in the same refresh, is done. What
  counts is when the *mark* first appeared, not when Canvas last changed anything about the
  item: the availability window closing a week after HAC's grade is not the teacher marking
  it missing again, and the work stays done (`missing_since` on the observation). The printed
  sheet reads a snapshot with no history, so it always follows HAC's grade here.
- **"Due so far" means work that is due.** Work handed in before its due date is *on time*
  from the moment it is handed in -- the outcome is right -- but it does not join *of N due
  so far* on Today, the Assignments tab or Trends until the due date passes. Work with no
  due date can never become past due, so it is on the record as soon as anything has
  happened to it (a grade, a hand-in, a mark); with nothing at all it is *not due yet* and
  off the record. `outcomes.on_record` is the one test every tally uses.

## Where each outcome shows up

| place | what you see |
|---|---|
| **Today, each kid's card** ("School record so far") | *N on time · N late · N not done · N on paper · N unknown · of N due so far.* Each number links to the rows behind it. "Due so far" is the five settled outcomes of work whose due date has passed (`outcomes.on_record`); work handed in early is not on the record until it is due, and not-due, excused and unpublished never are. |
| **Assignments tab, Outcome filter** (under *More filters*) | Every row's outcome; filter by one. Choosing an outcome shows *all* matching rows, including those past their late-work window — "not done" means not done, whether or not it can still be fixed. |
| **Open work page** | The sheet's two questions on a screen, per kid: *Still fixable* is the actionable rows (below) no more than the Overdue days setting past due, soonest-closing late-work window first, each with the day it closes and the credit the register promises; *Coming due* is unsubmitted Canvas work due within the Days ahead setting. What is open but past its window, and what you flagged handled, are counted underneath with links, not listed. Both read Days ahead and Overdue days through one accessor (`config.day_option`), so the page lists the same rows the sheet prints. Each row is the work list's row: the item's verdict, its question tag, and its detail card. |
| **Assignments tab, the work list** | Three columns: *Due*, *Assignment* (its class and kind beneath it) and *Where it stands* — one phrase from the item's verdict (`web/verdicts.py`), red only when the school recorded it as not done and nothing settled it otherwise. The raw facts the outcome was decided from are in the row's detail card: what Canvas and what HAC each say, and as of when. |
| **Trends, "How the work due each week came out"** | The five settled outcomes per week of *due date*, for work that is due — the same numbers as the card, spread over the calendar. By due week, not refresh week, so the chart shows the year so far from the first day. |
| **Trends, "On-time hand-ins"** | *on time ÷ (on time + late + not done)* over work due so far. "Done on paper" is left out because its timing is unknowable; "unknown" is left out because it is unknown. |
| **Questions** | Not an outcome — a *verdict* on top of it (`web/verdicts.py`): the app **decides** what the records settle (a HAC grade over Canvas's automatic missing; a gap explained by the late-work rule), **waits** on what time will settle (a Canvas grade not yet in HAC; paper work with no grade for less time than that class usually takes; work handed in and not graded), and **asks** only when the family can act: HAC lower than Canvas, a HAC zero on work handed in online or excused in Canvas, HAC still blank longer than it usually takes for that class, paper or HAC-only work with no grade longer than that class usually takes, or a newer record contradicting your own answer. "Usually takes" is Fridge Sheet's own count from that class's earlier grades (`web/pace.py`), 7 days until there are enough of them. Too late for credit is a status, not a question. |
| **"open"** (the Assignments tab's *Open* choice, which also shows what is coming due; Trends, *Open the longest*) | *not done* or *unknown*, plus *late* until it is graded (`web/reconcile.py`, `open_sources`). Defined from the outcome, so paper work the gradebook has marked is settled — it used to count as open forever because Canvas never sees a paper hand-in. |
| **The printed sheet** | Only what is still open: MISSING, ZERO, LATE, PAPER — CHECK, HAC — NO GRADE, and DUE TODAY / DUE TONIGHT / DUE TOMORROW / DUE *day*. These are the same facts, shouted, and limited to what a kid can still do something about. A deadline in the first hour of a day (00:00–00:59) belongs to the evening before: it is DUE TONIGHT on that day, never "due tomorrow" the evening it has to be finished, and the app's "Due tonight" and "due today" count say the same (`dates.deadline_date`). Work marked EXC in HAC does not print. Work with a grade above zero in HAC is *done on paper* and does not print, even where Canvas still shows MISSING (the sheet has no refresh history, so unlike the app it cannot tell a MISSING set after the grade); a 0 in either source still prints. |
| **"still fixable"** (Today's card, Open work; `actionable` in the code) | Also not an outcome: *not done* or *unknown* work that is still inside its late-work credit window (`late-rules.toml`) and that you have not flagged as handled. It is the short list for tonight; the record line is the long one for the quarter. |
| **How it is worded** | Every child sees every row and every action. A `[kids].grades` entry changes type, density, colour and vocabulary only (`fridgesheet/web/tiers.py`, `fridgesheet/web/phrasing.py`) — never which rows appear, which `tests/test_web_tier_parity.py` holds. No child phrase states a time, date or number its adult equivalent does not. The printed sheet follows the same rule per kid section: a kid on the early or middle tier reads the phrase table's word for the status ("Teacher hasn't got it" for MISSING, `sheet.status_word`) in the same colour and the same row; an older or ungraded kid's section, and the legend, keep the capitals. |

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
even where Canvas shows a score. The Assignments tab's *Settled by the records* lines still show where Canvas disagrees, each with a *Not right?* link.

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
| the teacher's marks | `missing`, `excused` | `EXC` in the score column (excused) |
| score | `score` / `grade` | `score` / percent |
| published | `published` | — |
| kind of work | submission types → online / paper / in class | — (assumed paper when only HAC lists it) |
| due date | yes | yes |

Which is why a HAC-only item can be *done on paper*, *not done* (a 0), *excused*, *unknown* or *not
due yet* — but never *on time* or *late*: HAC cannot say.
