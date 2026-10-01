---
version: 1
slug: "fridgesheet-web-templates-reports-html"
primary_target: "fridgesheet/web/templates/reports.html"
related_targets: ["fridgesheet/web/templates/report_builder.html","fridgesheet/web/templates/report_view.html","fridgesheet/web/templates/_report_preview.html","fridgesheet/web/routes/reports.py"]
---

# Surface brief: Reports (the household's report shelf)

Scope: `/reports` (reports.html, the shelf), `/reports/new` and `/reports/{id}` (report_builder.html,
the builder), `/reports/{id}/view` with `_report_preview.html` (the report's own page, on screen
and through the browser's print dialog); Operate mode. Audience: a parent picking a report to
look at or print, once a week; the same parent building or repairing one, rarely. Job: find the
report, see whether and when it last printed, Preview then Print, and reach Edit, CSV, JSON and
Delete without them crowding the line (maintainer, 2026-10-01: "the household's report shelf";
the list "ruled lines, one per report"; Preview and Print "two stroke buttons at the right"; all
three pages in scope). Proof: `registry.REPORTS` and `reports.all` as the shelf's two groups;
`runs.latest_for` for each line's last run, said through `runs.describe` so a preview is not
called a print; `jobs` gating every Preview and Print; one "Refresh data first" tick for the page
included by every job button; the builder's `#builder` form swapped whole on a source change with
its `customRange`, `chartFields` and `chartSeries` ids; `views.build` behind the preview and the
view. Constraints: the report key stays as the name's `title` attribute (the command line reads
it); the starter-reports sentence and button stay until a report exists; Delete stays the danger
button and Save the primary; the view page stays its own document (`print-page`, the page head
`screen-only`) and keeps Edit, CSV, JSON and Print / save PDF as its actions; the preview partial
serves both the builder's live preview and the view. The world is settled (DESIGN.md, The
Student Planner); this brief records composition only. Unresolved: whether the builder wants a
two-column desk (form beside its preview) on a wide screen; whether Schedules joins the shelf.

## Direction contract

THESIS: Reports is the household's report shelf: two day rows, BUILT IN and YOURS, over ruled
lines, one per report, each line remembering its last run from the sheet's log and carrying
Preview and Print at its right; the builder is the planner's ruled sections ending in Save with
Preview beside it; the report itself is one paper page. It refuses the two tables with a More
chip, the white card around the builder, and the card around the printed report.

OWN-WORLD: The Student Planner as documented: planner white with the faint ruling. The shelf
(`.planner-main.report-shelf`): a Day row in pencil for each group; under it one `.report` line
per report under a hairline: the name at 650 in Ink (a saved report's name a Ballpoint link to
its page), then in pencil label type what the sheet's log knows ("Printed Wed 9/30 7:00 AM" with
OK in Checkmark Green; "Previewed …"; a failed or skipped run as its time alone with FAIL in Red
Pen on Highlighter Red or SKIP in pencil, since "Failed … FAIL" would say it twice; "Not run yet"
for a report the log has never seen), a saved report's "updated Tue
9/29" in pencil, and at the right Preview and Print as two stroke buttons; under a saved report's
line a pencil fold ("▸ More") holding Edit · CSV · JSON in ballpoint and Delete in Red Pen. One
"Refresh data first" tick line above the shelf; the starter sentence as one pencil line with its
button when the shelf is bare; the job card beneath. The builder (`form.builder-form`): three
ruled sections — What goes in (name, title, rows come from, rows from, the custom range; Kids and
Columns as hairline fieldsets with day-row legends), Order and filters (group by; Sort and
Filters), Chart and page — their fields label over control in the Settings grid, help in pencil,
closing on one filled Save with Preview as a stroke button beside it; the preview fills in
beneath as the paper page. The report's own page (`section.sec.report-page` in
`_report_preview.html`): one paper page in the day-box rule with the report's title along its
top edge and its tally after it ("· 12 rows · Rows from: the last 7 days"), the chart as a
figure flat on the page, each group a Day row over its table, "No rows matched this report." as
one pencil line; on paper the shell's head is hidden and the page prints as it reads. No box in
a box, no chip, no card. Recognisable with the words removed: two pencil labels over ruled lines
with a pair of small stroke buttons at each line's right; then, on another page, one ruled box
with a label along its top edge.

STORY: A parent opens Reports on Sunday, reads under Weekly grades that it printed Friday
morning and went OK, taps Preview, reads the paper page as it fills in beneath, taps Print, and
later opens More to export the CSV for the counsellor.

FIRST VIEWPORT: Reports and its intro, New report at the right. ☐ Refresh data first. BUILT IN;
Open Work Sheet · Printed Wed 9/30 7:00 AM · OK · [Preview] [Print]. YOURS; Weekly grades ·
updated Tue 9/29 · Printed Fri 9/25 6:00 AM · OK · [Preview] [Print]; ▸ More beneath; Quarter
recap · updated Mon 9/28 · Not run yet · [Preview] [Print]; ▸ More. "No saved reports yet." as a
pencil line under YOURS when there are none. The job card beneath when one runs. Primary: none on
the shelf; Save on the builder.

FORM: The shelf remembers, position 3 of the ordered grounded list, dealt as the lead by the
surface roll and locked by the maintainer over the shelf as ruled lines (1) and each report a
small paper page (4); seed key 5f1a8977; code-led, no image generation. Signature interaction:
Preview fills the job card in beneath the shelf and the line's last run updates on the next
visit; More folds open under its own line; nothing else moves.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the
verdict, DESIGN.md, and every shipping raster carrying its provenance.
