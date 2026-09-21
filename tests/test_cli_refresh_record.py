"""`refresh --record` -- what a scheduled data refresh actually runs.

Bare `refresh` writes snapshot.json and stops; it does not ingest into the database the web
app renders from. A schedule wired to it would fire, log success, and leave the kiosk showing
the same numbers, which is exactly the failure this flag exists to prevent.
"""
from __future__ import annotations

import pytest

from fridgesheet.web import db
from fridgesheet.web.stores import runs
from tests.web_fixtures import snapshot


def test_refresh_record_ingests_and_records_with_the_schedule_trigger(tmp_path, monkeypatch):
    from fridgesheet.web import actions
    lines = []
    result = actions.refresh(home=tmp_path, log=lines.append, collect=lambda s: snapshot(),
                             trigger="schedule")
    assert result.ok, result.message
    conn = db.open_db(tmp_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] > 0   # it ingested
        row = runs.latest(conn)
        assert row["report_key"] == "refresh" and row["trigger"] == "schedule"
    finally:
        conn.close()


def test_the_default_trigger_is_still_web(tmp_path):
    """The Refresh now button must keep saying what it always said."""
    from fridgesheet.web import actions
    actions.refresh(home=tmp_path, log=lambda _m: None, collect=lambda s: snapshot())
    conn = db.open_db(tmp_path)
    try:
        assert runs.latest(conn)["trigger"] == "web"
    finally:
        conn.close()


def test_the_cli_flag_is_wired_to_that_function(monkeypatch, tmp_path):
    from fridgesheet import cli
    seen = {}

    def fake_refresh(**kw):
        seen.update(kw)
        return type("R", (), {"ok": True, "message": "done", "refresh_id": 1})()

    monkeypatch.setattr("fridgesheet.web.actions.refresh", fake_refresh)
    monkeypatch.setattr(cli, "load_settings", lambda: type("S", (), {"home": tmp_path})())
    # `cli.main` ends in `sys.exit(args.fn(args))` (cli.py:461): it raises, never returns.
    with pytest.raises(SystemExit) as exc:
        cli.main(["refresh", "--record"])
    assert exc.value.code == 0
    assert seen["trigger"] == "schedule"


def test_bare_refresh_still_does_not_ingest(tmp_path, monkeypatch):
    from fridgesheet import cli
    called = {"actions": False}
    monkeypatch.setattr("fridgesheet.web.actions.refresh",
                        lambda **kw: called.__setitem__("actions", True))
    monkeypatch.setattr(cli.collector, "collect", lambda *a, **k: snapshot())
    monkeypatch.setattr(cli.collector, "summary", lambda *a, **k: {"sources": {"canvas": "ok"}})
    monkeypatch.setattr(cli, "load_settings", lambda: type("S", (), {"home": tmp_path})())
    with pytest.raises(SystemExit):
        cli.main(["refresh"])
    assert called["actions"] is False
