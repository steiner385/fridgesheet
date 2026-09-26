"""#11 items 13 and 20: two pages that spoke to their author rather than to a parent.

Reports showed a "Key" column of internal strings (`open-work`, `view:3`), offered a button
called "Add the starter reports" with nothing saying what a starter report is, and gave only
*Print* where the Dashboard gives *Preview* and *Print* -- so the one page whose whole job is
building a report was also the one place a parent could not look before spending paper.

Runs labelled every row `web`, `cli` or `schedule` under a heading reading "How".
"""
from __future__ import annotations

import json
import re

from fridgesheet.web import db
from fridgesheet.web.stores import reports as reportstore, runs
from tests.web_fixtures import app_for, seed

MINE = {"title": "Mine", "source": "items", "columns": ["kid", "name"]}


def _with_report(home):
    conn = seed(home)
    rid = reportstore.create(conn, "Mine", json.dumps(MINE), now="2026-09-15T08:00:00-04:00")
    conn.close()
    return rid


# --- item 13: the Reports page -------------------------------------------------------------

def test_the_reports_page_has_no_key_column(tmp_path):
    """`open-work` and `view:3` are what the scheduler and the CLI call a report. They are
    not what a parent calls one, and the page already shows the name."""
    _with_report(tmp_path)
    body = app_for(tmp_path).get("/reports").text
    assert ">Key<" not in body


def test_the_key_is_still_reachable_for_the_command_line(tmp_path):
    """Dropping the column must not lose the string: `fridgesheet run <key>` is documented in
    the README, so the page keeps it as the report's title attribute."""
    rid = _with_report(tmp_path)
    body = app_for(tmp_path).get("/reports").text
    assert f'title="view:{rid}"' in body
    assert 'title="open-work"' in body


def test_the_starter_reports_button_says_what_it_will_add(tmp_path):
    """A button that writes four rows into the parent's own list should name them first."""
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/reports").text
    assert "Add the starter reports" in body
    for name, _ in reportstore.TEMPLATES:
        assert name in body, name


def test_the_starter_button_is_gone_once_there_are_reports(tmp_path):
    _with_report(tmp_path)
    body = app_for(tmp_path).get("/reports").text
    assert "Add the starter reports" not in body


def test_every_report_offers_preview_before_print(tmp_path):
    """The Dashboard's pairing, on the page that builds the things: look at it first, and
    the button that spends paper is not the only button there is."""
    rid = _with_report(tmp_path)
    body = app_for(tmp_path, worker=True).get("/reports").text
    assert body.count('hx-post="/jobs/preview"') == 2      # the built-in sheet and the saved one
    assert body.count('hx-post="/jobs/print"') == 2
    assert body.index('hx-post="/jobs/preview"') < body.index('hx-post="/jobs/print"')
    previews = re.findall(r'hx-post="/jobs/preview".*?</form>', body, re.S)
    assert any('value="open-work"' in f for f in previews)
    assert any(f'value="view:{rid}"' in f for f in previews)


def test_preview_is_not_offered_without_a_worker(tmp_path):
    """Same rule the Print button already followed: no jobs worker, no job buttons."""
    _with_report(tmp_path)
    body = app_for(tmp_path).get("/reports").text
    assert 'hx-post="/jobs/preview"' not in body


def test_previewing_a_saved_report_runs_that_report(tmp_path):
    rid = _with_report(tmp_path)
    c = app_for(tmp_path, worker=True)
    r = c.post("/jobs/preview", data={"report": f"view:{rid}"})
    assert r.status_code == 200


# --- item 20: the Runs page's "How" column --------------------------------------------------

def test_runs_says_who_started_it_in_words(tmp_path):
    conn = seed(tmp_path)
    for trigger in ("web", "cli", "schedule"):
        runs.record(conn, "open-work", f"2026-09-15T1{len(trigger)}:00:00-04:00",
                    "2026-09-15T14:02:00-04:00", trigger, "OK", "2p")
    conn.close()
    body = app_for(tmp_path).get("/runs").text
    assert ">How<" not in body and ">Started by<" not in body       # under the report's name since #187, not a column
    assert body.count('<small class="by">') == 3
    for jargon in (">web<", ">cli<", ">schedule<"):
        assert jargon not in body, jargon
    for words in ("In the app", "At a terminal", "On a schedule"):
        assert words in body, words


def test_an_unknown_trigger_is_shown_rather_than_swallowed(tmp_path):
    """A row written by a version that knows a trigger this one does not is still a row a
    parent should be able to read; the raw word beats a blank cell."""
    conn = seed(tmp_path)
    runs.record(conn, "open-work", "2026-09-15T14:00:00-04:00", "2026-09-15T14:02:00-04:00",
                "carrier-pigeon", "OK", "2p")
    conn.close()
    assert "carrier-pigeon" in app_for(tmp_path).get("/runs").text


def test_the_trigger_labels_cover_every_trigger_the_runner_declares():
    """`RunOptions.trigger` carries the list of triggers as a comment beside the field; a new
    one added there without a label here would print as a bare word to a parent."""
    from pathlib import Path
    src = (Path(runs.__file__).parents[2] / "runner.py").read_text(encoding="utf-8")
    declared = re.search(r'trigger: str = "cli"\s*#\s*([\w |]+)', src).group(1)
    assert set(runs.TRIGGER_LABELS) == {t.strip() for t in declared.split("|")}
