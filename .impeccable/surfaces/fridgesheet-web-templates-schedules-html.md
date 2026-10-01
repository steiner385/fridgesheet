---
version: 1
slug: "fridgesheet-web-templates-schedules-html"
primary_target: "fridgesheet/web/templates/schedules.html"
related_targets: ["fridgesheet/web/routes/schedules.py","fridgesheet/web/schedules.py"]
---

# Surface brief: Schedules (the household's timetable)

Scope: `/schedules` (schedules.html), the WORK page that says when the data refreshes and when
each report prints, and lets a parent change one schedule and save it; Operate mode. Audience: a
parent setting the sheet up once, then checking it took; the maintainer reading why a schedule
cannot run. Job: read the timetable in a glance, change a time, a day or a printer, save that one
schedule, see its next run and its last (maintainer, 2026-10-01: "the household's timetable";
each schedule "a ruled section, one Save"; next and last "a pencil line with the Runs word").
Proof: `schedules.rows` and `schedules.refresh_row` as the sections, `next_run` from the clock's
own plan, `last_run` from the runs the schedule itself made, `problem` from the plan; the two
POSTs (`/schedules`, `/schedules/refresh`) write config.toml and nothing else and come back with
their messages ("Scheduled: Mon, Fri at 16:30", "next: Fri 9/25 4:30 PM"). Constraints: the
notices (the Linux service hint, old scheduled tasks, the refresh-off warning) stay as page
lines; a config.toml that does not read is a line, not a 500, and no form is offered; the
`.schedule` forms keep the measure, the refresh form's `hx-post="/schedules/refresh"
hx-target="body"`, the report forms' `method="post"`, each with its hidden `key`, its `days`
ticks and a primary Save; "has not run on a schedule yet", "not scheduled" and "last: …, OK" stay
as the words the tests and the guide read. The world is settled (DESIGN.md, The Student Planner);
this brief records composition only. Unresolved: whether the problem word for a schedule that
cannot run should also reach the Runs log; whether the catch-up rule wants a pencil line here.

## Direction contract

THESIS: Schedules is the household's timetable: the refresh and then each report as ruled
sections parted by the printed rule, each head carrying its time at Display size at the right so
the page reads as a timetable before any field is opened, each closing on its own Save. It
refuses the stack of look-alike forms with their state in a sentence nobody finds.

OWN-WORLD: The Student Planner as documented: planner white with the faint ruling. Each schedule
a `form.sec.schedule` with its head (`.sec-head`): the report's title at 650 and, at the head's
right, the time at Display size in Ink ("2:00 PM"; the refresh's "every 2 hours, 5 AM–9 PM"), or
"not scheduled" in pencil when it is off; under the head one pencil line (`.sched-line`): the
days ("Mon–Fri", "Mon, Wed, Fri", "every day"), then "next Fri 9/25 2:00 PM", then "last Thu
9/24 2:00 PM" with OK in Checkmark Green or FAIL in Red Pen on Highlighter Red as Runs draws it,
or "has not run on a schedule yet"; a problem from the plan in Red Pen in place of next. Then
the fields label over control in the Settings grid (the on-switch as a tick line; Time; Every /
Between / and for the refresh; Printer; Print it), Days as a hairline fieldset with a day-row
legend and seven ticks, help in pencil, and the section's own filled Save on `p.form-save`.
Sections parted by the 1.5px printed rule. Notices as the planner's notice lines above. No box,
no card. Recognisable with the words removed: section heads with a large numeral at the right,
a pencil line, a grid of small fields, one blue button, a rule; again.

STORY: A parent opens Schedules on Sunday evening, reads down the right edge that the sheet
prints at 2:00 PM and the refresh runs every two hours, sees under Open Work Sheet that Friday's
run went OK, moves the time to 7:00 AM, saves, and reads "next Mon 9/28 7:00 AM" on the same
line.

FIRST VIEWPORT: Schedules and its intro ("Fridge Sheet runs these itself while it is running,
each from the last data refresh: a report does not refresh first."). REFRESH THE DATA — every 2
hours, 5 AM–9 PM; Mon–Fri · next Fri 9/25 11:00 AM · has not run on a schedule yet; ☑ Refresh on
a schedule · Every [2] hours · Between [05:00] and [21:00]; DAYS ☑ Mon … ☐ Sun; "Refreshes at
05:00, 07:00, …" in pencil; Save. The printed rule. OPEN WORK SHEET — 2:00 PM; Mon–Fri · next
Fri 9/25 2:00 PM · last Thu 9/24 2:00 PM · OK; ☑ Run this on a schedule · Time [14:00]; DAYS;
Printer [the printer on the Settings page]; ☑ Print it (off: keep the PDF only); Save. The rule.
WEEKLY SUMMARY — not scheduled; the fields; Save. Primary: one Save per section.

FORM: The time as the head's numeral, position 5 of the ordered grounded list, dealt as the lead
by the surface roll and locked by the maintainer over timetable lines with the form folded (2)
and days as the week strip (6); seed key 0da6308a; code-led, no image generation. Signature
interaction: Save writes one schedule and the page comes back with the numeral and the pencil
line updated; nothing else moves.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the
verdict, DESIGN.md, and every shipping raster carrying its provenance.
