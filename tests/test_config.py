"""The optional .env under the fridgesheet home must load without anyone having to
export FRIDGESHEET_ENV_FILE. Claude Desktop rewrites its config on exit and can drop the
`env` block, and a systemd unit copied by hand may lose the Environment= line; either
way the server silently ran without its settings."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

import pytest

from fridgesheet import config, host

MARKER = "FRIDGESHEET_TEST_MARKER"


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """A fake fridgesheet home and a fake cwd, each holding a .env with a different marker."""
    monkeypatch.delenv("FRIDGESHEET_ENV_FILE", raising=False)
    monkeypatch.delenv(MARKER, raising=False)
    home = tmp_path / "home"
    home.mkdir()
    (home / ".env").write_text(f"{MARKER}=home\n")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    (cwd / ".env").write_text(f"{MARKER}=cwd\n")
    monkeypatch.setattr(config, "DEFAULT_HOME", home)
    monkeypatch.chdir(cwd)
    return home, cwd


def test_env_file_defaults_to_home_dotenv_when_unset(isolated):
    home, _ = isolated
    assert config.env_file() == home / ".env"


def test_env_file_honours_explicit_setting(isolated, monkeypatch, tmp_path):
    explicit = tmp_path / "elsewhere.env"
    monkeypatch.setenv("FRIDGESHEET_ENV_FILE", str(explicit))
    assert config.env_file() == explicit


def test_home_dotenv_beats_cwd_dotenv_when_unset(isolated):
    config._load_env_files()
    assert os.environ[MARKER] == "home"


def test_explicit_env_file_beats_home_dotenv(isolated, monkeypatch, tmp_path):
    explicit = tmp_path / "elsewhere.env"
    explicit.write_text(f"{MARKER}=explicit\n")
    monkeypatch.setenv("FRIDGESHEET_ENV_FILE", str(explicit))
    config._load_env_files()
    assert os.environ[MARKER] == "explicit"


def test_missing_default_env_file_is_not_an_error(isolated):
    home, _ = isolated
    (home / ".env").unlink()
    config._load_env_files()  # falls through to cwd/.env, silently
    assert os.environ[MARKER] == "cwd"


def test_sheets_archive_comes_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)
    monkeypatch.delenv("FRIDGESHEET_ENV_FILE", raising=False)
    monkeypatch.setenv("FRIDGESHEET_SHEETS_ARCHIVE", "/mnt/drive/Sheets")
    assert config.load_settings().sheets_archive == "/mnt/drive/Sheets"
    monkeypatch.delenv("FRIDGESHEET_SHEETS_ARCHIVE")
    assert config.load_settings().sheets_archive == ""


def test_bare_settings_never_defaults_to_the_owners_real_home():
    """The autouse `_no_app_home` fixture in conftest.py patches `config.DEFAULT_HOME` for
    every test, since `Settings.home`'s default factory reads that module attribute at
    construction time. A bare `Settings()` is easy to write and easy to leave behind when a
    command path starts touching the database where it never used to (`reports.available` did,
    in the schedules plan) -- so it must never be able to resolve to the owner's actual
    ~/.fridgesheet, with no per-test opt-in required."""
    assert config.Settings().home != Path.home() / ".fridgesheet"


def test_default_home_is_localappdata_on_windows(monkeypatch, tmp_path):
    from fridgesheet import host
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("FRIDGESHEET_HOME", raising=False)
    assert config._default_home() == tmp_path / "fridgesheet"
    monkeypatch.setattr(host, "IS_WINDOWS", False)
    assert config._default_home() == Path.home() / ".fridgesheet"


def test_config_doc_round_trip(tmp_path):
    p = tmp_path / "config.toml"
    doc = {"account": {"username": "p@x.com"}, "print": {"printer": 'Brother "MFC"', "archive": "C:\\Users\\p\\Drive"},
           "kids": {"nicknames": {"Alex": "Al"}},
           "reports": {"open-work": {"enabled": True, "time": "15:30", "days": ["Mon", "Wed"], "days_ahead": 7, "overdue_days": 21}}}
    config.save_config_doc(p, doc)
    assert config.load_config_doc(p) == doc
    assert config.load_config_doc(tmp_path / "missing.toml") == {}


def test_broken_config_names_the_file(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[print\n")
    with pytest.raises(config.ConfigError) as e:
        config.load_config_doc(p)
    assert str(p) in str(e.value)


def test_settings_from_doc_and_env_precedence(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)
    monkeypatch.delenv("FRIDGESHEET_ENV_FILE", raising=False)
    for k in ("FRIDGESHEET_PRINTER", "FRIDGESHEET_NICKNAMES", "FRIDGESHEET_SHEETS_ARCHIVE"):
        monkeypatch.delenv(k, raising=False)
    config.save_config_doc(tmp_path / "config.toml", {
        "account": {"username": "p@x.com"}, "print": {"printer": "Office", "archive": "/mnt/d"},
        "kids": {"nicknames": {"Alex": "Al", "Katherine": "Kate"}},
        "reports": {"open-work": {"enabled": True, "time": "15:30", "days_ahead": 7}, "weekly": {"enabled": False}, "unknown-key": 1},
        "not_a_section": {"x": 1},
    })
    s = config.load_settings()
    assert s.username == "p@x.com" and s.printer == "Office" and s.sheets_archive == "/mnt/d"
    assert s.nicknames == {"Alex": "Al", "Katherine": "Kate"}
    rc = s.report_config("open-work")
    assert rc.enabled and rc.time == "15:30" and rc.days == ["Mon", "Tue", "Wed", "Thu", "Fri"] and rc.options == {"days_ahead": 7}
    assert s.report_config("nope").enabled is False and s.report_config("nope", default_time="18:00").time == "18:00"
    assert s.reports["weekly"].time is None      # present in config.toml but no time set
    assert s.report_config("weekly", default_time="18:00").time == "18:00"
    monkeypatch.setenv("FRIDGESHEET_PRINTER", "Env")
    monkeypatch.setenv("FRIDGESHEET_NICKNAMES", "Alex=D,Jo=Mel")
    monkeypatch.setenv("FRIDGESHEET_SHEETS_ARCHIVE", "/env")
    s = config.load_settings()
    assert s.printer == "Env" and s.sheets_archive == "/env"
    assert s.nicknames == {"Alex": "D", "Katherine": "Kate", "Jo": "Mel"}   # env wins per key


def test_parse_nicknames():
    assert config.parse_nicknames(" Alex = Al ,Katherine=Kate,,bad") == {"Alex": "Al", "Katherine": "Kate"}
    assert config.parse_nicknames("") == {}


def test_no_nickname_is_built_in(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)
    monkeypatch.delenv("FRIDGESHEET_ENV_FILE", raising=False)
    monkeypatch.delenv("FRIDGESHEET_NICKNAMES", raising=False)
    assert config.load_settings().nicknames == {}


def test_bad_report_time_is_a_config_error(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)
    monkeypatch.delenv("FRIDGESHEET_ENV_FILE", raising=False)
    config.save_config_doc(tmp_path / "config.toml", {"reports": {"open-work": {"time": "2 PM"}}})
    with pytest.raises(config.ConfigError) as e:
        config.load_settings()
    assert str(tmp_path / "config.toml") in str(e.value) and "2 PM" in str(e.value)

    config.save_config_doc(tmp_path / "config.toml", {"reports": {"open-work": {"time": "9:00"}}})
    with pytest.raises(config.ConfigError, match="9:00"):
        config.load_settings()

    config.save_config_doc(tmp_path / "config.toml", {"reports": {"open-work": {"time": "09:00"}}})
    s = config.load_settings()
    assert s.report_config("open-work").time == "09:00"


def test_settings_home_follows_default_home(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)
    assert config.Settings().home == tmp_path


def test_non_dict_config_sections_are_ignored(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)
    monkeypatch.delenv("FRIDGESHEET_ENV_FILE", raising=False)
    config.save_config_doc(tmp_path / "config.toml", {"print": "oops"})
    s = config.load_settings()
    assert s.printer == ""


def test_extra_hosts_is_lowercased_and_survives_a_value_of_the_wrong_shape(tmp_path):
    """`[web] extra_hosts` is the closed list of *names* the app answers to under a wildcard
    bind (addresses need no entry; see `web.app._host_allowed`). Lowercased on the way in
    because `urlsplit` lowercases the incoming `Host`, so `Graphy.Tailnet-1234.ts.net` typed
    here would otherwise never match the request it was written for -- the same trap an
    explicit `FRIDGESHEET_WEB_HOST` pin already fell into once."""
    s = config.Settings(home=tmp_path)
    config.settings_from_doc({"web": {"extra_hosts": ["Graphy.Tailnet-1234.TS.net", "  spaced.local  ", ""]}}, s)
    assert s.web_extra_hosts == ["graphy.tailnet-1234.ts.net", "spaced.local"]

    # A scalar where a list belongs must not become a list of its characters, and must not
    # take the whole config down: the default stands, as it does for a bad `port`.
    s2 = config.Settings(home=tmp_path)
    config.settings_from_doc({"web": {"extra_hosts": "graphy.local"}}, s2)
    assert s2.web_extra_hosts == []


def test_web_section_and_env_override(tmp_path, monkeypatch):
    s = config.Settings(home=tmp_path)
    config.settings_from_doc({"web": {"port": 9000, "allow_lan": True, "host": "10.0.0.5"}}, s)
    assert (s.web_port, s.web_allow_lan, s.web_host) == (9000, True, "10.0.0.5")
    assert s.bind_host == "0.0.0.0"
    s2 = config.Settings(home=tmp_path)
    assert (s2.web_port, s2.web_allow_lan, s2.bind_host) == (8433, False, "127.0.0.1")
    config.settings_from_doc({"web": {"port": "not a number"}}, s2)
    assert s2.web_port == 8433                     # a bad value keeps the default
    # `DEFAULT_HOME` is read at import, so pointing FRIDGESHEET_HOME at tmp_path here would
    # not move it: load_settings() would read (and mkdir under) the developer's real home, and
    # its .env would leak FRIDGESHEET_* values into every later test. Patch the module attribute,
    # the way the rest of this file does.
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)
    monkeypatch.delenv("FRIDGESHEET_ENV_FILE", raising=False)
    monkeypatch.setenv("FRIDGESHEET_WEB_PORT", "8500")
    monkeypatch.setenv("FRIDGESHEET_WEB_HOST", "0.0.0.0")
    s3 = config.load_settings()
    assert (s3.home, s3.web_port, s3.bind_host) == (tmp_path, 8500, "0.0.0.0")


def test_explicit_web_host_env_wins_over_allow_lan(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)
    monkeypatch.delenv("FRIDGESHEET_ENV_FILE", raising=False)
    config.save_config_doc(tmp_path / "config.toml", {"web": {"allow_lan": True}})
    assert config.load_settings().bind_host == "0.0.0.0"          # allow_lan alone opens the LAN
    monkeypatch.setenv("FRIDGESHEET_WEB_HOST", "127.0.0.1")
    s = config.load_settings()
    assert (s.web_allow_lan, s.web_host_explicit) == (True, True)
    assert s.bind_host == "127.0.0.1"                             # the env address pins it back


def test_a_report_can_name_its_own_printer_and_ask_not_to_print(tmp_path):
    """Spec section 5: a schedule is "any report, days, time, printer or PDF-only". Those two
    live with the rest of the report's config so changing them never means reinstalling a unit."""
    doc = tomllib.loads(
        '[reports."view:7"]\n'
        'enabled = true\ntime = "16:00"\ndays = ["Fri"]\n'
        'printer = "Brother_MFC_J4335DW"\nprint = false\n')
    s = config.Settings(home=tmp_path)
    config.settings_from_doc(doc, s)
    rc = s.report_config("view:7", "16:00")
    assert rc.printer == "Brother_MFC_J4335DW" and rc.prints is False
    assert "printer" not in rc.options and "print" not in rc.options   # not build options


def test_a_report_prints_to_the_shared_printer_by_default(tmp_path):
    doc = tomllib.loads('[reports.open-work]\nenabled = true\ndays_ahead = 10\n')
    s = config.Settings(home=tmp_path)
    config.settings_from_doc(doc, s)
    rc = s.report_config("open-work", "14:00")
    assert rc.printer == "" and rc.prints is True and rc.options == {"days_ahead": 10}


def test_a_days_value_that_is_not_a_list_of_days_falls_back_to_the_default(tmp_path):
    """`days` came straight off the document as `[str(d) for d in sect.get("days", WEEKDAYS)]`
    with no type check, so a hand-edited (or future-version) `days = 5` raised a bare
    `TypeError: 'int' object is not iterable` out of `settings_from_doc` -- and out of every
    one of its callers, including the uninstaller's settings read (as `schedule remove --all` then was), where it killed
    `schedule remove --all` before a single task was removed. A string is just as wrong in a
    quieter way: `[str(d) for d in "Mon"]` yields `["M", "o", "n"]`.

    Treat it the way `[web]`'s port and `[kids].nicknames` already treat a value of the wrong
    shape: keep the default and read the rest of the table."""
    for bad in (5, True, {"Mon": True}, None):
        s = config.Settings(home=tmp_path)
        config.settings_from_doc({"reports": {"open-work": {"enabled": True, "days": bad, "days_ahead": 7}}}, s)
        rc = s.report_config("open-work")
        assert rc.days == config.WEEKDAYS, f"days = {bad!r}"
        assert rc.enabled and rc.options == {"days_ahead": 7}       # and the rest of the table still read
        assert "days" not in rc.options                             # still a known key, not a build option

    s = config.Settings(home=tmp_path)                              # the good shape is untouched
    config.settings_from_doc({"reports": {"open-work": {"days": ["Mon", "Wed"]}}}, s)
    assert s.report_config("open-work").days == ["Mon", "Wed"]


def test_a_reports_key_that_is_not_a_table_is_ignored_like_any_other_section(tmp_path):
    """`reports = "oops"` raised `AttributeError` from `.items()`; the other top-level sections
    have been type-guarded since `test_non_dict_config_sections_are_ignored`."""
    s = config.Settings(home=tmp_path)
    config.settings_from_doc({"reports": "oops", "account": {"username": "p@example.org"}}, s)
    assert s.reports == {} and s.username == "p@example.org"


# --- [refresh]: the app's own data-refresh schedule ------------------------------------

def _doc_refresh(**kw) -> dict:
    return {"refresh": {**kw}}


def test_refresh_defaults_when_the_table_is_absent():
    s = config.Settings()
    config.settings_from_doc({}, s)
    assert s.refresh.enabled is False
    assert s.refresh.every_hours == 3
    assert (s.refresh.start, s.refresh.end) == ("06:00", "21:00")
    assert s.refresh.days == list(host.DAY_NAMES)          # all seven; grades post at weekends


def test_refresh_reads_every_field():
    s = config.Settings()
    config.settings_from_doc(_doc_refresh(enabled=True, every_hours=4, start="07:00",
                                          end="19:00", days=["Mon", "Wed"]), s)
    assert s.refresh.enabled is True and s.refresh.every_hours == 4
    assert (s.refresh.start, s.refresh.end) == ("07:00", "19:00")
    assert s.refresh.days == ["Mon", "Wed"]


@pytest.mark.parametrize("bad", ["three", 2.5, None, [], True])
def test_a_misshapen_every_hours_keeps_the_default(bad):
    """The `[reports]` rule: a wrong *shape* falls back rather than raising, because a
    TypeError here tracebacks out of `schedule remove --all` during uninstall."""
    s = config.Settings()
    config.settings_from_doc(_doc_refresh(every_hours=bad), s)
    assert s.refresh.every_hours == 3


@pytest.mark.parametrize("bad", [5, None, {}])
def test_misshapen_days_keep_the_default(bad):
    s = config.Settings()
    config.settings_from_doc(_doc_refresh(days=bad), s)
    assert s.refresh.days == list(host.DAY_NAMES)


def test_a_refresh_table_that_is_not_a_table_keeps_the_defaults():
    s = config.Settings()
    config.settings_from_doc({"refresh": "yes please"}, s)
    assert s.refresh.enabled is False and s.refresh.every_hours == 3


@pytest.mark.parametrize("field,bad", [("start", "6am"), ("end", "25:00"), ("start", 600)])
def test_a_time_that_is_not_a_time_is_a_config_error(field, bad):
    """The one exception to falling back: a refresh silently running at the wrong hour is
    worse than one that refuses to install."""
    s = config.Settings()
    with pytest.raises(config.ConfigError, match="refresh"):
        config.settings_from_doc(_doc_refresh(**{field: bad}), s)


# --- [kids].grades: which grade each child is in ---------------------------------------

def test_grades_default_to_empty():
    s = config.Settings()
    config.settings_from_doc({}, s)
    assert s.grades == {}


def test_grades_are_read_beside_the_nicknames():
    s = config.Settings()
    config.settings_from_doc({"kids": {"nicknames": {"Douglas": "Doug"},
                                       "grades": {"Douglas": 9, "Kayla": 5}}}, s)
    assert s.grades == {"Douglas": 9, "Kayla": 5}
    assert s.nicknames == {"Douglas": "Doug"}          # the neighbour still works


@pytest.mark.parametrize("bad", ["five", 5.5, None, [], True])
def test_a_grade_that_is_not_a_whole_number_is_dropped_not_raised(bad):
    """A child with an unreadable grade falls back to today's interface. Raising here would
    traceback out of `schedule remove --all`, which the uninstaller runs hidden."""
    s = config.Settings()
    config.settings_from_doc({"kids": {"grades": {"Douglas": bad, "Kayla": 5}}}, s)
    assert s.grades == {"Kayla": 5}


def test_a_grades_value_that_is_not_a_table_keeps_the_default():
    s = config.Settings()
    config.settings_from_doc({"kids": {"grades": "ninth"}}, s)
    assert s.grades == {}


def test_sources_table_reaches_settings():
    from fridgesheet import sources
    s = config.Settings()
    config.settings_from_doc({"sources": {"grades": "canvas", "rule": [{"course": "Band", "assignments": "hac"}]}}, s)
    assert s.sources.resolve("Alex", "Concert Band") == sources.Choice("hac", "canvas")


def test_settings_default_sources_are_canvas_assignments_hac_grades():
    from fridgesheet import sources
    assert config.Settings().sources == sources.DEFAULT


def test_a_bad_sources_table_does_not_fail_the_load():
    s = config.Settings()
    config.settings_from_doc({"sources": "hac"}, s)             # no exception
    config.settings_from_doc({"sources": {"grades": 3}}, s)
    assert s.sources.default.grades == "hac"


@pytest.mark.parametrize("raw, want", [("Mon", ["Mon"]), ("Mon, Wed", ["Mon", "Wed"]), ("Mon Wed Fri", ["Mon", "Wed", "Fri"]),
                                       ("Monday", ["Monday"])])
def test_a_days_string_means_the_days_it_names(raw, want):
    """#9: `days = "Mon"` fell back to all five weekdays in silence, so a hand edit meant to print
    on Mondays printed every school day. A string now names its days; a name that is not a day
    ("Monday") still reaches `host.check_schedule`, which says so when the schedule is installed."""
    s = config.Settings()
    config.settings_from_doc({"reports": {"open-work": {"days": raw}}, "refresh": {"days": raw}}, s)
    assert s.report_config("open-work").days == want
    assert s.refresh.days == want


def test_a_days_value_of_the_wrong_shape_says_so(caplog):
    s = config.Settings()
    with caplog.at_level("WARNING"):
        config.settings_from_doc({"reports": {"open-work": {"days": 5}}}, s)
    assert s.report_config("open-work").days == config.WEEKDAYS
    assert "[reports.open-work] days" in caplog.text


@pytest.mark.parametrize("raw, want", [(False, False), ("false", False), ("no", False), ("0", False), (0, False),
                                       (True, True), ("true", True), ("yes", True), (1, True)])
def test_a_quoted_boolean_means_what_it_says(raw, want):
    """#7: `print = "false"` read as True (`bool("false")`), so a report meant to be archived
    only went to the printer anyway. Same for `enabled`."""
    s = config.Settings()
    config.settings_from_doc({"reports": {"open-work": {"print": raw, "enabled": raw}},
                              "refresh": {"enabled": raw}}, s)
    rc = s.report_config("open-work")
    assert (rc.prints, rc.enabled, s.refresh.enabled) == (want, want, want)


def test_a_boolean_that_is_not_one_keeps_the_default_and_says_so(caplog):
    s = config.Settings()
    with caplog.at_level("WARNING"):
        config.settings_from_doc({"reports": {"open-work": {"print": "maybe"}}}, s)
    assert s.report_config("open-work").prints is True
    assert "[reports.open-work] print" in caplog.text


def test_printer_for_is_the_runners_precedence(tmp_path):
    """One answer to "which printer?" for the runner and every confirmation that names it
    (#127): the explicit override, then the report's own, then [print], then "" (the system
    default)."""
    doc = tomllib.loads('[print]\nprinter = "Shared"\n[reports.open-work]\nprinter = "Kitchen"\n')
    s = config.Settings(home=tmp_path)
    config.settings_from_doc(doc, s)
    assert s.printer_for("open-work") == "Kitchen"
    assert s.printer_for("open-work", "Office") == "Office"
    assert s.printer_for("view:7") == "Shared"
    s.printer = ""
    assert s.printer_for("view:7") == ""
