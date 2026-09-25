"""#144: a config.toml that does not read is a message, never a 500 or a traceback.
#146: a schedule can always be turned off, and the CLI keeps config.toml in step with the host.

Every scheduler here is `FakeScheduling` (on `state.extra` for the pages, monkeypatched over
`fridgesheet.host.scheduling` for the CLI), so nothing reaches systemctl or schtasks."""
from __future__ import annotations

import tomllib

import pytest
from fastapi.testclient import TestClient

from fridgesheet import cli, config, host
from fridgesheet.host import scheduling as _real_scheduling  # noqa: F401  makes `fridgesheet.host.scheduling` patchable
from fridgesheet.web import app as webapp, schedules
from tests.web_fixtures import LOCAL_HOST_HEADERS, FakeScheduling, seed

BAD_TIME = '[reports.open-work]\ntime = "25:99"\n'


def _client(home, sched=None):
    seed(home).close()
    (home / "login-ok.txt").write_text("ok")
    application = webapp.create_app(config.Settings(home=home), worker=False)
    extra = application.state.fridgesheet.extra
    extra["scheduling"] = sched or FakeScheduling()
    extra["printers"] = ["Brother"]
    extra["credstore"] = object()           # never reached: nothing here stores a password
    extra["describe_service"] = lambda: host.ServiceInfo("systemd", installed=True, active=True, detail="stub")
    return TestClient(application, headers=LOCAL_HOST_HEADERS)


# --- #144: the pages --------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/settings", "/schedules"])
def test_a_bad_setting_renders_the_page_with_the_setting_named(tmp_path, path):
    c = _client(tmp_path)
    (tmp_path / "config.toml").write_text(BAD_TIME, encoding="utf-8")
    r = c.get(path)
    assert r.status_code == 200
    assert "[reports.open-work] time" in r.text and "25:99" in r.text
    assert "config.toml" in r.text


@pytest.mark.parametrize("path", ["/settings", "/schedules"])
def test_a_config_toml_that_does_not_parse_renders_the_page(tmp_path, path):
    c = _client(tmp_path)
    (tmp_path / "config.toml").write_text("[reports.open-work\ntime = 14:00\n", encoding="utf-8")
    r = c.get(path)
    assert r.status_code == 200 and "cannot parse" in r.text


def test_the_settings_page_offers_no_form_that_could_save_defaults_over_the_file(tmp_path):
    """The form's values could not be read, so a Save from it would write placeholders over
    whatever the parent had -- the form is withheld until the file reads again."""
    c = _client(tmp_path)
    (tmp_path / "config.toml").write_text(BAD_TIME, encoding="utf-8")
    body = c.get("/settings").text
    assert 'action="/settings"' not in body


def test_posting_a_schedule_with_a_broken_file_is_a_message_not_a_500(tmp_path):
    sched = FakeScheduling()
    c = _client(tmp_path, sched)
    (tmp_path / "config.toml").write_text("[reports.open-work\n", encoding="utf-8")
    r = c.post("/schedules", data={"key": "open-work", "enabled": "on", "time": "14:00", "days": ["Mon"], "prints": "on"})
    assert r.status_code == 200 and "cannot parse" in r.text
    r = c.post("/schedules/refresh", data={"enabled": "on", "every_hours": "3", "start": "06:00", "end": "21:00", "days": ["Mon"]})
    assert r.status_code == 200 and "cannot parse" in r.text
    assert not sched.installed


# --- #144: the CLI ----------------------------------------------------------------------

def test_the_cli_says_one_line_and_exits_2_on_a_config_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)
    (tmp_path / "config.toml").write_text(BAD_TIME, encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        cli.main(["reports"])
    assert e.value.code == 2
    err = capsys.readouterr().err.strip()
    assert "Traceback" not in err
    last = err.splitlines()[-1]
    assert "[reports.open-work] time" in last and "25:99" in last


def test_a_cache_ttl_that_is_not_a_number_keeps_the_default(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)
    monkeypatch.setenv("FRIDGESHEET_CACHE_TTL_MINUTES", "three hours")
    s = config.load_settings()
    assert s.cache_ttl_minutes == config.Settings().cache_ttl_minutes


# --- #146: turning a schedule off -------------------------------------------------------

def test_unticking_the_schedule_and_every_day_still_turns_it_off(tmp_path):
    sched = FakeScheduling({"open-work": host.ScheduleInfo("systemd", True, "Mon 14:00", None)})
    out = schedules.save("open-work", enabled=False, time="14:00", days=[], printer="", prints=True,
                         home=tmp_path, log=lambda _m: None, scheduling=sched)
    assert out.ok, out.errors
    assert sched.removed == ["open-work"]
    assert tomllib.loads((tmp_path / "config.toml").read_text())["reports"]["open-work"]["enabled"] is False


def test_turning_off_still_refuses_a_time_that_would_break_the_file(tmp_path):
    sched = FakeScheduling()
    out = schedules.save("open-work", enabled=False, time="half four", days=[], printer="", prints=True,
                         home=tmp_path, log=lambda _m: None, scheduling=sched)
    assert not out.ok and "HH:MM" in out.errors[0]
    assert not (tmp_path / "config.toml").exists()


def test_unticking_the_refresh_schedule_and_every_day_still_turns_it_off(tmp_path):
    sched = FakeScheduling()
    out = schedules.save_refresh(enabled=False, every_hours=3, start="06:00", end="21:00", days=[],
                                 home=tmp_path, log=lambda _m: None, scheduling=sched)
    assert out.ok, out.errors
    assert sched.removed == [host.DATA_REFRESH_KEY]
    assert tomllib.loads((tmp_path / "config.toml").read_text())["refresh"]["enabled"] is False


def test_an_enabled_schedule_still_needs_a_day(tmp_path):
    out = schedules.save("open-work", enabled=True, time="14:00", days=[], printer="", prints=True,
                         home=tmp_path, log=lambda _m: None, scheduling=FakeScheduling())
    assert not out.ok and "no days" in out.errors[0]


# --- #146: the CLI keeps config.toml in step --------------------------------------------

@pytest.fixture
def cli_home(tmp_path, monkeypatch):
    sched = FakeScheduling()
    (tmp_path / "login-ok.txt").write_text("ok")       # `schedule install` gates on it, like the page (#154)
    monkeypatch.setattr(cli, "load_settings", lambda: config.Settings(home=tmp_path)
                        if not (tmp_path / "config.toml").exists() else _settings(tmp_path))
    monkeypatch.setattr("fridgesheet.host.scheduling", sched)
    sched.display_name = lambda key: f"fridgesheet-{key}"
    return tmp_path, sched


def _settings(home):
    s = config.Settings(home=home)
    config.settings_from_doc(config.load_config_doc(home / "config.toml"), s)
    return s


def _doc(home):
    return tomllib.loads((home / "config.toml").read_text())


def test_cli_install_and_remove_record_enabled_like_the_page_does(cli_home):
    home, sched = cli_home
    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "install", "open-work"])
    assert e.value.code == 0 and sched.installed[0]["key"] == "open-work"
    assert _doc(home)["reports"]["open-work"]["enabled"] is True
    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "remove", "open-work"])
    assert e.value.code == 0 and sched.removed == ["open-work"]
    assert _doc(home)["reports"]["open-work"]["enabled"] is False


def test_cli_install_keeps_everything_else_in_the_table(cli_home):
    home, sched = cli_home
    (home / "config.toml").write_text('[reports.open-work]\ntime = "15:10"\ndays = ["Tue"]\ndays_ahead = 7\n')
    with pytest.raises(SystemExit):
        cli.main(["schedule", "install", "open-work"])
    assert sched.installed[0]["times"] == ["15:10"] and sched.installed[0]["days"] == ["Tue"]
    assert _doc(home)["reports"]["open-work"] == {"time": "15:10", "days": ["Tue"], "days_ahead": 7, "enabled": True}


def test_a_failed_cli_install_leaves_the_config_alone(cli_home, monkeypatch):
    home, _ = cli_home
    failing = FakeScheduling(fail="systemctl said no")
    failing.display_name = lambda key: key
    monkeypatch.setattr("fridgesheet.host.scheduling", failing)
    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "install", "open-work"])
    assert e.value.code == 1
    assert not (home / "config.toml").exists()


def test_cli_install_data_refresh_installs_what_the_page_would(cli_home):
    home, sched = cli_home
    (home / "config.toml").write_text('[refresh]\nevery_hours = 4\nstart = "08:00"\nend = "16:00"\ndays = ["Sat"]\n')
    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "install", "data-refresh"])
    assert e.value.code == 0
    got = sched.installed[0]
    assert got["key"] == host.DATA_REFRESH_KEY and got["times"] == ["08:00", "12:00", "16:00"] and got["days"] == ["Sat"]
    assert got["title"] == "Data refresh"
    assert _doc(home)["refresh"]["enabled"] is True
    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "remove", "data-refresh"])
    assert e.value.code == 0 and _doc(home)["refresh"]["enabled"] is False
