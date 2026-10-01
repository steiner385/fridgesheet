---
version: 1
slug: "fridgesheet-web-templates-settings-html"
primary_target: "fridgesheet/web/templates/settings.html"
related_targets: ["fridgesheet/web/templates/_late_rules_editor.html","fridgesheet/web/templates/_no_print_days_editor.html","fridgesheet/web/routes/settings.py"]
---

# Surface brief: Settings (the household's setup page)

Scope: `/settings` (settings.html with `_late_rules_editor.html`, `_no_print_days_editor.html`,
`_update_status.html`, `_update_button.html`, `_job.html`), the maintainer's own page, set up
once and returned to rarely; Operate mode. Audience: the parent who installed the app, on the
kitchen computer, sometimes a phone. Job: read the setup top to bottom, change a value, save
the file it lives in, and know which file each Save writes (maintainer, 2026-10-01: "the
household's setup page"; "one Save per file, said plainly"; the editors "keep the folds and
rows"). Proof: the current values of config.toml, late-rules.toml and no-print-days.txt as
the app reads them, the environment's overrides named beside their boxes, the update line.
Constraints: every field, name and route stays (`tests/test_web_settings_page.py`,
`test_update_card.py`); the sticky Save stays for the long first form; the editors' folds
close on a fresh load and open after a save or an error; the PIN hint sits beside the PIN
field, before the editors (#145); the builder on Reports shares `.settings-grid`; at most one
filled primary per form; 44px controls. The world is settled (DESIGN.md, The Student Planner);
this brief records composition only. Unresolved: whether Gradebook overrides (a table) becomes
lines; whether Schedules follows.

## Direction contract

THESIS: Settings is the planner's blocks in order: each topic a section with its ruled head,
its fields label over control on the ruling and its help in pencil beneath, the first form
ending in the sticky Save that names config.toml, and the two editors two more sections ending
in their own Save. It refuses the stack of white cards and the wizard.

OWN-WORLD: The Student Planner as documented: planner white with the faint ruling; a section is
an h3 at Title size over a hairline-free run of fields (`.settings-grid`, label at 550 over a
1px Stroke Grey control, 6px corners), help as Pencil Grey label-size lines, an environment
note the same in pencil; the three forms parted by the 1.5px printed rule, each closing on its
own Save (the primary Ballpoint fill for the sticky Save config.toml; the editors' Saves name
their file); the editors' rows as ruled lines under hairlines with their controls at the right;
the update line and the job card as they are; About a quiet fold. Recognisable with the words
removed: a column of ruled heads and fields on a ruled page, two printed rules, three Saves.

STORY: A parent opens Settings, reads down to the one thing to change, changes it, taps the
Save at the end of that form and reads "Saved config.toml"; the late-work rules and no-print
days sit under their own rules with their own Saves, folded until they are needed.

FIRST VIEWPORT: The title and one intro line ("Set up once; each part saves to the file it
names."). School login as a ruled head: username and password side by side, the pencil line
about the credential store. Printing and the report window: Printer, Days ahead, Overdue days,
Archive folder, then Nicknames, the two pencil lines (Schedules, automatic printing). Where you
are, Gradebook sources, Network and Updates follow as heads in one column; the sticky Save
config.toml (filled) with Test login beside it. A printed rule, then Late-work rules and Days
the sheet does not print with their folds and Saves, then About folded. One filled primary per
form.

FORM: Ruled sections with one Save each, position 1 of the ordered grounded list, dealt by the
surface roll and locked by the maintainer over the setup checklist (5) and one topic at a time
(7); seed key 40e594fb; code-led, no image generation. Signature interaction: a Save says which
file it wrote, in place; a fold opens in place; nothing else moves.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the
verdict, DESIGN.md, and every shipping raster carrying its provenance.
