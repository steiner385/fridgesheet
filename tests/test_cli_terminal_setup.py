"""#154: a terminal-only or headless setup can finish.

`fridgesheet check` leaves the same `login-ok.txt` the web Test login leaves; `schedule install`
turns a schedule on in config.toml with no login gate (the Schedules page has none either, since
the server's own clock fires schedules) and accepts `--force` for scripts written for the old
gate; `web --help` says how to run on a machine with no desktop.

Nothing here launches Chromium: the session helpers `check` calls are replaced with fakes.
Nothing reaches systemctl or schtasks: `install` writes config.toml and nothing else.
"""
from __future__ import annotations

import contextlib
import tomllib
from datetime import datetime

import pytest

from fridgesheet import cli, config
from fridgesheet.web import actions


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


def test_a_failed_check_removes_the_stamp(monkeypatch, tmp_path, capsys):
    (tmp_path / actions.LOGIN_STAMP).write_text("2026-09-01T00:00:00-04:00")
    _fake_sites(monkeypatch, tmp_path, hac_ok=False)
    with pytest.raises(SystemExit) as e:
        cli.main(["check"])
    assert e.value.code == 1
    assert not (tmp_path / actions.LOGIN_STAMP).exists()


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


# --- `schedule install` turns a schedule on, with no login gate -----------------------------

@pytest.fixture
def cli_home(tmp_path, monkeypatch):
    def load():
        s = config.Settings(home=tmp_path)
        config.settings_from_doc(config.load_config_doc(tmp_path / "config.toml"), s)
        return s
    monkeypatch.setattr(cli, "load_settings", load)
    return tmp_path


def _doc(home):
    return tomllib.loads((home / "config.toml").read_text())


def _enabled(home, key):
    doc = _doc(home)
    return (doc["refresh"] if key == "data-refresh" else doc["reports"][key])["enabled"]


@pytest.mark.parametrize("key", ["open-work", "data-refresh"])
def test_schedule_install_needs_no_login(cli_home, capsys, key):
    """No stamp, no `--force`: `install` still turns the schedule on. The server's clock fires
    it, and the Schedules page has no login gate either, so the terminal must not have one."""
    home = cli_home
    assert not (home / actions.LOGIN_STAMP).exists()
    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "install", key])
    assert e.value.code == 0
    assert _enabled(home, key) is True
    out = capsys.readouterr().out
    assert f"{key}: turned on in config.toml" in out and f"{key}: next" in out


@pytest.mark.parametrize("key", ["open-work", "data-refresh"])
def test_schedule_install_after_a_passed_login_is_the_same(cli_home, capsys, key):
    home = cli_home
    actions.record_login(home, True)
    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "install", key])
    assert e.value.code == 0
    assert _enabled(home, key) is True


def test_schedule_install_accepts_force_and_ignores_it(cli_home, capsys):
    """`--force` was #154's way past the old gate; upstream docs and scripts still pass it."""
    home = cli_home
    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "install", "open-work", "--force"])
    assert e.value.code == 0
    assert _enabled(home, "open-work") is True


def test_schedule_install_of_a_report_turns_the_refresh_on_too(cli_home, capsys):
    """The Schedules page's #120/#171 rule, from the terminal: a scheduled report prints from
    the last refresh and refuses one a day old, so turning a report on with the refresh off
    turns the refresh on in the same breath and says so, in the page's words."""
    from fridgesheet.web import schedules as page
    home = cli_home
    (home / "config.toml").write_text('[refresh]\nenabled = false\nevery_hours = 2\n')
    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "install", "open-work"])
    assert e.value.code == 0
    assert _enabled(home, "open-work") is True and _enabled(home, "data-refresh") is True
    assert _doc(home)["refresh"]["every_hours"] == 2     # the rest of [refresh] is kept
    out = capsys.readouterr().out
    s = config.Settings(home=home)
    config.settings_from_doc(config.load_config_doc(home / "config.toml"), s)
    assert "every 2 hours" in page.refresh_turned_on(s.refresh)
    assert page.refresh_turned_on(s.refresh) in out and "data-refresh: next" in out


def test_schedule_install_of_a_report_leaves_an_on_refresh_alone(cli_home, capsys):
    home = cli_home
    (home / "config.toml").write_text('[refresh]\nenabled = true\n')
    with pytest.raises(SystemExit):
        cli.main(["schedule", "install", "open-work"])
    assert "Turned on the data refresh" not in capsys.readouterr().out


def test_schedule_remove_and_show_never_ask_for_the_stamp(cli_home, capsys):
    """Taking a schedule away or looking at it needs no login."""
    for action in ("remove", "show"):
        with pytest.raises(SystemExit) as e:
            cli.main(["schedule", action, "open-work"])
        assert e.value.code == 0, action


def test_schedule_parser_offers_install_remove_and_show(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "enable"])
    assert e.value.code == 2
    # argparse quotes the choices up to 3.12.7 ("choose from 'install', 'remove', 'show'") and
    # stops quoting them from 3.12.8 / 3.13 ("choose from install, remove, show"); CI's 3.12
    # is whichever patch release the runner has, so the assertion names the choices, not the
    # punctuation around them.
    err = capsys.readouterr().err
    assert "invalid choice: 'enable'" in err
    choices = err.split("choose from", 1)[1].replace("'", "").replace(")", "")
    assert [c.strip() for c in choices.split(",")] == ["install", "remove", "show"]


# --- `web --help` -----------------------------------------------------------------------------

def test_web_help_says_how_to_run_without_a_desktop(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["web", "--help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert "--no-browser" in out and "no desktop" in out
