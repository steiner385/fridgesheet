"""Residual items from #2, #3, #4, #5 and #8 that a parent could meet: a Changes page that
could crash on mixed timestamps, a Settings save that could 500, a Diagnostics page that could
500, an evicted job's reload, scheduled runs labelled "cli", undated HAC keys that follow row
order, and the web lock's release order."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta

import pytest

from fridgesheet import config
from fridgesheet.web import ingest
from fridgesheet.web.stores import changes, flags
from tests.web_fixtures import NOW, TZ, app_for, seed


def _id(conn, name):
    return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]


def test_changes_sort_survives_a_timestamp_with_no_offset(tmp_path):
    """#5: the feed sorted on `e.at` directly; one naive timestamp among aware ones (a flag
    written without an offset) raised TypeError and took /changes down."""
    conn = seed(tmp_path)
    flags.set_flag(conn, _id(conn, "Lab notebook"), "done", now="2026-09-15T10:00:00")      # no offset
    feed = changes.since(conn, since=NOW - timedelta(days=30))
    conn.close()
    assert feed.total > 1
    assert any(e.at.tzinfo is None for e in feed) and any(e.at.tzinfo is not None for e in feed)


def test_a_settings_save_whose_reload_fails_shows_the_page_not_a_500(tmp_path, monkeypatch):
    """#4: `state.reload()` after a successful write could raise ConfigError (a hand edit the
    form does not own), and the parent got a bare 500."""
    seed(tmp_path).close()
    c = app_for(tmp_path)
    from fridgesheet.web import actions

    monkeypatch.setattr(actions, "save", lambda form, **k: actions.SaveResult(True, ["Saved."]))
    def broken():
        raise config.ConfigError("config.toml: [reports.open-work] time must be HH:MM (24-hour), got '25:00'")
    monkeypatch.setattr(c.app.state.fridgesheet, "reload", broken)
    r = c.post("/settings", data={"username": "u", "password": "p", "days_ahead": "14", "overdue_days": "14"})
    assert r.status_code == 200
    assert "time must be HH:MM" in r.text


def test_diagnostics_reads_a_report_with_bad_bytes(tmp_path):
    """#4: `doctor.txt` is written by a separate process; a byte that is not UTF-8 made the
    page a 500."""
    from fridgesheet import doctor
    seed(tmp_path).close()
    (tmp_path / doctor.REPORT_NAME).write_bytes(b"database: ok\nprinter: \xff\xfe broken\n")
    r = app_for(tmp_path).get("/diagnostics")
    assert r.status_code == 200 and "database: ok" in r.text


def test_an_evicted_jobs_reload_says_so_instead_of_a_404_page(tmp_path):
    """#4: the live log's `done` event fetches /jobs/<id>; once the job has been evicted that
    swapped a full 404 page into the card."""
    seed(tmp_path).close()
    r = app_for(tmp_path, worker=True).get("/jobs/999", headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert 'id="job"' in r.text and "no longer kept" in r.text
    assert app_for(tmp_path, worker=True).get("/jobs/999").status_code == 404     # not an htmx swap: still a 404


def test_a_scheduled_report_run_is_recorded_as_a_schedule(monkeypatch):
    """#8: `run` hard-coded trigger="cli", so every scheduled print read "cli" in Runs."""
    from fridgesheet import cli, runner
    seen = {}
    monkeypatch.setattr(runner, "run", lambda key, opts, settings: seen.setdefault("trigger", opts.trigger) and 0)
    monkeypatch.setattr(cli, "load_settings", lambda: None)
    with pytest.raises(SystemExit):
        cli.main(["run", "open-work", "--no-refresh", "--trigger", "schedule"])
    assert seen["trigger"] == "schedule"
    seen.clear()
    with pytest.raises(SystemExit):
        cli.main(["run", "open-work", "--no-refresh"])
    assert seen["trigger"] == "cli"


def test_undated_colliding_hac_rows_keep_their_keys_whatever_the_row_order():
    """#2: two same-named undated HAC rows were numbered in scrape order, so a gradebook that
    listed them the other way round swapped their keys -- and a flag or note moved to the
    other assignment."""
    a = {"name": "Reading check", "due": "", "assigned": "09/01/2026", "category": "Quiz", "points": 10.0, "score": None, "score_raw": ""}
    b = {"name": "Reading check", "due": "", "assigned": "09/08/2026", "category": "Quiz", "points": 20.0, "score": None, "score_raw": ""}
    one = {row["assigned"]: key for row, key in ingest._hac_only_rows([a, b], "English 9", TZ)}
    two = {row["assigned"]: key for row, key in ingest._hac_only_rows([b, a], "English 9", TZ)}
    assert one == two and len(set(one.values())) == 2


def test_the_web_lock_file_goes_before_the_lock_is_let_go(tmp_path, monkeypatch):
    """#3: `release` unlocked first and unlinked after, so a second server could take the lock
    in between and then have its lock file deleted under it. A file Windows will not delete
    (still open elsewhere) is not worth an exception on shutdown."""
    from fridgesheet.web import server
    lock = server.WebLock(tmp_path / "web.lock")
    assert lock.acquire()
    order = []
    real_unlock = server._unlock
    monkeypatch.setattr(server, "_unlock", lambda fd: (order.append(("unlock", (tmp_path / "web.lock").exists())), real_unlock(fd)))
    lock.release()
    if sys.platform == "win32":                             # an open file cannot be deleted there
        assert order == [("unlock", True)] and not (tmp_path / "web.lock").exists()
    else:
        assert order == [("unlock", False)]                 # the file was already gone when it unlocked

    lock2 = server.WebLock(tmp_path / "web.lock")
    assert lock2.acquire()
    monkeypatch.setattr(type(lock2.path), "unlink", lambda self, missing_ok=False: (_ for _ in ()).throw(PermissionError("in use")))
    lock2.release()                                         # does not raise


def test_a_time_zone_change_reaches_the_clock_without_a_restart(tmp_path):
    """The in-app scheduler builds its slots from `state.now()`: an app whose clock kept the
    start-up zone after a Settings save would fire in the old zone while the runner judged
    the slot in the new one -- fire early, SKIP, record the slot, print nothing."""
    from zoneinfo import ZoneInfo
    from fridgesheet.web.app import create_app
    seed(tmp_path).close()
    config.save_config_doc(tmp_path / "config.toml", {"general": {"timezone": "America/New_York"}})
    s = config.Settings(home=tmp_path)
    config.settings_from_doc(config.load_config_doc(tmp_path / "config.toml"), s)
    state = create_app(s, home=tmp_path).state.fridgesheet
    assert state.now().tzinfo == ZoneInfo("America/New_York")
    config.save_config_doc(tmp_path / "config.toml", {"general": {"timezone": "America/Los_Angeles"}})
    state.reload()
    assert state.now().tzinfo == ZoneInfo("America/Los_Angeles")
