"""The banner that says the data is old, and the one number it shares with the runner."""
from __future__ import annotations

import json
import re
from datetime import timedelta

from fridgesheet import runner
from fridgesheet.web import db, staleness
from tests.web_fixtures import NOW, app_for, seed


def _refresh(conn, at, ok, sources=None):
    conn.execute("INSERT INTO refreshes(started_at, finished_at, sources, ok) VALUES (?,?,?,?)",
                 (at.isoformat(), at.isoformat(), json.dumps(sources or {"canvas": "ok", "hac": "ok"}), int(ok)))
    conn.commit()


def test_the_ceiling_is_the_runners_own_constant():
    """A banner with its own threshold could say the data is fine while the 2 PM print
    refuses it as stale -- the app disagreeing with itself about one fact."""
    assert staleness.CEILING_HOURS is runner.MAX_DATA_AGE_HOURS


def test_fresh_data_has_no_banner(tmp_path):
    conn = seed(tmp_path)
    assert staleness.check(conn, NOW) is None
    conn.close()


def test_data_past_the_ceiling_reports_its_age(tmp_path):
    conn = db.open_db(tmp_path)
    _refresh(conn, NOW - timedelta(hours=31), ok=True)
    s = staleness.check(conn, NOW)
    conn.close()
    assert s is not None and s.hours == 31


def test_it_names_the_last_successful_refresh_not_the_last_attempt(tmp_path):
    """On a host that has been failing to log in since Sunday, "refreshed this morning" is
    true and useless: what a parent needs is when the data is actually from."""
    conn = db.open_db(tmp_path)
    _refresh(conn, NOW - timedelta(hours=40), ok=True)
    _refresh(conn, NOW - timedelta(hours=2), ok=False, sources={"canvas": "login_required: expired", "hac": "ok"})
    s = staleness.check(conn, NOW)
    conn.close()
    assert s.hours == 40
    assert "login_required" in s.reason and "canvas" in s.reason.lower()


def test_no_refresh_at_all_is_stale_rather_than_a_crash(tmp_path):
    conn = db.open_db(tmp_path)
    s = staleness.check(conn, NOW)
    conn.close()
    assert s is not None and s.last_good is None


def test_the_banner_renders_on_every_page_when_the_data_is_old(tmp_path):
    conn = db.open_db(tmp_path)
    _refresh(conn, NOW - timedelta(hours=31), ok=True)
    conn.close()
    for path in ("/", "/runs", "/settings"):
        body = app_for(tmp_path).get(path).text
        assert "31 hours old" in body, path
        banner = re.search(r'<p class="stale">.*?</p>', body, re.S)
        assert banner and 'href="/">Refresh now</a>' in banner.group(0), path


def test_no_banner_when_the_data_is_fresh(tmp_path):
    seed(tmp_path).close()
    assert "hours old" not in app_for(tmp_path).get("/").text
