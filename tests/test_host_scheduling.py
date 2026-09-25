from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from fridgesheet import host
from fridgesheet.host import NotSupported, scheduling, scheduling_linux, scheduling_windows, service_windows


class _R:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def test_safe_key_makes_a_name_both_operating_systems_accept():
    """A view report's key is `view:<id>`. A colon starts an instance name in systemd and is
    refused outright by Task Scheduler, so it never reaches either."""
    assert host.safe_key("open-work") == "open-work"          # every existing task keeps its name
    assert host.safe_key("view:7") == "view-7"
    assert host.safe_key("view:7:extra") == "view-7-extra"
    assert host.safe_key("a/b\\c d") == "a-b-c-d"
    assert host.safe_key("...") == "report"                   # nothing usable left
    assert host.safe_key("") == "report"
    assert host.task_name("view:7") == "Fridge Sheet - view 7"


def test_check_schedule_speaks_once_for_both_platforms():
    host.check_schedule("14:00", ["Mon", "Sun"])              # no exception
    with pytest.raises(scheduling.SchedulingError, match="Monday"):
        host.check_schedule("14:00", ["Mon", "Monday"])
    with pytest.raises(scheduling.SchedulingError, match="no days"):
        host.check_schedule("14:00", [])
    with pytest.raises(scheduling.SchedulingError, match="HH:MM"):
        host.check_schedule("9:00", ["Mon"])
    with pytest.raises(scheduling.SchedulingError, match="HH:MM"):
        host.check_schedule("24:00", ["Mon"])


def test_schedule_info_says_whether_the_app_may_change_it():
    """A hand-written unit is reported and left alone; the page reads `manageable` to decide
    whether to offer a Remove button. The default keeps every existing construction working."""
    assert host.ScheduleInfo("systemd", True, "x", None).manageable is True
    assert host.ScheduleInfo("systemd", True, "x", None, False).manageable is False
    assert host.ScheduleInfo("task-scheduler", True, "x", "0") == host.ScheduleInfo("task-scheduler", True, "x", "0")


def test_day_tags_keys_come_from_day_names_not_a_second_spelling():
    """`_DAY_TAGS`'s keys, `host.DAY_NAMES` and `routes/schedules.py`'s `DAYS` used to be three
    separate spellings of the same seven abbreviations (#31-#36 roll-up). `_DAY_TAGS` must be
    built *from* `DAY_NAMES`, so a day added or reordered there cannot silently leave this
    module's XML rendering out of step."""
    assert tuple(scheduling_windows._DAY_TAGS) == host.DAY_NAMES


def test_task_xml_description_can_be_the_reports_title():
    xml = scheduling_windows.render_task_xml("Fridge Sheet - view-7", ["16:00"], ["Fri"], "x", "run view:7", ".",
                                             description="Fridge Sheet: Weekly summary")
    assert "<Description>Fridge Sheet: Weekly summary</Description>" in xml


def test_windows_install_takes_the_same_keywords_as_the_linux_one():
    """One call site serves both platforms, so both signatures take `title`, `home` and
    `timezone`. Task Scheduler carries neither of the last two -- the task runs in the
    logged-in session's own environment, and StartBoundary is local time by definition."""
    seen = {}

    def run(cmd, **kw):
        seen["xml"] = Path(cmd[cmd.index("/XML") + 1]).read_text(encoding="utf-16")
        return _R(0, "SUCCESS")

    scheduling_windows.install("view:7", ["16:00"], ["Fri"], "x", "run view:7", ".", run=run,
                               title="Weekly summary", home="/anything", timezone="America/New_York")
    assert "<Description>Fridge Sheet: Weekly summary</Description>" in seen["xml"]


def test_task_xml_has_the_trigger_settings_and_action():
    xml = scheduling_windows.render_task_xml("Fridge Sheet - open-work", ["14:00"], ["Mon", "Tue", "Wed", "Thu", "Fri"],
                                             r"C:\Apps\FridgeSheet.exe", "run open-work", r"C:\Apps")
    assert "<StartBoundary>2026-01-01T14:00:00</StartBoundary>" in xml
    assert "<Monday />" in xml and "<Friday />" in xml and "<Saturday />" not in xml
    assert "<StartWhenAvailable>true</StartWhenAvailable>" in xml
    assert "<ExecutionTimeLimit>PT30M</ExecutionTimeLimit>" in xml
    assert "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>" in xml
    assert "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>" in xml
    assert "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>" in xml
    assert "<WakeToRun>false</WakeToRun>" in xml
    assert "<LogonType>InteractiveToken</LogonType>" in xml and "<RunLevel>LeastPrivilege</RunLevel>" in xml
    assert r"<Command>C:\Apps\FridgeSheet.exe</Command>" in xml and "<Arguments>run open-work</Arguments>" in xml
    assert r"<WorkingDirectory>C:\Apps</WorkingDirectory>" in xml
    assert "<Description>Fridge Sheet: open-work</Description>" in xml


def test_task_xml_escapes_paths_with_ampersands():
    xml = scheduling_windows.render_task_xml("n", ["08:05"], ["Sat"], r"C:\A & B\x.exe", "run k", r"C:\A & B")
    assert r"<Command>C:\A &amp; B\x.exe</Command>" in xml and "<Saturday />" in xml and "T08:05:00" in xml


def test_task_xml_rejects_unknown_or_empty_days():
    with pytest.raises(scheduling.SchedulingError, match="Monday"):
        scheduling_windows.render_task_xml("n", ["14:00"], ["Mon", "Monday"], "x", "run k", ".")
    with pytest.raises(scheduling.SchedulingError, match="no days"):
        scheduling_windows.render_task_xml("n", ["14:00"], [], "x", "run k", ".")


def test_task_xml_rejects_bad_time():
    with pytest.raises(scheduling.SchedulingError, match="HH:MM"):
        scheduling_windows.render_task_xml("n", ["9:00"], ["Mon"], "x", "run k", ".")
    with pytest.raises(scheduling.SchedulingError, match="HH:MM"):
        scheduling_windows.render_task_xml("n", ["14:60"], ["Mon"], "x", "run k", ".")


def test_windows_install_with_bad_days_never_calls_schtasks():
    def run(cmd, **kw):
        raise AssertionError("schtasks must not run")
    with pytest.raises(scheduling.SchedulingError):
        scheduling_windows.install("k", ["14:00"], ["Funday"], "x", "run k", ".", run=run)


def test_windows_install_writes_utf16_xml_and_calls_schtasks():
    seen = {}

    def run(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        seen["xml"] = Path(cmd[cmd.index("/XML") + 1]).read_bytes()
        return _R(0, "SUCCESS: The scheduled task has been created.")

    scheduling_windows.install("open-work", ["14:00"], ["Mon"], r"C:\x.exe", "run open-work", "C:\\", run=run)
    assert seen["cmd"][:4] == ["schtasks", "/Create", "/TN", "Fridge Sheet - open-work"] and seen["cmd"][-1] == "/F"
    assert seen["xml"].startswith(b"\xff\xfe") and seen["xml"].decode("utf-16").startswith('<?xml version="1.0" encoding="UTF-16"?>')
    assert seen["kw"]["creationflags"] == scheduling_windows.CREATE_NO_WINDOW
    assert not Path(seen["cmd"][seen["cmd"].index("/XML") + 1]).exists()      # temp file cleaned up


def test_windows_install_failure_surfaces_stderr():
    with pytest.raises(scheduling.SchedulingError, match="Access is denied"):
        scheduling_windows.install("k", ["14:00"], ["Mon"], "x", "run k", ".", run=lambda c, **k: _R(1, "", "ERROR: Access is denied."))


def test_windows_remove_and_describe():
    seen = []

    def run(cmd, **kw):
        seen.append(cmd)
        if cmd[1] == "/Delete":
            return _R(0)
        return _R(0, "Folder: \\\nHostName:      PC\nTaskName:      \\Fridge Sheet - open-work\nNext Run Time: 9/15/2026 2:00:00 PM\n"
                     "Status:        Ready\nLast Run Time: 9/14/2026 2:00:03 PM\nLast Result:   0\n")

    scheduling_windows.remove("open-work", run=run)
    assert seen[0] == ["schtasks", "/Delete", "/TN", "Fridge Sheet - open-work", "/F"]
    info = scheduling_windows.describe("open-work", run=run)
    assert seen[1] == ["schtasks", "/Query", "/TN", "Fridge Sheet - open-work", "/FO", "LIST", "/V"]
    assert info == scheduling.ScheduleInfo("task-scheduler", True, "9/15/2026 2:00:00 PM", "0")
    missing = scheduling_windows.describe("open-work", run=lambda c, **k: _R(1, "", "ERROR: The system cannot find the file specified."))
    assert missing == scheduling.ScheduleInfo("task-scheduler", False, None, None)
    scheduling_windows.remove("gone", run=lambda c, **k: _R(1, "", "ERROR: The system cannot find the file specified."))  # not an error


def test_linux_install_and_remove_are_no_longer_refused(tmp_path):
    """The read-only era is over: scheduling_linux writes units (tests/test_host_scheduling_linux.py
    covers what it writes and what stays refused for a hand-written unit). This just pins that
    a plain key with no legacy unit installs cleanly with no `is-enabled` probe at all."""
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
    scheduling_linux.install("view:3", ["14:00"], ["Mon"], "x", "run view:3", ".", run=run, unit_dir=tmp_path)
    assert (tmp_path / "fridgesheet-view-3.timer").is_file()
    assert calls == [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", "fridgesheet-view-3.timer"],
    ]


def test_windows_refuses_the_web_servers_own_logon_task_before_any_schtasks_call():
    """`task_name("web")` is byte-for-byte `service_windows.NAME`, the always-on logon task the
    installer registers. Without this guard `schedule remove web` deletes it and the server
    never comes back at next logon. Linux refuses the same key by name too -- see
    `tests/test_host_scheduling_linux.py::test_install_and_remove_refuse_the_web_servers_own_unit_by_name`
    -- via `service_linux.UNIT_FILE` imported into `scheduling_linux._FOREIGN_UNITS`, the same
    fix as this module's `_FOREIGN_TASKS`: an ownership promise cannot be an accident of one
    platform."""
    assert host.task_name("web") == service_windows.NAME

    def run(cmd, **kw):
        raise AssertionError("schtasks must not run for a task this app did not schedule")

    with pytest.raises(scheduling.SchedulingError, match="refusing"):
        scheduling_windows.install("web", ["14:00"], ["Mon"], "x", "run web", ".", run=run)
    with pytest.raises(scheduling.SchedulingError, match="refusing"):
        scheduling_windows.remove("web", run=run)


def test_windows_refuses_the_logon_task_however_the_key_is_cased():
    """Task Scheduler's namespace is case-insensitive: "Fridge Sheet - Web" and "Fridge Sheet -
    web" are one and the same task. An exact-string `_FOREIGN_TASKS` membership test therefore
    guarded only one spelling, and `[reports.Web]` hand-edited into config.toml went straight
    through to `schtasks /Delete /TN "Fridge Sheet - Web" /F` -- the web server's own logon
    task, gone until someone reinstalls.

    Linux needs no equivalent and must not grow one: systemd unit names really are
    case-sensitive, so `fridgesheet-Web.timer` is a genuinely different unit."""
    def run(cmd, **kw):
        raise AssertionError("schtasks must not run for a task this app did not schedule")

    for key in ("Web", "WEB", "wEb", "web "):
        with pytest.raises(scheduling.SchedulingError, match="refusing"):
            scheduling_windows.remove(key, run=run)
        with pytest.raises(scheduling.SchedulingError, match="refusing"):
            scheduling_windows.install(key, ["14:00"], ["Mon"], "x", f"run {key}", ".", run=run)


def test_display_name_is_what_this_platform_actually_installed(tmp_path):
    """`task_name` is documented as *the Windows task's display name*, and says "Fridge Sheet -
    open-work" on both platforms -- so a Linux `schedule remove --all` printed a Windows task
    name once per report while what it removed was a pair of systemd units. `blocking_name` was
    platform-dispatched in this branch for exactly this reason; `display_name` is the other
    half of it, and `scheduling` re-exports whichever one this host is running."""
    assert scheduling_windows.display_name("open-work") == "Fridge Sheet - open-work"
    assert scheduling_windows.display_name("view:7") == "Fridge Sheet - view 7"
    assert scheduling_linux.display_name("open-work") == "fridgesheet-open-work.{service,timer}"
    assert scheduling_linux.display_name("view:7") == "fridgesheet-view-7.{service,timer}"
    expected = scheduling_windows if host.IS_WINDOWS else scheduling_linux
    assert scheduling.display_name("open-work") == expected.display_name("open-work")


def test_schedule_remove_refuses_a_key_that_is_not_a_report(monkeypatch, capsys, tmp_path):
    """The `install` branch resolves the key first; `remove` did not, so `fridgesheet
    schedule remove web` went straight to the scheduler with a key no report answers to."""
    from fridgesheet import cli
    from fridgesheet.config import Settings
    monkeypatch.setattr(cli, "load_settings", lambda: Settings(home=tmp_path))

    def boom(*a, **k):
        raise AssertionError("the scheduler must not be touched for a key that is not a report")

    monkeypatch.setattr(scheduling, "remove", boom)
    monkeypatch.setattr(scheduling, "describe", boom)
    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "remove", "web"])
    assert e.value.code == 1 and "web" in capsys.readouterr().err


def test_schedule_remove_data_refresh_is_an_escape_hatch(monkeypatch, capsys, tmp_path):
    """`data-refresh` is not a report (`[refresh]`, not `[reports.<key>]`), so the ordinary
    `reports.resolve` gate `remove` otherwise applies would refuse it exactly like `remove web`
    does above -- leaving a parent with no single-key way to turn off a refresh schedule whose
    `[refresh]` table is already gone, only the blunt `schedule remove --all`. `data-refresh` is
    admitted by exact name, not by loosening the gate itself: it is a fixed, reserved key
    (`host.RESERVED_KEYS`) a report can never be saved under, so this costs nothing the gate
    was protecting.

    `remove` no longer touches an OS scheduler at all (2026-09-25 in-app scheduler): it just
    resolves the key and writes `config.toml`, which is all this test now pins -- the key must
    not be refused the way a non-report string is."""
    from fridgesheet import cli
    from fridgesheet.config import Settings
    monkeypatch.setattr(cli, "load_settings", lambda: Settings(home=tmp_path))

    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "remove", "data-refresh"])
    assert e.value.code == 0
    assert "data-refresh: turned off in config.toml" in capsys.readouterr().out


def test_schedule_removal_keys_always_includes_the_data_refresh_key(tmp_path):
    """The bug this closes: `[refresh]` lives outside `[reports.<key>]` and is not a report, so
    it never appeared in `_schedule_removal_keys`' output before this fix -- a household that
    enabled the refresh schedule and then uninstalled kept `Fridge Sheet - data-refresh` firing
    at a deleted exe forever, with no `[UninstallRun]` step that would ever remove it.

    Pinned with a bare `Settings()` and no `config.toml` at all under `tmp_path` -- not just no
    `[refresh]` table, no file -- because the fix must be unconditional: it cannot depend on
    `[refresh]` having ever been written, since the whole point is to remove a task whose
    config may already be gone."""
    from fridgesheet import cli, config, host

    s = config.Settings(home=tmp_path)
    keys, complete = cli._schedule_removal_keys(s)
    assert host.DATA_REFRESH_KEY in keys
    assert complete is True


def test_schedule_remove_all_removes_every_available_reports_schedule(monkeypatch, capsys, tmp_path):
    """The uninstaller's own call (installer.iss's `[UninstallRun]` now runs `schedule remove
    --all` instead of a bare `schedule remove`, which only ever named the default report):
    every report this app knows about -- the built-in one and any saved view report -- gets a
    `remove()` call, so a parent who scheduled a report on the Schedules page does not keep its
    Task Scheduler entry (or systemd timer) behind after uninstalling.

    `config.DEFAULT_HOME` is what points the command at `tmp_path`, not a stub for
    `cli.load_settings`: the `--all` path finds its own settings (`_removal_settings`) and a
    test that replaces that function tests the stub instead of the code."""
    from fridgesheet import cli, config
    from fridgesheet.web import db, views
    from fridgesheet.web.stores import reports as store

    conn = db.open_db(tmp_path)
    store.create(conn, "Weekly summary", views.defaults().to_json(), now="2026-09-16T08:00:00-04:00")
    conn.close()

    removed = []
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)
    monkeypatch.setattr(scheduling, "remove", lambda key, **kw: removed.append(key))

    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "remove", "--all"])
    assert e.value.code == 0
    assert sorted(removed) == ["data-refresh", "open-work", "view:1"]
    # What it says it removed is this platform's own object, not a Windows task name on Linux.
    assert f"Removed {scheduling.display_name('open-work')}" in capsys.readouterr().out


def test_schedule_remove_all_keeps_going_past_one_reports_refusal(monkeypatch, tmp_path):
    """A `SchedulingError` for one report (e.g. a hand-written namesake unit) must not stop the
    uninstaller from still trying every other report -- but the exit code says something was
    left behind."""
    from fridgesheet import cli, config
    from fridgesheet.web import db, views
    from fridgesheet.web.stores import reports as store

    conn = db.open_db(tmp_path)
    store.create(conn, "Weekly summary", views.defaults().to_json(), now="2026-09-16T08:00:00-04:00")
    conn.close()

    removed = []

    def flaky_remove(key, **kw):
        if key == "open-work":
            raise scheduling.SchedulingError("fridgesheet-open-work.timer was not written by this app")
        removed.append(key)

    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)
    monkeypatch.setattr(scheduling, "remove", flaky_remove)

    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "remove", "--all"])
    assert e.value.code == 1
    # sorted order: "data-refresh" comes before "open-work" (which raises) and "view:1"
    assert removed == ["data-refresh", "view:1"]


def test_schedule_remove_all_stops_outright_on_not_supported(monkeypatch, capsys, tmp_path):
    """`NotSupported` means this host has no scheduler at all -- unlike `SchedulingError`, no
    later report in the loop could fare any better, so `_cmd_schedule_remove_all` must stop
    there rather than trying (and failing identically on) every remaining key.

    What this pins is the *handler's* contract against an injected `remove` that raises, not a
    path any shipped code takes: nothing under `fridgesheet/host/` raises `NotSupported` for
    scheduling -- both platforms have a real implementation -- so the branch is unreachable in
    production and is kept as insurance for a third platform. Read this as "if a scheduler ever
    says it cannot schedule, stop and exit 2", not as coverage of live behaviour."""
    from fridgesheet import cli, config
    from fridgesheet.web import db, views
    from fridgesheet.web.stores import reports as store

    conn = db.open_db(tmp_path)
    store.create(conn, "Weekly summary", views.defaults().to_json(), now="2026-09-16T08:00:00-04:00")
    conn.close()

    calls = []

    def unsupported(key, **kw):
        calls.append(key)
        raise NotSupported("scheduling is not available on this host")

    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)
    monkeypatch.setattr(scheduling, "remove", unsupported)

    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "remove", "--all"])
    assert e.value.code == 2
    assert "scheduling is not available" in capsys.readouterr().err
    assert calls == ["data-refresh"]       # stopped at the first key, sorted first -- the rest never attempted


def test_schedule_remove_all_is_refused_with_show(monkeypatch, capsys, tmp_path):
    """`--all` only makes sense with `remove`; the uninstaller is the only caller, and pairing
    it with `show` would say nothing useful. (`install` is no longer a `schedule` action at
    all -- argparse refuses it outright, pinned separately below.)"""
    from fridgesheet import cli, config
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)

    def boom(*a, **k):
        raise AssertionError("_cmd_schedule_remove_all must not run: the --all/show guard "
                             "should have returned before this, and a regression here must not "
                             "fall through to a real schtasks/systemctl call")
    monkeypatch.setattr(cli, "_cmd_schedule_remove_all", boom)

    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "show", "--all"])
    assert e.value.code == 2 and "--all" in capsys.readouterr().err


def test_schedule_install_is_no_longer_a_valid_action(monkeypatch, capsys, tmp_path):
    """`install` went away with the OS scheduler (2026-09-25 in-app scheduler): a schedule is
    turned on from the Schedules page, not installed by the CLI. argparse refuses the action
    before `cmd_schedule` ever runs."""
    from fridgesheet import cli, config
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)

    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "install"])
    assert e.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_schedule_remove_all_never_creates_a_home_or_database_that_was_not_there(monkeypatch, tmp_path):
    """A parent who deleted `%LOCALAPPDATA%\\fridgesheet` before uninstalling must not get it
    back. Two side effects would hand it back: `reports.available`'s `db.open_db` (which
    `_schedule_removal_keys` avoids by gating on `db_path.is_file()`), and `load_settings`'s
    closing `for d in (s.home, s.profile_dir, s.cache_dir): d.mkdir(...)`. Both are wrong here,
    because `installer.iss`'s post-uninstall message box points a parent straight at that
    folder and calls whatever is in it "kept" data -- and a folder the uninstaller made three
    seconds ago is not kept data.

    This test drives the real settings load. The version it replaces stubbed
    `cli.load_settings` out, i.e. replaced the very function whose `mkdir` created the folder,
    so its `assert not home.exists()` was a property of the stub and passed against the bug.
    `config.DEFAULT_HOME` is the honest seam: it is what `config_file()` and a bare
    `Settings()` both read, and nothing on this path is faked."""
    from fridgesheet import cli, config
    from fridgesheet.web import db as web_db

    home = tmp_path / "fresh-home"           # deliberately not created by anything above
    removed = []
    monkeypatch.setattr(config, "DEFAULT_HOME", home)
    monkeypatch.setattr(scheduling, "remove", lambda key, **kw: removed.append(key))

    def never(*a, **k):
        raise AssertionError("the --all path must not call load_settings: it creates home, "
                             "browser-profile and cache as a side effect")
    monkeypatch.setattr(cli, "load_settings", never)

    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "remove", "--all"])

    assert e.value.code == 0
    assert removed == ["data-refresh", "open-work"]  # no config.toml, no database: the code report,
                                                      # plus the refresh key added unconditionally
    assert not home.exists()                 # neither the folder...
    assert not web_db.db_path(home).exists() # ...nor fridgesheet.db was created to check for more


def test_schedule_remove_all_still_removes_what_it_can_when_config_toml_will_not_parse(monkeypatch, capsys, tmp_path):
    """An unreadable `config.toml` must not be the end of the uninstall.

    `load_settings` raises `ConfigError` for a file tomllib cannot parse, and `main()` has no
    handler for it, so `schedule remove --all` used to die with a traceback *before*
    `_schedule_removal_keys` ran a single removal. `[UninstallRun]` is `runhidden` and ignores
    exit codes, so every scheduled task survived the uninstall with nothing on screen saying
    so. `_schedule_removal_keys` already degrades gracefully for an unreadable *database*; the
    config file -- which its own docstring calls the source that works "database or no
    database" -- cannot be the fatal one."""
    from fridgesheet import cli, config

    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text('[reports."view:7"\nenabled = true\n', encoding="utf-8")   # no closing ]
    removed = []
    monkeypatch.setattr(config, "DEFAULT_HOME", home)
    monkeypatch.setattr(scheduling, "remove", lambda key, **kw: removed.append(key))

    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "remove", "--all"])

    assert e.value.code == 1                 # incomplete -- the same 1 an unreadable database gives
    assert removed == ["data-refresh", "open-work"]  # the code reports (and the refresh key) still go
    err = capsys.readouterr().err
    assert "cannot parse" in err and "config.toml" in err


@pytest.mark.parametrize("toml_text", ['reports = "oops"\n',                              # not a table
                                       '[reports.open-work]\ndays = 5\n',                 # not iterable
                                       '[reports.open-work]\ndays = "Mon"\n'])            # iterable, wrong
def test_schedule_remove_all_survives_a_reports_value_of_the_wrong_shape(monkeypatch, capsys, tmp_path, toml_text):
    """More ways `config.toml` goes wrong, past the two `ConfigError` cases above: it parses
    fine, and every `.time` is fine too, but some value under `reports` is not the shape the
    reader assumed (hand edited, or written by a future version).

    `settings_from_doc` read both of these straight off the document with no type check --
    `(doc.get("reports") or {}).items()` and `[str(d) for d in sect.get("days", WEEKDAYS)]` --
    so `reports = "oops"` raised `AttributeError` and `days = 5` raised `TypeError`, each
    straight out of `_removal_settings`, past the `except ConfigError` that was the only guard
    there. `main()` has no handler for either, so both were the same silent-uninstall failure
    as a parse error: a traceback `runhidden` swallows and `[UninstallRun]` never checks,
    before a single schedule is removed, orphaning every task including the code reports.

    Both are now fixed at the root, in `settings_from_doc`, so every caller gets it (a plain
    `fridgesheet status` died on these too). A value of the wrong shape is ignored the way
    `[web].port` and `[kids].nicknames` already ignore one, which means this run is not
    degraded at all: the removal list is complete -- a file with no readable `[reports.<key>]`
    table has no schedule to miss -- so it exits 0, where the first draft of this test wanted
    the 1 an unreadable *file* gives. That is deliberate; an exit 1 here claimed an
    incompleteness that never existed."""
    from fridgesheet import cli, config

    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text(toml_text, encoding="utf-8")
    removed = []
    monkeypatch.setattr(config, "DEFAULT_HOME", home)
    monkeypatch.setattr(scheduling, "remove", lambda key, **kw: removed.append(key))

    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "remove", "--all"])

    assert e.value.code == 0
    assert removed == ["data-refresh", "open-work"]  # the code reports (and the refresh key) still go
    assert "Traceback" not in capsys.readouterr().err


def test_removal_settings_degrades_for_any_shape_settings_from_doc_can_raise(monkeypatch, tmp_path):
    """Belt and braces behind the root-cause fix above. `_removal_settings` named the exception
    types it had seen (`ConfigError`, then `AttributeError`); the next unguarded `str()`/`int()`
    /iteration added to `settings_from_doc` would be a third type, and this call site is the one
    where an escaping exception costs the parent every scheduled task with nothing on screen.
    Whatever the reader raises, the keys are still taken off the raw document and the caller is
    told the settings are degraded."""
    from fridgesheet import cli, config

    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text('[reports."view:7"]\nenabled = true\n', encoding="utf-8")
    monkeypatch.setattr(config, "DEFAULT_HOME", home)

    def boom(doc, s):
        raise ValueError("a shape nobody guarded")
    monkeypatch.setattr(cli, "settings_from_doc", boom)

    s, degraded = cli._removal_settings()
    assert set(s.reports) == {"view:7"}               # every table on the raw document still named
    assert "a shape nobody guarded" in degraded and "config.toml" in degraded


def test_schedule_remove_all_survives_a_config_toml_it_cannot_even_open(monkeypatch, tmp_path):
    """The other way `config.toml` goes wrong: it parses fine, nothing can read it. A
    permission the uninstaller does not have, or a file some other tool wrote in an encoding
    `read_text` refuses, raises `OSError`/`UnicodeDecodeError` out from under `ConfigError` --
    and an uninstall that dies on those is the same silent failure as one that dies on a
    missing bracket. Injected rather than chmod'd, so it behaves the same on Windows and when
    the suite is run as root."""
    from fridgesheet import cli, config

    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)

    def denied(path):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(cli, "load_config_doc", denied)

    s, degraded = cli._removal_settings()
    assert s.reports == {} and "Permission denied" in degraded
    assert not (tmp_path / "browser-profile").exists()          # and still nothing created


def test_schedule_remove_all_survives_one_unusable_report_time(monkeypatch, capsys, tmp_path):
    """The other half of `ConfigError`: a single `[reports.<key>].time` that is not HH:MM (hand
    edited, or written by a build that allowed something this one does not). It used to kill
    the whole uninstall; now the other tables are still removed, taken off the raw document
    that parsed perfectly well, and the exit code says the run was incomplete."""
    from fridgesheet import cli, config

    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text('[reports."view:5"]\ntime = "not-a-time"\n\n'
                                      '[reports."view:7"]\ntime = "16:00"\n', encoding="utf-8")
    removed = []
    monkeypatch.setattr(config, "DEFAULT_HOME", home)
    monkeypatch.setattr(scheduling, "remove", lambda key, **kw: removed.append(key))

    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "remove", "--all"])

    assert e.value.code == 1
    # view:5 is the one that raised, and it is still removed: the key is all `remove` needs.
    assert sorted(removed) == ["data-refresh", "open-work", "view:5", "view:7"]
    assert "HH:MM" in capsys.readouterr().err


def test_schedule_remove_all_leaves_alone_a_config_key_that_is_not_a_report(monkeypatch, capsys, tmp_path):
    """`--all` drops the single-key path's `reports.resolve` gate by design, and feeds raw
    `[reports.<key>]` table names off disk to `scheduling.remove`. `[reports.Web]` hand-edited
    into config.toml renders to "Fridge Sheet - Web", and Task Scheduler's namespace is
    case-insensitive: that is the web server's own logon task, and deleting it takes the server
    away until someone reinstalls. `--all` cannot call `resolve` (it would open, and so create,
    a database), so it gates on the key's spelling instead -- exactly the spellings `resolve`
    accepts, and no others."""
    from fridgesheet import cli, config

    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text('[reports.Web]\nenabled = true\n\n'
                                      '[reports.web]\nenabled = true\n\n'
                                      '[reports."view:007"]\nenabled = true\n\n'
                                      '[reports."view:7"]\nenabled = true\n', encoding="utf-8")
    removed = []
    monkeypatch.setattr(config, "DEFAULT_HOME", home)
    monkeypatch.setattr(scheduling, "remove", lambda key, **kw: removed.append(key))

    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "remove", "--all"])

    assert e.value.code == 0                             # nothing of ours was left behind
    assert sorted(removed) == ["data-refresh", "open-work", "view:7"]    # not Web, not web, not view:007
    err = capsys.readouterr().err
    assert "Web" in err and "web" in err and "view:007" in err   # skipped out loud, not silently


def test_schedule_remove_all_still_removes_everything_it_knows_about_when_the_database_cannot_be_read(monkeypatch, tmp_path):
    """#36 fix-round-1, Important 1: a parent installs a build that migrates `fridgesheet.db` to a
    newer schema, then rolls back to this build and uninstalls. `db.migrate` raises for a
    schema newer than this build understands; `reports.available` would swallow that (right for
    a page render, wrong for an uninstaller) and silently report zero saved reports, leaving
    "Fridge Sheet - view 7" firing forever with exit code 0.

    `config.toml`'s `[reports."view:7"]` table -- the Schedules page's own record, independent
    of the database -- is what actually saves this: `scheduling.remove("view:7")` still gets
    called even though the database that would explain what report 7 *is* cannot be read. The
    exit code says the run was incomplete anyway, so the failure is not silent."""
    from fridgesheet import cli, config
    from fridgesheet.web import db as web_db

    home = tmp_path
    (home / "config.toml").write_text('[reports."view:7"]\nenabled = true\ntime = "16:00"\ndays = ["Fri"]\n',
                                      encoding="utf-8")

    # A database from a future build: schema_version higher than this build's SCHEMA_VERSION,
    # so db.migrate() raises rather than silently upgrading or downgrading anything.
    conn = web_db.connect(web_db.db_path(home))
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version(version) VALUES (?)", (web_db.SCHEMA_VERSION + 1,))
    conn.close()

    removed = []
    monkeypatch.setattr(config, "DEFAULT_HOME", home)
    monkeypatch.setattr(scheduling, "remove", lambda key, **kw: removed.append(key))

    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "remove", "--all"])

    assert e.value.code == 1              # incomplete, not a clean 0 -- something could not be read
    assert sorted(removed) == ["data-refresh", "open-work", "view:7"]   # ...but still removed, via config.toml alone


def test_command_for_source_and_frozen(monkeypatch, tmp_path):
    import sys
    monkeypatch.delattr(sys, "frozen", raising=False)
    exe, args, wd = scheduling.command_for("open-work")
    assert exe == sys.executable and args == "-m fridgesheet.cli run open-work --no-refresh --trigger schedule" and wd == str(Path.cwd())
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    # The frozen exe is always the Windows build, so its folder is a Windows path wherever the
    # test runs (as `service.command_for` already assumes).
    monkeypatch.setattr(sys, "executable", r"C:\App\FridgeSheet.exe")
    exe, args, wd = scheduling.command_for("open-work")
    assert exe.endswith("FridgeSheet.exe") and args == "run open-work --no-refresh --trigger schedule" and wd == r"C:\App"


def test_schedule_show_lists_next_and_last(tmp_path, monkeypatch, capsys):
    """`schedule show` (no key needed -- it lists every schedule) reads the same plan the
    clock acts on (`clock.configured` / `schedule_plan.next_run`), not an OS scheduler: a
    freshly-enabled schedule has a next run but has never fired on a schedule yet."""
    from fridgesheet import cli, config
    doc = {"reports": {"open-work": {"enabled": True, "time": "14:00", "days": list(host.DAY_NAMES)}}}
    config.save_config_doc(tmp_path / "config.toml", doc)

    def _load():
        s = config.Settings(home=tmp_path)
        config.settings_from_doc(doc, s)
        return s

    monkeypatch.setattr(cli, "load_settings", _load)
    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "show"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert "open-work: next" in out and "has not run on a schedule yet" in out


# --- multi-time schedules and the reserved data-refresh key ----------------------------

def test_check_schedule_times_accepts_a_list():
    host.check_schedule_times(["06:00", "09:00", "12:00"], ["Mon", "Tue"])


def test_check_schedule_times_refuses_an_empty_list():
    with pytest.raises(host.SchedulingError, match="no times"):
        host.check_schedule_times([], ["Mon"])


def test_check_schedule_times_refuses_the_one_bad_time_among_good_ones():
    """Every time is checked before any file is written, so a bad one leaves nothing behind."""
    with pytest.raises(host.SchedulingError, match="HH:MM"):
        host.check_schedule_times(["06:00", "9:00", "12:00"], ["Mon"])


def test_the_data_refresh_key_is_reserved_however_it_is_spelled():
    """Task Scheduler's namespace is case-insensitive, so a hand-edited [reports.Data-Refresh]
    would otherwise collide with the app's own task."""
    for spelling in ("data-refresh", "Data-Refresh", "DATA-REFRESH", " data-refresh "):
        assert host.is_reserved(spelling), spelling
    assert not host.is_reserved("open-work")
    assert not host.is_reserved("view:3")


def test_the_reserved_key_does_not_collide_with_a_protected_name():
    """The whole point of the name: the hand-written refresh pair stays protected and the
    app's own schedule sits beside it."""
    from fridgesheet.host import scheduling_linux, scheduling_windows
    unit = scheduling_linux.timer_unit(host.DATA_REFRESH_KEY)
    assert unit not in scheduling_linux._FOREIGN_UNITS
    assert unit == "fridgesheet-data-refresh.timer"
    name = host.task_name(host.DATA_REFRESH_KEY)
    assert name.strip().casefold() not in scheduling_windows._FOREIGN_TASKS_FOLDED


def test_one_time_renders_exactly_what_it_rendered_before():
    """The byte-identical promise: every task already installed keeps its current XML, so
    nothing on a machine the author cannot reach needs reinstalling."""
    xml = scheduling_windows.render_task_xml("Fridge Sheet - open-work", ["14:00"], ["Mon", "Fri"],
                                             "C:\\app\\FridgeSheet.exe", "run open-work --no-refresh", "C:\\app")
    assert xml.count("<CalendarTrigger>") == 1
    assert "<StartBoundary>2026-01-01T14:00:00</StartBoundary>" in xml
    assert "          <Monday />\n          <Friday />" in xml


def test_several_times_render_one_trigger_each():
    xml = scheduling_windows.render_task_xml("Fridge Sheet - data-refresh", ["06:00", "09:00", "12:00"],
                                             ["Mon"], "C:\\app\\FridgeSheet.exe", "refresh --record", "C:\\app")
    assert xml.count("<CalendarTrigger>") == 3
    for t in ("06:00", "09:00", "12:00"):
        assert f"<StartBoundary>2026-01-01T{t}:00</StartBoundary>" in xml
    assert xml.count("<Monday />") == 3          # every trigger carries its own day list


def test_a_bad_time_among_good_ones_renders_nothing():
    with pytest.raises(host.SchedulingError):
        scheduling_windows.render_task_xml("Fridge Sheet - data-refresh", ["06:00", "nope"], ["Mon"],
                                           "exe", "args", "wd")


def test_command_for_the_refresh_key_records_the_run(monkeypatch):
    """A report's schedule runs `--no-refresh` and trusts the snapshot. This is what makes
    the snapshot trustworthy -- and it must be `refresh --record`, not bare `refresh`, which
    writes snapshot.json and never ingests, so the kiosk would never change."""
    from fridgesheet.host import scheduling
    monkeypatch.setattr(scheduling.sys, "frozen", False, raising=False)
    _, args, _ = scheduling.command_for(host.DATA_REFRESH_KEY)
    assert args.endswith("refresh --record")
    assert "--no-refresh" not in args


def test_command_for_a_report_is_unchanged(monkeypatch):
    from fridgesheet.host import scheduling
    monkeypatch.setattr(scheduling.sys, "frozen", False, raising=False)
    _, args, _ = scheduling.command_for("open-work")
    assert args.endswith("run open-work --no-refresh --trigger schedule")


def test_command_for_the_refresh_key_records_the_run_when_frozen(monkeypatch, tmp_path):
    """The PyInstaller branch is the production path on the household's Windows machine (a
    frozen `FridgeSheet.exe`), but only the non-frozen branch above was ever pinned. Same
    assertion as `test_command_for_the_refresh_key_records_the_run`, against `sys.frozen`."""
    from fridgesheet.host import scheduling
    monkeypatch.setattr(scheduling.sys, "frozen", True, raising=False)
    monkeypatch.setattr(scheduling.sys, "executable", r"C:\App\FridgeSheet.exe")
    exe, args, wd = scheduling.command_for(host.DATA_REFRESH_KEY)
    assert exe.endswith("FridgeSheet.exe")
    assert args == "refresh --record"          # no "-m fridgesheet.cli" prefix, and no --no-refresh
    assert wd == r"C:\App"
