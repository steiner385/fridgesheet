---
version: 1
slug: "fridgesheet-web-templates-diagnostics-html"
primary_target: "fridgesheet/web/templates/diagnostics.html"
related_targets: ["fridgesheet/web/routes/diagnostics.py"]
---

# Surface brief: Diagnostics (the app's checkup)

Scope: `/diagnostics` (diagnostics.html), the APP page that shows the last doctor report and
runs a new one; Operate mode. Audience: a parent whose sheet stopped printing, following the
guide's "Start with Diagnostics → Run diagnostics. Any FAIL line is where to look"; the
maintainer reading a pasted report. Job: see at once whether anything failed and which check,
read its detail, run the checks again, and copy the report as a file when asked (maintainer,
2026-10-01: folded into the Schedules round; the report "as ruled lines with OK/FAIL as the Runs
words"; the failed-update card "as a ruled section"). Proof: `doctor.REPORT_NAME` read as text
(`OK    name: detail` / `FAIL  name: detail` lines, then "All checks passed" or "N check(s)
failed"), parsed into lines where a line fits that shape and kept as written where it does not;
the file's mtime as when it was checked; the `/jobs/doctor` button only with a worker; the job
card while it runs; `state.extra["last_update"]` for a failed update. Constraints: "Diagnostics
have not been run yet." before the first run; "FAIL  printers" and "1 check(s) failed" stay
readable in the page (the file's text is on the page, folded); the page action stays Run
diagnostics; a report another process is writing must not 500. The world is settled (DESIGN.md,
The Student Planner); this brief records composition only. Unresolved: whether the checks want
grouping by what they touch; whether the failed-update section should offer the installer as a
link.

## Direction contract

THESIS: Diagnostics is the app's checkup: one day row dated when the checks ran, with its tally,
over one planner line per check, each with its tick or red mark and its word on the highlighter
at the right; the report as a file folds beneath. It refuses the black console as the page.

OWN-WORLD: The Student Planner as documented: planner white with the faint ruling. The failed
update, when there is one, as a `section.sec` with its head ("The last update did not finish")
and two sentences, the paths in pencil. The job card while a run is going. Then
`.planner-main.checkup`: a Day row in pencil ("CHECKED THU 10/1 11:40 AM" with its tally after it
at 400: "· 12 checks · 1 failed", or "· 12 checks · all passed"); under it one `.check` line per
check under a hairline: a drawn SVG tick in Checkmark Green for a check that passed or a red
mark in Red Pen for one that failed, the check's name at 650 in Ink, its detail in pencil capped
at the measure, and OK or FAIL at the line's right as Runs draws the word (OK in Checkmark Green
on the bare page, FAIL in Red Pen on Highlighter Red); a line of the file the parser does not
recognise is kept as one pencil line. Beneath, a pencil fold ("▸ The report as a file") holding
the text as written in a plain monospace block on paper, not a black console. Before the first
run one pencil line: "Diagnostics have not been run yet." No box, no card, no console.
Recognisable with the words removed: a pencil label over ruled lines, a small mark at each
line's left and one highlighted word at the right where something failed.

STORY: A parent whose fridge is empty opens Diagnostics, reads the day row's "1 failed", sees the
red mark on printers with "none found" in pencil, plugs the printer in, taps Run diagnostics,
watches the job card fill in, and reads "all passed" on the new day row.

FIRST VIEWPORT: Diagnostics and its intro ("What the app can reach and what it cannot, checked on
this computer."), Run diagnostics at the right. CHECKED THU 10/1 11:40 AM · 12 checks · 1 failed;
✓ python · 3.12 · OK; ✓ home · writable · OK; ✗ printers · none found · FAIL; ✓ canvas · reachable
· OK; … ▸ The report as a file. Primary: none; Run diagnostics is a stroke button.

FORM: Each check a planner line, position 5 of the ordered grounded list, dealt as the lead by
the surface roll and locked by the maintainer over the checks as cells (6) and failures first
(2); seed key 36e2d9e9; code-led, no image generation. Signature interaction: Run diagnostics
fills the job card in and the page is reloaded with the new day row when the job is done;
nothing else moves.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the
verdict, DESIGN.md, and every shipping raster carrying its provenance.
