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


@pytest.mark.parametrize("flag", ["--no-hac", "--no-canvas", "--kids"])
def test_record_rejects_a_partial_pull_flag(tmp_path, monkeypatch, flag):
    """`--record` is the schedule's own path; a scheduled refresh has no use for a partial
    pull, and `web.actions.refresh` takes no such filters -- so these must be rejected, not
    silently ignored (the bug: the --record branch used to return before any of them were
    even read)."""
    from fridgesheet import cli

    def boom(**kw):
        raise AssertionError("actions.refresh must not run when a partial-pull flag is rejected")

    monkeypatch.setattr("fridgesheet.web.actions.refresh", boom)
    monkeypatch.setattr(cli, "load_settings", lambda: type("S", (), {"home": tmp_path})())
    with pytest.raises(SystemExit) as exc:
        cli.main(["refresh", "--record", flag])
    assert exc.value.code == 2


def test_record_alone_still_works(tmp_path, monkeypatch):
    from fridgesheet import cli
    seen = {}

    def fake_refresh(**kw):
        seen.update(kw)
        return type("R", (), {"ok": True, "message": "done", "refresh_id": 1})()

    monkeypatch.setattr("fridgesheet.web.actions.refresh", fake_refresh)
    monkeypatch.setattr(cli, "load_settings", lambda: type("S", (), {"home": tmp_path})())
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


def test_bare_refresh_runs_under_the_run_lock(tmp_path, monkeypatch):
    """`run` and `refresh --record` hold run.lock while Chromium is up; bare `refresh` -- the
    hand-written refresh timer's command -- did not, so it could overlap a scheduled print and
    two Chromiums fought over the one browser profile (#151)."""
    from fridgesheet import cli, runner
    seen = {}

    def collect(s, **kw):
        seen["locked"] = (tmp_path / runner.LOCK_NAME).is_file()
        return snapshot()

    monkeypatch.setattr(cli.collector, "collect", collect)
    monkeypatch.setattr(cli.collector, "summary", lambda *a, **k: {"sources": {"canvas": "ok"}})
    monkeypatch.setattr(cli, "load_settings", lambda: type("S", (), {"home": tmp_path})())
    with pytest.raises(SystemExit) as exc:
        cli.main(["refresh"])
    assert exc.value.code == 0 and seen["locked"] is True
    assert not (tmp_path / runner.LOCK_NAME).exists()              # and let go of afterwards


def test_bare_refresh_waits_a_bounded_time_then_says_so_in_one_line(tmp_path, monkeypatch, capsys):
    import time
    from fridgesheet import cli, collector, runner
    (tmp_path / runner.LOCK_NAME).write_text("1 deadbeef")           # a run in progress
    naps = []
    monkeypatch.setattr(time, "sleep", naps.append)
    monkeypatch.setattr(collector, "LOCK_WAIT_SECONDS", 12)
    monkeypatch.setattr(cli.collector, "collect", lambda *a, **k: pytest.fail("collect must not run over another run"))
    monkeypatch.setattr(cli, "load_settings", lambda: type("S", (), {"home": tmp_path})())
    with pytest.raises(SystemExit) as exc:
        cli.main(["refresh"])
    assert exc.value.code == 1
    err = capsys.readouterr().err.strip()
    assert "\n" not in err and "run.lock" in err
    assert sum(naps) == 12                                            # it waited the whole allowance, no longer
    assert (tmp_path / runner.LOCK_NAME).read_text() == "1 deadbeef"  # and did not touch the other run's lock


def test_collect_locked_goes_ahead_once_the_other_run_lets_go(tmp_path, monkeypatch):
    from fridgesheet import collector, runner
    lock = tmp_path / runner.LOCK_NAME
    lock.write_text("1 deadbeef")
    naps = []

    def sleep(n):
        naps.append(n)
        lock.unlink()

    monkeypatch.setattr(collector, "collect", lambda s, **kw: {"kw": kw})
    s = type("S", (), {"home": tmp_path})()
    assert collector.collect_locked(s, wait_seconds=30, sleep=sleep, include_hac=False) == {"kw": {"include_hac": False}}
    assert naps == [collector.LOCK_POLL_SECONDS] and not lock.exists()
