"""Settings as the household's setup page (the Student Planner; the surface brief in
.impeccable/surfaces/, 2026-10-01): the planner's blocks in order, each topic a ruled section
with its fields label over control and its help in pencil; the first form ends in the sticky
Save that names config.toml, the two editors are sections parted by the printed rule with a
Save each naming its file; the editors' rows are ruled lines; nothing boxed."""
from __future__ import annotations

import re
from pathlib import Path

from tests.web_fixtures import app_for, seed

CSS = (Path(__file__).resolve().parents[1] / "fridgesheet" / "web" / "static" / "app.css").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"no {selector} rule"
    return m.group(1)


def test_every_topic_is_a_ruled_section_and_nothing_on_the_page_is_a_card(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/settings").text
    main = body[body.index("<main"):]
    heads = re.findall(r'<section class="sec">\s*<div class="sec-head"><h3>([^<]*)</h3></div>', main)
    assert heads[:6] == ["School login", "Printing and the report window", "Where you are", "Gradebook sources", "Network", "Updates"]
    assert "About" in heads
    assert re.search(r'<form class="sec" id="late-rules"[^>]*>\s*<div class="sec-head"><h3>Late-work rules</h3></div>', main)
    assert re.search(r'<form class="sec" id="no-print-days"[^>]*>\s*<div class="sec-head"><h3>Days the sheet does not print</h3></div>', main)
    assert 'class="card"' not in main and 'class="card ' not in main                           # the job card is absent until a job runs
    assert '<p class="page-intro">Set up once; each part saves to the file it names.</p>' in main


def test_one_save_per_file_said_plainly_each_filled(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/settings").text
    main = body[body.index("<main"):]
    assert '<button class="primary">Save config.toml</button>' in main
    assert '<button class="primary">Save late-rules.toml</button>' in main and '<button class="primary">Save no-print-days.txt</button>' in main
    assert main.count('class="primary"') == 3                                                 # one per form, the forms parted by the printed rule
    assert 'class="danger"' not in main                                                       # Remove is a row edit, not a deletion: no Red Pen
    assert "Save above keeps the cards above it" not in main and 'class="field-help seam"' not in main
    assert main.index("Save config.toml") < main.index('class="settings-below"') < main.index("Save late-rules.toml") < main.index("Save no-print-days.txt")


def test_the_editors_fold_closed_and_their_rows_are_ruled_lines(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/settings").text
    assert re.search(r'<details class="fold" >\s*<summary>\d+ quarters? and \d+ rules? set — show and edit</summary>', body)
    assert re.search(r'<details class="skip-days" >\s*<summary>\d+ dates? set — show and edit</summary>', body)
    assert "Labor Day" in body and 'name="quarter_date" value="2026-10-15"' in body            # the rows are in the markup behind the folds
    row = _rule(".row")
    assert "border-bottom: 1px solid var(--rule)" in row and "background" not in row
    assert "margin-left: auto" in _rule(".row > button:first-of-type")
    fs = _rule("fieldset")
    assert "border: 0" in fs and "border-top: 1px solid var(--rule)" in fs and "border-radius" not in fs
    legend = _rule("legend")
    assert "text-transform: uppercase" in legend and "letter-spacing: .04em" in legend and "color: var(--muted)" in legend


def test_the_seam_is_the_printed_rule_and_the_folds_are_pencil_lines():
    below = _rule(".settings-below")
    assert "border-top: 1.5px solid var(--box)" in below and "max-width: 1100px" in below
    assert "border-top: 1.5px solid var(--box)" in _rule(".settings-below > form.sec + form.sec, .settings-below > form.sec + section.sec")
    assert "max-width: var(--measure)" in _rule(".settings-grid .field-help, .settings-grid .env-note")
    assert "white-space: nowrap" in _rule("#late-rules fieldset > label")
    assert "max-width: 1100px" in _rule(".settings-form")
    fold = _rule("details.skip-days > summary, details.fold > summary")
    assert "color: var(--muted)" in fold and "list-style: none" in fold and "font-weight: 400" in fold
    assert re.search(r"details\.skip-days > summary::before, details\.fold > summary::before\s*\{[^}]*content: \"▸ \"", CSS)


def test_a_notice_is_a_line_not_a_left_ruled_block(tmp_path):
    notice = _rule(".notice")
    assert "border-left" not in notice and "border-bottom: 1px solid var(--rule)" in notice
    warn = _rule(".notice.warn")
    assert "background: var(--warn-wash)" in warn and "color: var(--warn)" in warn
    seed(tmp_path).close()
    c = app_for(tmp_path)
    saved = c.post("/settings", data={"username": "parent@example.org", "password": "", "days_ahead": "14", "overdue_days": "14", "port": "8433"}).text
    assert re.search(r'<p class="notice[^"]*" role="(status|alert)">', saved)                   # saved or refused, said as a line


def test_the_linux_update_note_is_said_once(tmp_path, monkeypatch):
    from fridgesheet import host
    from tests.test_update_card import _app_with_update
    monkeypatch.setattr(host, "IS_WINDOWS", False)
    body = _app_with_update(tmp_path).get("/settings").text
    main = body[body.index("<main"):]
    assert main.count("git pull") == 1
