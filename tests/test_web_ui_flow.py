"""Three places the page went somewhere the parent did not ask to go: Close on an item detail
opened from a question card (#126), the Plan tab's step links landing on Check-in (#128), and a
busy job card that never showed (#142)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.test_web_jobs import FakeActions, _worker
from tests.web_fixtures import LOCAL_HOST_HEADERS, app_for, seed

APP_JS = Path(__file__).resolve().parents[1] / "fridgesheet" / "web" / "static" / "app.js"


def _id(conn, name):
    return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]


def _setup(tmp_path, name="Participation"):
    conn = seed(tmp_path)
    iid = _id(conn, name)
    conn.close()
    return app_for(tmp_path), iid


def _htmx(page):
    return {"HX-Request": "true", "HX-Current-URL": f"http://127.0.0.1:8433{page}"}


# --- #126: Close on a detail opened from a question card puts the card back ---------------------

def test_add_a_note_tells_the_detail_which_card_it_replaced(tmp_path):
    c, pid = _setup(tmp_path)
    page = c.get("/questions").text
    assert f'hx-get="/items/{pid}?card=q-{pid}" hx-target="#q-{pid}"' in page


def test_a_detail_opened_from_a_card_keeps_its_id_and_closes_back_to_the_card(tmp_path):
    c, pid = _setup(tmp_path)
    detail = c.get(f"/items/{pid}?card=q-{pid}", headers=_htmx("/questions")).text
    assert re.match(rf'\s*<div class="card" id="q-{pid}" data-focus>', detail)
    close = re.search(r"<button[^>]*data-close-detail[^>]*>Close</button>", detail).group(0)
    assert f'hx-get="/items/{pid}/question?slot=q-{pid}"' in close
    assert f'hx-target="#q-{pid}"' in close and 'hx-swap="outerHTML"' in close


def test_the_question_card_comes_back_as_it_now_stands(tmp_path):
    c, pid = _setup(tmp_path)
    r = c.get(f"/items/{pid}/question?slot=q-{pid}", headers=_htmx("/questions"))
    assert r.status_code == 200
    assert f'<div class="q card" id="q-{pid}"' in r.text and "Was it handed in?" in r.text and "Add a note" in r.text
    assert c.get(f"/items/{pid}/question?slot=qc-{pid}").text.count(f'id="qc-{pid}"') == 1
    assert c.get("/items/99999/question").status_code == 404


def test_an_unknown_card_id_is_not_echoed_into_the_page(tmp_path):
    c, pid = _setup(tmp_path)
    for bad in ('x" onmouseover="alert(1)', "q-1; foo", f"qd-{pid}", "q-999999"):
        detail = c.get(f"/items/{pid}", params={"card": bad}).text
        assert 'onmouseover="' not in detail and "/question?slot=" not in detail
        assert re.match(r'\s*<div class="card" data-focus>', detail)


def test_a_flag_change_on_such_a_detail_keeps_the_way_back(tmp_path):
    c, pid = _setup(tmp_path)
    detail = c.get(f"/items/{pid}?card=q-{pid}").text
    assert f'<input type="hidden" name="card" value="q-{pid}">' in detail
    r = c.post(f"/items/{pid}/flag", data={"flag": "done", "card": f"q-{pid}"})
    assert f'id="q-{pid}"' in r.text and f"/items/{pid}/question?slot=q-{pid}" in r.text


def test_a_detail_in_a_table_row_keeps_the_js_close(tmp_path):
    c, pid = _setup(tmp_path)
    detail = c.get(f"/items/{pid}").text
    close = re.search(r"<button[^>]*data-close-detail[^>]*>Close</button>", detail).group(0)
    assert "hx-get" not in close


# --- #128: the Plan tab's step links come back to the Plan tab ---------------------------------

def _form(title="Pick up the form", **over):
    base = dict(title=title, family_account="", next_step="Bring it home", owner="Alex",
                planned_for="2026-09-16", minutes="", state="planned", position="", request_key=str(uuid4()), revision="0")
    base.update(over)
    return base


def _step(c):
    r = c.post("/kids/Alex/check-in/step", data=_form(), follow_redirects=False)
    assert r.status_code == 303
    return re.search(r"step\?step_id=(\d+)", c.get("/kids/Alex/plan").text).group(1)


def test_the_plan_tab_links_carry_the_plan_tab_as_return_to(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    sid = _step(c)
    plan = c.get("/kids/Alex/plan").text
    assert 'href="/kids/Alex/check-in/step?return_to=/kids/Alex/plan">Add a task' in plan
    assert f'href="/kids/Alex/check-in/step?step_id={sid}&amp;return_to=/kids/Alex/plan">Edit or complete step' in plan


def test_a_step_form_opened_from_the_plan_says_so_and_saves_back_to_it(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    sid = _step(c)
    form = c.get(f"/kids/Alex/check-in/step?step_id={sid}&return_to=/kids/Alex/plan").text
    assert '<a href="/kids/Alex/plan">← Alex’s plan</a>' in form
    assert 'name="return_to" value="/kids/Alex/plan"' in form
    r = c.post(f"/kids/Alex/check-in/step?step_id={sid}", data=_form(revision="1", return_to="/kids/Alex/plan"),
               follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/kids/Alex/plan?saved=1"
    r = c.post("/kids/Alex/check-in/step", data=_form(return_to="/kids/Alex/plan"), follow_redirects=False)
    assert r.headers["location"] == "/kids/Alex/plan?saved=1"


def test_removing_a_step_from_the_plan_returns_to_the_plan(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    sid = _step(c)
    form = c.get(f"/kids/Alex/check-in/step?step_id={sid}&return_to=/kids/Alex/plan").text
    remove = form.split('class="remove-step"', 1)[1]
    assert 'name="return_to" value="/kids/Alex/plan"' in remove
    r = c.post(f"/kids/Alex/check-in/step/{sid}/delete", data={"return_to": "/kids/Alex/plan"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/kids/Alex/plan?saved=1"


def test_the_check_in_still_returns_to_the_check_in(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    sid = _step(c)
    assert f"step_id={sid}&amp;return_to=/kids/Alex/check-in" in c.get("/kids/Alex/check-in").text
    form = c.get(f"/kids/Alex/check-in/step?step_id={sid}&return_to=/kids/Alex/check-in").text
    assert "← Alex’s check-in" in form
    r = c.post(f"/kids/Alex/check-in/step?step_id={sid}", data=_form(revision="1", return_to="/kids/Alex/check-in"),
               follow_redirects=False)
    assert r.headers["location"] == "/kids/Alex/check-in?saved=1#plan"
    r = c.post(f"/kids/Alex/check-in/step/{sid}/delete", follow_redirects=False)
    assert r.headers["location"] == "/kids/Alex/check-in?saved=1#plan"
    sid = _step(c)
    r = c.post(f"/kids/Alex/check-in/step/{sid}/delete", data={"return_to": "https://evil.example/"}, follow_redirects=False)
    assert r.headers["location"] == "/kids/Alex/check-in?saved=1#plan"


# --- #142: a busy job card is shown, not replaced by a generic error --------------------------

def test_a_busy_job_answers_409_with_an_html_card(tmp_path):
    application, w = _worker(tmp_path, FakeActions())
    c = TestClient(application, headers=LOCAL_HOST_HEADERS)
    assert c.post("/jobs/refresh").status_code == 200
    r = c.post("/jobs/doctor", headers={"HX-Request": "true"})
    assert r.status_code == 409 and r.headers["content-type"].startswith("text/html")
    assert 'id="job"' in r.text and "Busy:" in r.text and "is still running" in r.text


def _run_js(script: str) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    harness = """
var handlers = {};
var document = { addEventListener: function (n, f) { (handlers[n] = handlers[n] || []).push(f); },
                 getElementById: function () { return null; }, contains: function () { return true; } };
var window = { addEventListener: function () {} };
""" + APP_JS.read_text(encoding="utf-8") + "\n" + script
    done = subprocess.run([node, "-e", harness], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def test_app_js_swaps_a_409_html_card_and_keeps_json_409s_as_errors():
    result = _run_js("""
function ev(status, type, body) {
  var d = { xhr: { status: status, responseText: body, getResponseHeader: function (h) {
              return h.toLowerCase() === "content-type" ? type : null; } },
            shouldSwap: false, isError: true, serverResponse: body };
  handlers["htmx:beforeSwap"].forEach(function (f) { f({ detail: d }); });
  return { swap: d.shouldSwap, error: d.isError };
}
console.log(JSON.stringify({
  busy: ev(409, "text/html; charset=utf-8", '<div class="card job" id="job"><p class="warn">Busy: x</p></div>'),
  json: ev(409, "application/json", '{"detail":"Already in the plan for Mon 9/14."}'),
  other: ev(500, "text/html; charset=utf-8", "<html>boom</html>")
}));
""")
    assert result["busy"] == {"swap": True, "error": False}
    assert result["json"] == {"swap": False, "error": True}
    assert result["other"] == {"swap": False, "error": True}
