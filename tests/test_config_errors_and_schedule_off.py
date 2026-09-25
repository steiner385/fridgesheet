"""#144: a config.toml that does not read is a message, never a 500 or a traceback.
#146: a schedule can always be turned off, and the CLI keeps config.toml in step with the
server's own clock (web/clock.py reads config.toml fresh every tick, so `remove` needs to do
nothing but write the file).

Neither the pages nor the CLI call an OS scheduler any more: the server's own clock replaced
it (2026-09-25 in-app scheduler), so nothing here reaches systemctl or schtasks."""
from __future__ import annotations

import tomllib

import pytest
from fastapi.testclient import TestClient

from fridgesheet import cli, config, host
from fridgesheet.web import app as webapp, schedules
from tests.web_fixtures import LOCAL_HOST_HEADERS, seed

BAD_TIME = '[reports.open-work]\ntime = "25:99"\n'


def _client(home):
    seed(home).close()
    application = webapp.create_app(config.Settings(home=home), worker=False)
    extra = application.state.fridgesheet.extra
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
    c = _client(tmp_path)
    (tmp_path / "config.toml").write_text("[reports.open-work\n", encoding="utf-8")
    r = c.post("/schedules", data={"key": "open-work", "enabled": "on", "time": "14:00", "days": ["Mon"], "prints": "on"})
    assert r.status_code == 200 and "cannot parse" in r.text
    r = c.post("/schedules/refresh", data={"enabled": "on", "every_hours": "3", "start": "06:00", "end": "21:00", "days": ["Mon"]})
    assert r.status_code == 200 and "cannot parse" in r.text
    assert (tmp_path / "config.toml").read_text(encoding="utf-8") == "[reports.open-work\n"   # never written over


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
    out = schedules.save("open-work", enabled=False, time="14:00", days=[], printer="", prints=True,
                         home=tmp_path, log=lambda _m: None)
    assert out.ok, out.errors
    assert tomllib.loads((tmp_path / "config.toml").read_text())["reports"]["open-work"]["enabled"] is False


def test_turning_off_still_refuses_a_time_that_would_break_the_file(tmp_path):
    out = schedules.save("open-work", enabled=False, time="half four", days=[], printer="", prints=True,
                         home=tmp_path, log=lambda _m: None)
    assert not out.ok and "HH:MM" in out.errors[0]
    assert not (tmp_path / "config.toml").exists()


def test_unticking_the_refresh_schedule_and_every_day_still_turns_it_off(tmp_path):
    out = schedules.save_refresh(enabled=False, every_hours=3, start="06:00", end="21:00", days=[],
                                 home=tmp_path, log=lambda _m: None)
    assert out.ok, out.errors
    assert tomllib.loads((tmp_path / "config.toml").read_text())["refresh"]["enabled"] is False


def test_an_enabled_schedule_still_needs_a_day(tmp_path):
    out = schedules.save("open-work", enabled=True, time="14:00", days=[], printer="", prints=True,
                         home=tmp_path, log=lambda _m: None)
    assert not out.ok and "no days" in out.errors[0]


# --- #146: the CLI keeps config.toml in step --------------------------------------------

@pytest.fixture
def cli_home(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "load_settings", lambda: config.Settings(home=tmp_path)
                        if not (tmp_path / "config.toml").exists() else _settings(tmp_path))
    return tmp_path


def _settings(home):
    s = config.Settings(home=home)
    config.settings_from_doc(config.load_config_doc(home / "config.toml"), s)
    return s


def _doc(home):
    return tomllib.loads((home / "config.toml").read_text())


def test_cli_remove_records_enabled_like_the_page_does(cli_home):
    """`install` is gone (2026-09-25 in-app scheduler): a schedule is turned on from the
    Schedules page and read by the server's own clock, so the CLI's one remaining job here is
    turning one off -- and `record_enabled` must write `enabled = false` the same way the page
    does, or `doctor`'s scheduler check keeps calling it on."""
    home = cli_home
    (home / "config.toml").write_text('[reports.open-work]\nenabled = true\ntime = "14:00"\ndays = ["Mon"]\n')
    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "remove", "open-work"])
    assert e.value.code == 0
    assert _doc(home)["reports"]["open-work"]["enabled"] is False


def test_cli_remove_data_refresh_turns_off_what_the_page_would(cli_home):
    """`data-refresh` is the one escape hatch through the report-key gate `remove` otherwise
    applies (it is not a report, `[refresh]` not `[reports.<key>]`) -- see
    `test_host_scheduling.py::test_schedule_remove_data_refresh_is_an_escape_hatch` for the
    key-resolution side of this; this pins that it actually turns `[refresh]` off."""
    home = cli_home
    (home / "config.toml").write_text('[refresh]\nenabled = true\nevery_hours = 4\nstart = "08:00"\nend = "16:00"\ndays = ["Sat"]\n')
    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "remove", "data-refresh"])
    assert e.value.code == 0
    assert _doc(home)["refresh"]["enabled"] is False
