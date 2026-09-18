"""The move from the old name to Fridge Sheet: once, silently, and never destructive."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from fridgesheet import migrate


# --- environment aliases ------------------------------------------------------------------

def test_old_env_names_are_honoured_but_the_new_name_wins():
    env = {"LAKOTA_PRINTER": "Brother", "LAKOTA_GRADES_HOME": "/old", "FRIDGESHEET_HAC_BASE": "x",
           "LAKOTA_HAC_BASE": "y", "PATH": "/bin"}
    honoured = migrate.alias_legacy_env(env)
    assert env["FRIDGESHEET_PRINTER"] == "Brother"
    assert env["FRIDGESHEET_HOME"] == "/old"                 # not FRIDGESHEET_GRADES_HOME
    assert env["FRIDGESHEET_HAC_BASE"] == "x"                # already set: kept
    assert honoured == ["LAKOTA_GRADES_HOME", "LAKOTA_HAC_BASE", "LAKOTA_PRINTER"]
    assert migrate.alias_legacy_env(env) == honoured         # idempotent


def test_no_old_names_is_a_no_op():
    env = {"FRIDGESHEET_PRINTER": "x"}
    assert migrate.alias_legacy_env(env) == [] and env == {"FRIDGESHEET_PRINTER": "x"}


# --- the data directory -----------------------------------------------------------------------

def test_legacy_home_per_os_and_none_under_an_override(tmp_path, real_legacy_home):
    legacy_home = real_legacy_home                              # conftest stubs the live one out
    assert legacy_home(is_windows=False, environ={}) == Path.home() / ".lakota-grades"
    assert legacy_home(is_windows=True, environ={"LOCALAPPDATA": str(tmp_path)}) == tmp_path / "lakota-grades"
    assert legacy_home(is_windows=False, environ={"FRIDGESHEET_HOME": "/x"}) is None
    assert legacy_home(is_windows=False, environ={"LAKOTA_GRADES_HOME": "/x"}) is None


def test_home_is_moved_once_and_a_link_is_left_on_linux(tmp_path):
    old, new = tmp_path / ".lakota-grades", tmp_path / ".fridgesheet"
    old.mkdir()
    (old / "config.toml").write_text("[account]\n")
    what = migrate.migrate_home(new, old, link_old=True)
    assert "moved" in what and (new / "config.toml").is_file()
    assert old.is_symlink() and old.resolve() == new.resolve()
    assert (old / "config.toml").is_file()                   # the old path still works
    assert migrate.migrate_home(new, old, link_old=True) is None    # second start: nothing


def test_home_move_without_a_link_on_windows(tmp_path):
    old, new = tmp_path / "lakota-grades", tmp_path / "fridgesheet"
    old.mkdir()
    migrate.migrate_home(new, old, link_old=False)
    assert new.is_dir() and not old.exists()


def test_home_move_refuses_when_both_exist_or_nothing_old(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    assert migrate.migrate_home(new, None, link_old=True) is None
    assert migrate.migrate_home(new, old, link_old=True) is None          # no old dir
    old.mkdir(); new.mkdir()
    (old / "keep").write_text("x"); (new / "config.toml").write_text("[web]\n")
    assert migrate.migrate_home(new, old, link_old=True) is None          # both real: untouched
    assert (old / "keep").is_file() and not old.is_symlink() and (new / "config.toml").is_file()


def test_home_move_ignores_an_old_path_that_is_already_a_link(tmp_path):
    real, old, new = tmp_path / "real", tmp_path / "old", tmp_path / "new"
    real.mkdir(); old.symlink_to(real)
    assert migrate.migrate_home(new, old, link_old=True) is None
    assert not new.exists()


# --- the database file ----------------------------------------------------------------------

def test_database_and_its_sidecars_are_renamed_together(tmp_path):
    for n in ("lakota.db", "lakota.db-wal", "lakota.db-shm"):
        (tmp_path / n).write_bytes(b"x")
    assert migrate.migrate_db(tmp_path, "fridgesheet.db") == "renamed lakota.db to fridgesheet.db"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["fridgesheet.db", "fridgesheet.db-shm", "fridgesheet.db-wal"]
    assert migrate.migrate_db(tmp_path, "fridgesheet.db") is None


def test_database_rename_never_overwrites_a_new_file(tmp_path):
    (tmp_path / "lakota.db").write_bytes(b"old")
    (tmp_path / "fridgesheet.db").write_bytes(b"new")
    assert migrate.migrate_db(tmp_path, "fridgesheet.db") is None
    assert (tmp_path / "fridgesheet.db").read_bytes() == b"new" and (tmp_path / "lakota.db").exists()


def test_open_db_picks_up_the_old_file(tmp_path):
    """The web layer's open path migrates first, so an upgraded install keeps its history."""
    import sqlite3
    from fridgesheet.web import db as webdb
    conn = webdb.open_db(tmp_path)
    conn.execute("INSERT INTO refreshes (started_at, sources, ok) VALUES ('t', '{}', 1)")
    conn.commit(); conn.close()
    os.replace(tmp_path / "fridgesheet.db", tmp_path / "lakota.db")
    for side in ("-wal", "-shm"):
        p = tmp_path / ("fridgesheet.db" + side)
        if p.exists():
            os.replace(p, tmp_path / ("lakota.db" + side))
    conn = webdb.open_db(tmp_path)
    assert conn.execute("SELECT count(*) FROM refreshes").fetchone()[0] == 1
    conn.close()
    assert not (tmp_path / "lakota.db").exists()


# --- credentials -------------------------------------------------------------------------------

def _run_for(answers: dict[str, str]):
    def run(argv, **kw):
        key = argv[argv.index("key") + 1] if "key" in argv else ""
        if argv[3] == "lakota-grades" and key in answers:
            return subprocess.CompletedProcess(argv, 0, stdout=answers[key] + "\n", stderr="")
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")
    return run


def test_legacy_password_is_read_from_the_old_service_on_linux():
    run = _run_for({"password": "pw", "username": "me@example.com"})
    assert migrate.read_legacy_password("me@example.com", is_windows=False, run=run) == "pw"
    assert migrate.read_legacy_username(is_windows=False, run=run) == "me@example.com"
    assert migrate.read_legacy_password("x", is_windows=False, run=_run_for({})) is None


def test_legacy_password_read_never_raises():
    def boom(argv, **kw):
        raise FileNotFoundError("secret-tool")
    assert migrate.read_legacy_password("x", is_windows=False, run=boom) is None
    assert migrate.read_legacy_username(is_windows=False, run=boom) is None


def test_settings_fall_back_to_the_old_credential_entry_and_copy_it_forward(monkeypatch, tmp_path):
    from fridgesheet import config
    from fridgesheet.host import credentials as store
    written = {}
    monkeypatch.setattr(store, "read_username", lambda run=None: None)
    monkeypatch.setattr(store, "read_password", lambda u, run=None: written.get(u))
    monkeypatch.setattr(store, "write", lambda u, p, run=None: written.__setitem__(u, p))
    monkeypatch.setattr(migrate, "read_legacy_username", lambda **kw: "me@example.com")
    monkeypatch.setattr(migrate, "read_legacy_password", lambda u, **kw: "pw" if u == "me@example.com" else None)
    s = config.Settings(home=tmp_path)
    assert s.credentials() == ("me@example.com", "pw")
    assert written == {"me@example.com": "pw"}                 # copied to the new service
    s2 = config.Settings(home=tmp_path, username="me@example.com")
    monkeypatch.setattr(migrate, "read_legacy_password", lambda u, **kw: pytest.fail("new entry exists; old not consulted"))
    assert s2.credentials() == ("me@example.com", "pw")


# --- doctor ------------------------------------------------------------------------------------

def test_doctor_lists_what_still_goes_by_the_old_name(tmp_path):
    new = tmp_path / "new"; new.mkdir()
    old = tmp_path / "old"; old.symlink_to(new)
    lines = migrate.legacy_in_use(environ={"LAKOTA_PRINTER": "x", "FRIDGESHEET_LEGACY_COMMAND": "1"},
                                  home=new, legacy_home_path=old)
    assert lines[0].startswith("environment: LAKOTA_PRINTER")
    assert any("lakota-grades" in line for line in lines)
    assert any("link" in line for line in lines)
    assert migrate.legacy_in_use(environ={}, home=new, legacy_home_path=tmp_path / "missing") == []


# --- the frozen entry point must move before it logs ---------------------------------------------

def test_a_new_home_holding_only_a_log_does_not_block_the_move(tmp_path):
    """The exe opens app.log before anything reads the home; that must not count as a second
    install worth protecting. Seen on the first real upgrade: an empty new folder, a full old one."""
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir(); (old / "config.toml").write_text("[web]\n"); (old / "fridgesheet.db").write_bytes(b"x")
    new.mkdir(); (new / "app.log").write_text("started\n"); (new / "app.log.1").write_text("")
    assert "moved" in migrate.migrate_home(new, old, link_old=False)
    assert (new / "config.toml").is_file() and not (new / "app.log.1").exists() and not old.exists()


def test_a_new_home_with_anything_else_in_it_is_respected(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir(); (old / "config.toml").write_text("[web]\n")
    new.mkdir(); (new / "app.log").write_text(""); (new / "notes.txt").write_text("mine")
    assert migrate.migrate_home(new, old, link_old=False) is None
    assert (new / "notes.txt").is_file() and (old / "config.toml").is_file()


def test_the_frozen_entry_point_moves_the_home_before_it_opens_its_log(monkeypatch, tmp_path):
    from fridgesheet import config
    from fridgesheet.web import __main__ as entry
    old, new = tmp_path / "lakota-grades", tmp_path / "fridgesheet"
    old.mkdir(); (old / "config.toml").write_text("[web]\nport = 8499\n")
    monkeypatch.setattr(config, "DEFAULT_HOME", new)
    monkeypatch.setattr(config, "_default_home", lambda: new)          # the OS default, not an override
    monkeypatch.setattr(migrate, "legacy_home", lambda **kw: old)
    seen = []
    monkeypatch.setattr(entry, "setup_logging", lambda home, stderr=None: seen.append(sorted(p.name for p in home.iterdir())))
    monkeypatch.setattr(entry, "launch", lambda s: 0)
    monkeypatch.setattr(entry, "load_settings", lambda: None)
    assert entry.main([]) == 0
    assert seen == [["config.toml"]]                    # the log opened in the *moved* home
    assert old.is_symlink() or not old.exists()         # a link on Linux, gone on Windows
