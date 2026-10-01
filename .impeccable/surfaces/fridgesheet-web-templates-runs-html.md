---
version: 1
slug: "fridgesheet-web-templates-runs-html"
primary_target: "fridgesheet/web/templates/runs.html"
related_targets: ["fridgesheet/web/routes/runs.py","fridgesheet/web/stores/runs.py"]
---

# Surface brief: Runs (the sheet's own log)

Scope: `/runs` (runs.html), the APP page that says whether the sheet printed, and if not why;
Operate mode. Audience: a parent asking "did it print this morning?" after a quiet fridge; the
maintainer checking a schedule took. Job: find this morning's run in a glance, read why one
failed, open the PDF a run kept, print it again as it was (maintainer, 2026-10-01: "the sheet's
own log"; the outcome "the sheet's word on its highlighter"; the rows "days, like Changes").
Proof: `runs.recent` (the last 100), one line per run as the store records it; who started it in
words (`trigger_label`); the PDF link on exactly the runs whose file is on disk (`safe_pdf`);
Reprint only on an OK run with a PDF when a worker exists, posting the run's own id
(`/jobs/reprint`, #143). Constraints: the job card (`_job.html`) stays above the log and keeps its
badge; an unknown trigger is shown as written; a saved report's run says the parent's title, not
`view:<id>`; the page carries no tier and no filters. The world is settled (DESIGN.md, The
Student Planner); this brief records composition only. Unresolved: whether a hundred runs over
fifty days wants a fold per older day; whether the job card follows the log into the world.

## Direction contract

THESIS: Runs is the planner's log turned to the sheet: each day a day row with its tally over
the day's runs, each run one ruled line with its outcome as a word on the highlighter at the
right. It refuses the four-column table with a chip per row and a console of raw messages.

OWN-WORLD: The Student Planner as documented: planner white with the faint ruling; the job card
first when one is running; then `.planner-main.run-log` at the log's width: each day a Day row
in pencil (WED 9/30) with its tally after it at 400 in sentence case ("· 2 runs · 1 failed";
"· 1 run" on a clean day; skipped runs counted after failed); under it the lines, one per run
under a hairline: the time in pencil label type, the report's title at 650 in ink, who started it
in the pencil meta ("On a schedule", "In the app", "At a terminal"), the message in ink, and at
the line's right the outcome word — OK in Checkmark Green on the bare page, FAIL in Red Pen on
the red highlighter (the header's badge wears the same two colours), SKIP in pencil; beneath the
message, the foot links in ballpoint: "open the PDF" and the Reprint button, 44px under a finger.
No box, no chip, no table. Recognisable with the words removed: day labels over ruled lines,
one highlighted word at each line's right edge where something failed.

STORY: A parent finds nothing on the fridge, opens Runs, reads this morning's day row (2 runs · 1
failed), sees the 7:52 line's FAIL on red with its reason and the 7:00 line's OK, opens that run's
PDF, and prints it again with one tap on Reprint.

FIRST VIEWPORT: The title and its intro ("Every sheet, report and refresh the app has run, newest
first, with why one failed."); the job card if one runs. WED 9/30 · 2 runs · 1 failed; 7:52 AM ·
Open Work Sheet · In the app · no snapshot on disk and refresh failed · FAIL; 7:00 AM · Open Work
Sheet · On a schedule · Printed 1 page: Alex=3 Sam=2 · OK, with open the PDF · Reprint beneath.
TUE 9/29 · 1 run · 1 failed; 6:00 AM · Refresh · On a schedule · HAC: timed out waiting for the
gradebook · FAIL. "No runs yet." as one pencil line when nothing has run. No primary on this page.

FORM: Days, like Changes, position 3 of the ordered grounded list, dealt as the lead by the
surface roll and locked by the maintainer over the sheets' days as cells (7) and failures first
(4); seed key c219c7a9; code-led, no image generation. Signature interaction: Reprint asks once
and the job card fills in above the log; open the PDF opens the file; nothing else moves.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the
verdict, DESIGN.md, and every shipping raster carrying its provenance.
