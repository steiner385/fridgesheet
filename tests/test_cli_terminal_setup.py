"""#154: a terminal-only or headless setup can finish.

`fridgesheet check` leaves the same `login-ok.txt` the web Test login leaves, so the Schedules
page (and `schedule install`) stop saying "nothing is installed yet" after a CLI setup;
`schedule install` applies the page's own gate unless `--force`; `web --help` says how to run
on a machine with no desktop.

Nothing here launches Chromium: the session helpers `check` calls are replaced with fakes.
Nothing reaches systemctl: the scheduler is `FakeScheduling`.
"""
from __future__ import annotations

import contextlib
from datetime import datetime

import pytest

from fridgesheet import cli, config
from fridgesheet.host import scheduling as _real_scheduling  # noqa: F401  makes `fridgesheet.host.scheduling` patchable
from fridgesheet.web import actions, schedules
from tests.web_fixtures import FakeScheduling


def _fake_sites(monkeypatch, home, *, canvas_ok=True, hac_ok=True):
    """`check` against two fake sites: `browser` yields a bare object, `ensure_*` pass or
    raise the way the real ones do, and nothing is launched."""
    monkeypatch.setattr(cli, "load_settings", lambda: config.Settings(home=home))
    monkeypatch.setattr(cli, "browser", lambda s, **kw: contextlib.nullcontext(object()))

    def site(ok):
        def ensure(ctx, s):
            if not ok:
                raise RuntimeError("LoginRequired: OneLogin did not redirect")
        return ensure
    monkeypatch.setattr(cli, "ensure_canvas", site(canvas_ok))
    monkeypatch.setattr(cli, "ensure_hac", site(hac_ok))


# --- `check` writes the stamp --------------------------------------------------------------

def test_a_passing_check_writes_the_stamp_test_login_writes(monkeypatch, tmp_path, capsys):
    _fake_sites(monkeypatch, tmp_path)
    with pytest.raises(SystemExit) as e:
        cli.main(["check"])
    assert e.value.code == 0
    stamp = tmp_path / actions.LOGIN_STAMP
    assert stamp.is_file()
    datetime.fromisoformat(stamp.read_text())        # the same shape Test login writes
    assert actions.login_passed(tmp_path)              # ... and the gate the page applies reads it


def test_a_failed_check_removes_the_stamp(monkeypatch, tmp_path, capsys):
    (tmp_path / actions.LOGIN_STAMP).write_text("2026-09-01T00:00:00-04:00")
    _fake_sites(monkeypatch, tmp_path, hac_ok=False)
    with pytest.raises(SystemExit) as e:
        cli.main(["check"])
    assert e.value.code == 1
    assert not (tmp_path / actions.LOGIN_STAMP).exists()
    assert not actions.login_passed(tmp_path)


def test_check_and_test_login_share_one_stamp_helper(monkeypatch, tmp_path, capsys):
    """One helper writes and removes the stamp, whoever passed the login: the CLI and the
    page cannot drift apart on the file name, its contents or when it is removed."""
    calls = []
    monkeypatch.setattr(actions, "record_login", lambda home, ok, **kw: calls.append((home, ok)))
    _fake_sites(monkeypatch, tmp_path)
    with pytest.raises(SystemExit):
        cli.main(["check"])
    actions.test_login(home=tmp_path, log=lambda line: None, settings=config.Settings(home=tmp_path),
                       check=lambda s, log: {"Canvas": None, "HAC": "LoginRequired"})
    assert calls == [(tmp_path, True), (tmp_path, False)]


def test_the_stamp_helper_writes_on_success_and_removes_on_failure(tmp_path):
    now = datetime(2026, 9, 25, 7, 0).astimezone()
    actions.record_login(tmp_path, True, now=now)
    assert (tmp_path / actions.LOGIN_STAMP).read_text() == now.isoformat()
    actions.record_login(tmp_path, False)
    assert not (tmp_path / actions.LOGIN_STAMP).exists()
    actions.record_login(tmp_path, False)              # already gone: still not an error


def test_the_page_and_the_cli_read_one_gate(tmp_path):
    """`schedules.LOGIN_STAMP` is the file `actions` writes, not a second spelling of it."""
    assert schedules.LOGIN_STAMP is actions.LOGIN_STAMP


# --- `schedule install` applies the page's gate ---------------------------------------------

@pytest.fixture
def cli_home(tmp_path, monkeypatch):
    sched = FakeScheduling()
    sched.display_name = lambda key: f"fridgesheet-{key}"
    monkeypatch.setattr(cli, "load_settings", lambda: config.Settings(home=tmp_path))
    monkeypatch.setattr("fridgesheet.host.scheduling", sched)
    return tmp_path, sched


@pytest.mark.parametrize("key", ["open-work", "data-refresh"])
def test_schedule_install_refuses_until_a_login_has_passed(cli_home, capsys, key):
    home, sched = cli_home
    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "install", key])
    assert e.value.code == 1
    assert sched.installed == []
    assert not (home / "config.toml").exists()          # nothing recorded as enabled either
    err = capsys.readouterr().err.strip()
    assert "\n" not in err                              # one line
    assert "fridgesheet check" in err and "Test login" in err and "--force" in err


@pytest.mark.parametrize("key", ["open-work", "data-refresh"])
def test_schedule_install_proceeds_once_the_stamp_is_there(cli_home, capsys, key):
    home, sched = cli_home
    actions.record_login(home, True)
    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "install", key])
    assert e.value.code == 0
    assert sched.installed[0]["key"] == key


def test_schedule_install_force_skips_the_gate(cli_home, capsys):
    home, sched = cli_home
    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "install", "open-work", "--force"])
    assert e.value.code == 0
    assert sched.installed[0]["key"] == "open-work"


def test_schedule_remove_and_show_never_ask_for_the_stamp(cli_home, capsys):
    """The gate is about installing a timer that would then fail every run; taking one away
    or looking at it needs no login."""
    home, sched = cli_home
    for action in ("remove", "show"):
        with pytest.raises(SystemExit) as e:
            cli.main(["schedule", action, "open-work"])
        assert e.value.code == 0, action


# --- `web --help` -----------------------------------------------------------------------------

def test_web_help_says_how_to_run_without_a_desktop(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["web", "--help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert "--no-browser" in out and "no desktop" in out
