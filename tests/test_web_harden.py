"""Print now from the 2026-09-29 critique (.impeccable/critique/): the action the product exists
for asks in its card, and a job's log sits behind "Details" under one sentence."""
from __future__ import annotations

import re
from pathlib import Path

from tests.web_fixtures import app_for, seed

WEB = Path(__file__).resolve().parents[1] / "fridgesheet" / "web"
CSS = (WEB / "static" / "app.css").read_text(encoding="utf-8")
JS = (WEB / "static" / "app.js").read_text(encoding="utf-8")


def test_print_now_is_a_two_step_in_the_card_with_one_filled_button(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path, worker=True)
    page = c.get("/").text
    box = re.search(r'<details class="print-confirm"><summary>Print now</summary>(.*?)</details>', page, re.S).group(1)
    assert re.search(r'<p class="ask-line">Print today\'s sheet on [^<]+\?</p>', box)
    assert re.search(r'<button class="primary" hx-post="/jobs/print"[^>]*>Print</button>', box)
    assert '<button type="button" class="link" data-close-details>Cancel</button>' in box
    assert "hx-confirm" not in page
    assert page.count('class="primary"') == 1


def test_cancel_closes_the_fold_and_the_summary_wears_the_primary_look():
    assert re.search(r'closest\("\[data-close-details\]"\)', JS) and 'removeAttribute("open")' in JS
    assert re.search(r"\.print-confirm > summary\s*\{[^}]*background: var\(--accent\)", CSS)
    assert re.search(r"\.print-confirm\[open\] > summary\s*\{[^}]*background: var\(--paper\)", CSS)


def test_a_finished_job_is_a_sentence_and_a_closed_details_fold(tmp_path):
    from tests.test_web_jobs import FakeActions, _tc, _worker
    application, w = _worker(tmp_path, FakeActions())
    c = _tc(application)
    running = c.post("/jobs/refresh").text
    assert "Working on it, started" in running and '<details class="job-log" open>' in running
    w.run_pending()
    done = c.get(f"/jobs/{w.last.id}").text
    assert '<details class="job-log"><summary>Details</summary><pre class="log">' in done
    assert "Working on it" not in done and "job " + str(w.last.id) not in done.split("<h3>")[1].split("</h3>")[0]
