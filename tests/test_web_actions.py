"""The settings app's actions, with every host adapter and the runner faked."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fridgesheet import config
from fridgesheet.web import actions

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fridgesheet import host, late_rules, runner
from fridgesheet.config import Settings
from fridgesheet.host import ScheduleInfo, selfupdate
from fridgesheet.web import db
from fridgesheet.web import updates as web_updates
from fridgesheet.web.stores import reports as reportstore
from fridgesheet.web.stores import runs as runstore

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 14, 14, 5, tzinfo=TZ)


def test_load_form_defaults_when_no_config(tmp_path):
    f = actions.load_form(tmp_path)
    assert f == actions.FormValues()
    assert actions.stored_username(tmp_path) == ""


def test_load_form_reads_every_field(tmp_path):
    config.save_config_doc(tmp_path / "config.toml", {
        "account": {"username": "p@x.com"},
        "print": {"printer": "Office", "archive": "D:/Drive/Sheets"},
        "kids": {"nicknames": {"Alex": "Al", "Katherine": "Kate"}},
        "reports": {"open-work": {"enabled": True, "time": "15:30", "days": ["Mon", "Wed"], "days_ahead": 7, "overdue_days": 21}},
    })
    f = actions.load_form(tmp_path)
    assert f == actions.FormValues(username="p@x.com", password="", printer="Office", days_ahead=7, overdue_days=21,
                                   nicknames="Alex=Al\nKatherine=Kate", archive="D:/Drive/Sheets")
    assert actions.stored_username(tmp_path) == "p@x.com"


def test_run_doctor_streams_lines_and_returns_verdict(tmp_path):
    lines = []
    fake = lambda settings, home, probes=None: ("OK    python: 3.12\nFAIL  boom: x\n1 check(s) failed", False)  # noqa: E731
    assert actions.run_doctor(home=tmp_path, log=lines.append, settings=Settings(home=tmp_path), run=fake) is False
    assert lines == ["OK    python: 3.12", "FAIL  boom: x", "1 check(s) failed"]


def test_run_doctor_survives_a_broken_config(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)
    (tmp_path / "config.toml").write_text("[print\n")
    lines = []
    calls = []

    def fake(settings, home, probes=None):
        calls.append(settings)
        return "OK    python: 3.12\nAll checks passed", True

    ok = actions.run_doctor(home=tmp_path, log=lines.append, run=fake)
    assert ok is True
    assert len(calls) == 1 and calls[0].home == tmp_path
    assert any("config.toml" in line for line in lines)


def test_load_form_surfaces_a_broken_config(tmp_path):
    (tmp_path / "config.toml").write_text("[print\n")
    with pytest.raises(config.ConfigError, match="config.toml"):
        actions.load_form(tmp_path)


def test_load_form_tolerates_garbage_day_counts(tmp_path):
    config.save_config_doc(tmp_path / "config.toml", {
        "reports": {"open-work": {"days_ahead": "two weeks", "overdue_days": [1]}},
    })
    f = actions.load_form(tmp_path)
    assert f.days_ahead == 14
    assert f.overdue_days == 14


def test_nickname_lines_round_trip_and_reject_garbage():
    assert actions.parse_nickname_lines(" Alex = Al \n\nKatherine=Kate\n") == {"Alex": "Al", "Katherine": "Kate"}
    assert actions.format_nicknames({"Alex": "Al", "Katherine": "Kate"}) == "Alex=Al\nKatherine=Kate"
    with pytest.raises(ValueError, match="line 2"):
        actions.parse_nickname_lines("Alex=Al\nnot a pair\n")
    with pytest.raises(ValueError, match="line 1"):
        actions.parse_nickname_lines("=Al")


def _form(**over) -> actions.FormValues:
    d = dict(username="p@x.com", password="hunter2", printer="", days_ahead=14, overdue_days=14, nicknames="", archive="")
    d.update(over)
    return actions.FormValues(**d)


def test_validate_accepts_a_good_form():
    assert actions.validate(_form(), stored="") == []
    assert actions.validate(_form(password=""), stored="p@x.com") == []      # keep stored password


def test_validate_requires_username_and_a_password_for_a_new_username():
    assert any("username" in e.lower() for e in actions.validate(_form(username="  "), stored=""))
    assert any("password" in e.lower() for e in actions.validate(_form(password=""), stored=""))
    assert any("password" in e.lower() for e in actions.validate(_form(username="new@x.com", password=""), stored="old@x.com"))


def test_validate_checks_day_ranges_and_nicknames():
    assert any("days ahead" in e.lower() for e in actions.validate(_form(days_ahead=0), stored=""))
    assert any("overdue" in e.lower() for e in actions.validate(_form(overdue_days=61), stored=""))
    assert any("line 1" in e for e in actions.validate(_form(nicknames="bad"), stored=""))
    errs = actions.validate(_form(username="", days_ahead=99), stored="")
    assert len(errs) == 2            # one message per problem, none swallowed


def test_validate_reports_non_numeric_days_instead_of_raising():
    errs = actions.validate(_form(days_ahead="", overdue_days="abc"), stored="")   # type: ignore[arg-type]
    assert len(errs) == 2 and all("whole number" in e for e in errs)
    assert actions.validate(_form(days_ahead="7", overdue_days=" 21 "), stored="") == []   # type: ignore[arg-type]


class _Cred:
    def __init__(self):
        self.written = []

    def write(self, username, password):
        self.written.append((username, password))


def _save(tmp_path, form, **kw):
    lines = []
    cred = kw.pop("cred", _Cred())
    r = actions.save(form, home=tmp_path, log=lines.append, credstore=cred, **kw)
    return r, lines, cred


def test_save_rejects_an_invalid_form_and_writes_nothing(tmp_path):
    r, lines, cred = _save(tmp_path, _form(username=""))
    assert not r.ok and any("username" in m.lower() for m in r.messages)
    assert not (tmp_path / "config.toml").exists() and cred.written == []


def test_save_writes_config_and_stores_the_password(tmp_path):
    r, lines, cred = _save(tmp_path, _form(printer="Office", nicknames="Alex=Al", archive="D:/S", days_ahead=7))
    assert r.ok
    doc = config.load_config_doc(tmp_path / "config.toml")
    assert doc["account"] == {"username": "p@x.com"}
    assert doc["print"] == {"printer": "Office", "archive": "D:/S"}
    assert doc["kids"] == {"nicknames": {"Alex": "Al"}}
    assert doc["reports"]["open-work"] == {"days_ahead": 7, "overdue_days": 14}   # enabled/time/days: the Schedules page's alone
    assert cred.written == [("p@x.com", "hunter2")]
    assert "hunter2" not in " ".join(lines + r.messages) and "hunter2" not in (tmp_path / "config.toml").read_text()


def test_save_never_touches_a_schedule_already_on_the_report(tmp_path):
    """The regression this task exists to prevent: Settings used to default `days` to
    Mon-Fri on every save, which overwrote whatever the parent chose on the Schedules page."""
    config.save_config_doc(tmp_path / "config.toml", {"account": {"username": "p@x.com"},
                                                      "reports": {"open-work": {"enabled": True, "time": "15:00", "days": ["Mon"]}}})
    r, *_ = _save(tmp_path, _form(password=""))
    assert r.ok
    doc = config.load_config_doc(tmp_path / "config.toml")
    assert doc["reports"]["open-work"]["enabled"] is True
    assert doc["reports"]["open-work"]["time"] == "15:00"
    assert doc["reports"]["open-work"]["days"] == ["Mon"]


def test_save_tolerates_scalar_sections_in_an_existing_config(tmp_path):
    (tmp_path / "config.toml").write_text('print = "oops"\naccount = 5\n')
    r, *_ = _save(tmp_path, _form())
    assert r.ok
    doc = config.load_config_doc(tmp_path / "config.toml")
    assert doc["print"]["printer"] == "" and doc["account"]["username"] == "p@x.com"


def test_save_keeps_the_config_when_the_credential_store_fails(tmp_path):
    class BadCred:
        def write(self, username, password):
            raise RuntimeError("credential store write failed: backend locked")

    r, lines, _ = _save(tmp_path, _form(), cred=BadCred())
    assert not r.ok
    assert any("could not be stored" in m and "backend locked" in m for m in r.messages)
    assert "hunter2" not in " ".join(lines + r.messages)
    assert config.load_config_doc(tmp_path / "config.toml")["account"]["username"] == "p@x.com"   # config was written first


def test_test_login_writes_the_stamp_on_success_and_removes_it_on_failure(tmp_path):
    lines = []
    ok = actions.test_login(home=tmp_path, log=lines.append, settings=Settings(home=tmp_path),
                            check=lambda s, log: {"Canvas": None, "HAC": None}, now=NOW)
    assert ok.ok and ok.results == {"Canvas": None, "HAC": None} and "OK" in ok.message
    assert (tmp_path / actions.LOGIN_STAMP).read_text() == NOW.isoformat()
    assert any("Canvas: OK" in l for l in lines) and any("HAC: OK" in l for l in lines)
    bad = actions.test_login(home=tmp_path, log=lines.append, settings=Settings(home=tmp_path),
                             check=lambda s, log: {"Canvas": None, "HAC": "LoginRequired: OneLogin did not redirect"}, now=NOW)
    assert not bad.ok and "HAC" in bad.message and "did not redirect" in bad.message
    assert not (tmp_path / actions.LOGIN_STAMP).exists()


def test_test_login_treats_an_exception_from_the_checker_as_failure(tmp_path):
    def boom(s, log):
        raise RuntimeError("No credentials available. Run set-credentials")
    r = actions.test_login(home=tmp_path, log=lambda l: None, settings=Settings(home=tmp_path), check=boom, now=NOW)
    assert not r.ok and "No credentials" in r.message and not (tmp_path / actions.LOGIN_STAMP).exists()


def _record_run(home, key, pdf, *, started="2026-09-14T14:05:00-04:00", finished="2026-09-14T14:05:01-04:00"):
    """What the real runner does on every branch (including dry-run): write the PDF it built
    into the `runs` row so `preview` can read the path back instead of guessing it."""
    conn = db.open_db(home)
    try:
        runstore.record(conn, key, started, finished, "web", "OK", "dry-run built", pdf_path=str(pdf))
    finally:
        conn.close()


def test_preview_runs_a_forced_dry_run_and_opens_the_pdf(tmp_path):
    seen, opened, lines = {}, [], []

    def fake_run(key, opts, settings, **kw):
        seen["key"], seen["opts"], seen["echo"] = key, opts, kw.get("echo")
        kw["echo"]("2026-09-14 14:05:00 OK    open-work dry-run built x")
        pdf = tmp_path / "sheets" / "2026-09-14" / "sheet.pdf"
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_text("pdf")
        _record_run(tmp_path, key, pdf)
        return 0

    log = lines.append          # one bound method, so the identity check below is meaningful
    pdf = actions.preview(home=tmp_path, log=log, settings=Settings(home=tmp_path), run=fake_run, opener=opened.append, today=NOW.date())
    assert pdf == tmp_path / "sheets" / "2026-09-14" / "sheet.pdf" and opened == [pdf]
    assert seen["key"] == "open-work" and seen["opts"] == runner.RunOptions(dry_run=True, force=True, notify=False, trigger="web", no_refresh=True)
    assert seen["opts"].trigger == "web"
    assert seen["echo"] is log and any("dry-run built" in l for l in lines)
    assert actions.preview(home=tmp_path, log=log, settings=Settings(home=tmp_path), run=lambda *a, **k: 1, opener=opened.append, today=NOW.date()) is None
    assert len(opened) == 1


def test_preview_returns_none_when_the_run_skipped_without_building(tmp_path):
    opened, lines = [], []

    def fake_run(key, opts, settings, **kw):
        kw["echo"]("2026-09-14 14:05:00 SKIP  open-work already running (run.lock present); nothing done")
        return 0

    pdf = actions.preview(home=tmp_path, log=lines.append, settings=Settings(home=tmp_path), run=fake_run, opener=opened.append, today=NOW.date())
    assert pdf is None and opened == []


def test_preview_of_a_saved_report_opens_the_pdf_the_run_recorded_not_a_stale_one(tmp_path):
    """A saved view report's PDF lands at reports/view-<id>/<day>/report.pdf. Finding 1: resolving
    only the output_dir and globbing the day's directory sorts by filename, so a stale `old.pdf`
    left over from an earlier run would win over the `report.pdf` this run just built. Reading the
    path back from the `runs` row the run itself recorded must find the real file instead."""
    conn = db.open_db(tmp_path)
    d = {"title": "Mine", "source": "items", "columns": ["kid", "name"]}
    rid = reportstore.create(conn, "Mine", json.dumps(d), now="2026-09-14T08:00:00-04:00")
    conn.close()
    key = f"view:{rid}"

    day_dir = tmp_path / f"reports/view-{rid}" / "2026-09-14"
    day_dir.mkdir(parents=True)
    (day_dir / "old.pdf").write_text("stale")           # alphabetically earlier than report.pdf
    real_pdf = day_dir / "report.pdf"

    opened = []

    def fake_run(k, opts, settings, **kw):
        kw["echo"]("2026-09-14 14:05:00 OK    view dry-run built x")
        real_pdf.write_text("real")
        _record_run(tmp_path, k, real_pdf)
        return 0

    pdf = actions.preview(home=tmp_path, log=lambda l: None, settings=Settings(home=tmp_path),
                          run=fake_run, opener=opened.append, today=NOW.date(), report_key=key)
    assert pdf == real_pdf and opened == [pdf]


def test_print_now_forces_a_reprint(tmp_path):
    seen = {}

    def fake_run(key, opts, settings, **kw):
        seen["opts"] = opts
        return 0

    assert actions.print_now(home=tmp_path, log=lambda l: None, settings=Settings(home=tmp_path), run=fake_run) == 0
    assert seen["opts"] == runner.RunOptions(force=True, reprint=True, force_print=True, trigger="web", no_refresh=True)
    assert seen["opts"].trigger == "web"
    # `force_print` is what makes the button print a report whose schedule is PDF-only; the
    # schedule's own run has no such flag and still only builds.
    assert seen["opts"].force_print is True
    assert actions.print_now(home=tmp_path, log=lambda l: None, settings=Settings(home=tmp_path), run=fake_run,
                             date="2026-09-14") == 0
    assert seen["opts"] == runner.RunOptions(force=True, reprint=True, force_print=True, date="2026-09-14", trigger="web", no_refresh=True)


def test_preview_and_print_now_can_force_a_refresh_first(tmp_path):
    """The "Refresh data first" checkbox: when checked, `refresh=True` reaches the runner as
    `no_refresh=False` -- the old, always-pull behaviour -- instead of the new fast default."""
    seen = {}

    def fake_run(key, opts, settings, **kw):
        seen["opts"] = opts
        return 0

    actions.preview(home=tmp_path, log=lambda l: None, settings=Settings(home=tmp_path), run=fake_run,
                    opener=lambda p: None, today=NOW.date(), refresh=True)
    assert seen["opts"] == runner.RunOptions(dry_run=True, force=True, notify=False, trigger="web", no_refresh=False)

    actions.print_now(home=tmp_path, log=lambda l: None, settings=Settings(home=tmp_path), run=fake_run, refresh=True)
    assert seen["opts"] == runner.RunOptions(force=True, reprint=True, force_print=True, trigger="web", no_refresh=False)


def test_status_line_reports_last_run_and_next_run(tmp_path):
    assert actions.status_line(tmp_path, describe=lambda k: ScheduleInfo("task-scheduler", False, None, None)) == "No runs yet · not scheduled"
    (tmp_path / runner.LOG_NAME).write_text("old line\n2026-09-14 14:05:00 OK    open-work printed job=1\n")
    s = actions.status_line(tmp_path, describe=lambda k: ScheduleInfo("task-scheduler", True, "9/15/2026 2:00:00 PM", "0"))
    assert s == "2026-09-14 14:05:00 OK    open-work printed job=1 · next run 9/15/2026 2:00:00 PM"
    s = actions.status_line(tmp_path, describe=lambda k: ScheduleInfo("systemd", True, "Tue 2026-09-15 14:00:00 EDT", None))
    assert s.endswith("· next run Tue 2026-09-15 14:00:00 EDT (systemd)")
    s = actions.status_line(tmp_path, describe=lambda k: ScheduleInfo("task-scheduler", True, None, None))
    assert s.endswith("· scheduled (next run unknown)")

    def boom(k):
        raise RuntimeError("boom")
    s = actions.status_line(tmp_path, describe=boom)
    assert s.endswith("· schedule unknown")


def test_form_carries_web_fields_and_validates_the_port(tmp_path):
    (tmp_path / "config.toml").write_text('[web]\nport = 9000\nallow_lan = true\n')
    f = actions.load_form(tmp_path)
    assert (f.port, f.allow_lan) == (9000, True)
    assert actions.load_form(tmp_path / "none").port == 8433
    f = actions.FormValues(username="u", password="p", port=80)
    assert any("1024" in e for e in actions.validate(f, stored=""))
    f.port = 8433
    assert not [e for e in actions.validate(f, stored="") if "port" in e.lower()]


def test_save_writes_web_section_and_flags_a_restart(tmp_path):
    form = actions.FormValues(username="u", password="p", port=9000, allow_lan=True)
    r = actions.save(form, home=tmp_path, log=lambda s: None, credstore=_Cred())
    assert r.ok and r.restart_needed
    doc = config.load_config_doc(tmp_path / "config.toml")
    assert doc["web"] == {"port": 9000, "allow_lan": True, "check_updates": True}
    r = actions.save(form, home=tmp_path, log=lambda s: None, credstore=_Cred())
    assert r.ok and not r.restart_needed


def test_late_rules_settings_seeds_the_file_and_parses_it(tmp_path):
    rules = actions.late_rules_settings(tmp_path)
    assert (tmp_path / "late-rules.toml").is_file()
    assert rules.default.late_days == 14 and rules.default.credit == "?"


def test_save_late_rules_writes_default_quarters_and_rules(tmp_path):
    errors = actions.save_late_rules(
        tmp_path, default_late_days="10", default_credit="?",
        quarter_dates=["2026-10-15", "2026-12-18"],
        rule_kid=["Alex"], rule_course=["Band"], rule_mode=["days"],
        rule_late_days=["7"], rule_credit=["50%"], rule_source=["syllabus"],
    )
    assert errors == []
    rules = late_rules.load(tmp_path / "late-rules.toml")
    assert rules.default.late_days == 10
    assert rules.quarters == [date(2026, 10, 15), date(2026, 12, 18)]
    r = rules.rules[0]
    assert (r.kid, r.course, r.late_days, r.credit, r.source) == ("Alex", "Band", 7, "50%", "syllabus")


def test_save_late_rules_supports_quarter_end_mode(tmp_path):
    errors = actions.save_late_rules(
        tmp_path, default_late_days="14", default_credit="",
        quarter_dates=["2026-10-15"],
        rule_kid=[""], rule_course=["Band"], rule_mode=["quarter_end"],
        rule_late_days=[""], rule_credit=[""], rule_source=[""],
    )
    assert errors == []
    r = late_rules.load(tmp_path / "late-rules.toml").rules[0]
    assert r.until == "quarter_end" and r.late_days is None


def test_save_late_rules_rejects_a_non_numeric_default_and_writes_nothing(tmp_path):
    actions.late_rules_settings(tmp_path)      # seed
    before = (tmp_path / "late-rules.toml").read_text()
    errors = actions.save_late_rules(
        tmp_path, default_late_days="seven", default_credit="",
        quarter_dates=[], rule_kid=[], rule_course=[], rule_mode=[], rule_late_days=[], rule_credit=[], rule_source=[],
    )
    assert errors
    assert (tmp_path / "late-rules.toml").read_text() == before


def test_save_late_rules_reports_a_bad_rule_days_value(tmp_path):
    errors = actions.save_late_rules(
        tmp_path, default_late_days="14", default_credit="",
        quarter_dates=[], rule_kid=[""], rule_course=["Band"], rule_mode=["days"],
        rule_late_days=["not-a-number"], rule_credit=[""], rule_source=[""],
    )
    assert errors and not (Path(tmp_path) / "late-rules.toml").exists()


def test_save_late_rules_reports_a_bad_quarter_date(tmp_path):
    errors = actions.save_late_rules(
        tmp_path, default_late_days="14", default_credit="",
        quarter_dates=["not-a-date"], rule_kid=[], rule_course=[], rule_mode=[], rule_late_days=[], rule_credit=[], rule_source=[],
    )
    assert errors


def test_no_print_days_settings_seeds_the_file_and_parses_it(tmp_path):
    entries = actions.no_print_days_settings(tmp_path)
    assert (tmp_path / "no-print-days.txt").is_file()
    assert any(e.note == "Labor Day" for e in entries)


def test_save_no_print_days_writes_entries(tmp_path):
    errors = actions.save_no_print_days(tmp_path, [runner.SkipEntry(date(2026, 12, 25), None, "Christmas")])
    assert errors == []
    assert "Christmas" in (tmp_path / "no-print-days.txt").read_text()


def test_late_rules_view_renders_a_register_as_editable_strings():
    rules = late_rules.LateRules(
        default=late_rules.Rule(late_days=14, credit="?"),
        rules=[late_rules.Rule(course="Band", until="quarter_end", late_days=None),
               late_rules.Rule(kid="Alex", late_days=7, credit="50%", source="syllabus")],
        quarters=[date(2026, 10, 15)],
    )
    v = actions.late_rules_view(rules)
    assert v["default_late_days"] == "14" and v["default_credit"] == "?"
    assert v["quarters"] == ["2026-10-15"]
    assert v["rules"][0] == {"kid": "", "course": "Band", "mode": "quarter_end", "late_days": "", "credit": "", "source": ""}
    assert v["rules"][1] == {"kid": "Alex", "course": "", "mode": "days", "late_days": "7", "credit": "50%", "source": "syllabus"}


def test_no_print_days_view_renders_entries_as_editable_strings():
    entries = [runner.SkipEntry(date(2026, 9, 7), None, "Labor Day"),
               runner.SkipEntry(date(2026, 12, 21), date(2027, 1, 1), "Holiday break")]
    v = actions.no_print_days_view(entries)
    assert v == [
        {"start": "2026-09-07", "end": "", "note": "Labor Day"},
        {"start": "2026-12-21", "end": "2027-01-01", "note": "Holiday break"},
    ]


def test_save_no_print_days_rejects_an_end_before_the_start(tmp_path):
    actions.no_print_days_settings(tmp_path)   # seed
    before = (tmp_path / "no-print-days.txt").read_text()
    errors = actions.save_no_print_days(tmp_path, [runner.SkipEntry(date(2026, 12, 25), date(2026, 12, 20), "")])
    assert errors
    assert (tmp_path / "no-print-days.txt").read_text() == before


def test_lan_url_uses_the_probe_and_tolerates_failure():
    assert actions.lan_url(8433, probe=lambda: "192.168.1.5") == "http://192.168.1.5:8433/"

    def boom():
        raise OSError("no network")
    assert actions.lan_url(8433, probe=boom) is None


def test_tailnet_url_reports_a_cgnat_address_and_nothing_else():
    """Tailscale assigns out of 100.64.0.0/10, and the probe is only believed when its answer
    lands there. With Tailscale down the UDP connect does not necessarily fail -- the OS can
    fall back to the default route and hand back the ordinary LAN address, which would
    otherwise be published to the parent as "your tailnet address"."""
    assert actions.tailnet_url(8433, probe=lambda: "100.107.58.120") == "http://100.107.58.120:8433/"
    assert actions.tailnet_url(8433, probe=lambda: "192.168.1.5") is None      # the fallback, refused
    assert actions.tailnet_url(8433, probe=lambda: "100.63.255.255") is None   # just below the range
    assert actions.tailnet_url(8433, probe=lambda: "100.128.0.0") is None      # just above it


def test_tailnet_url_tolerates_a_failed_probe_and_a_nonsense_answer():
    def boom():
        raise OSError("no network")
    assert actions.tailnet_url(8433, probe=boom) is None
    assert actions.tailnet_url(8433, probe=lambda: "") is None
    assert actions.tailnet_url(8433, probe=lambda: "not-an-address") is None


def test_print_now_passes_the_date(tmp_path):
    seen = {}

    def fake_run(key, opts, settings, echo=None):
        seen["opts"] = opts
        return 0
    actions.print_now(home=tmp_path, log=lambda s: None, settings=config.Settings(home=tmp_path), run=fake_run, date="2026-09-14")
    assert seen["opts"].date == "2026-09-14" and seen["opts"].reprint and seen["opts"].force


def test_about_text_names_version_repo_and_licences():
    from importlib import metadata
    t = actions.about_text()
    try:
        expected = metadata.version("fridgesheet")
    except metadata.PackageNotFoundError:
        expected = "dev"
    assert t.startswith(f"Fridge Sheet {expected}\n")
    assert "github.com/steiner385/fridgesheet" in t
    assert "SumatraPDF" in t and "Chromium" in t and "segno" in t
    assert "Tk" not in t and "Tcl" not in t          # the window is retired; nothing bundles Tk


def test_forward_logs_streams_app_records_only_while_active():
    lines = []
    parent, child = logging.getLogger("fridgesheet"), logging.getLogger("fridgesheet.session")
    saved = (parent.level, child.level)
    parent.setLevel(logging.NOTSET)
    child.setLevel(logging.NOTSET)          # like the real app: nobody has configured these
    try:
        with actions.forward_logs(lines.append):
            child.info("OneLogin login page detected; signing in")
            logging.getLogger("other").info("not ours")
        child.info("after")
        assert lines == ["OneLogin login page detected; signing in"]
        assert parent.level == logging.NOTSET      # restored
    finally:
        parent.setLevel(saved[0])
        child.setLevel(saved[1])


# -- self_update: downloads and executes a binary, so every branch is exercised with fakes --
# only `download_verified`/`spawn_installer` (host.selfupdate) and the release fetch are ever
# replaced; nothing here reaches the network or starts a process.

UPDATE_DIGEST = "sha256:" + "ab" * 32


class _FakeState:
    """The two things `self_update` needs from `AppState`: `.extra` (to inject the release
    fetch through the same `update_fetch` seam `web.updates.check` uses) and `.now()` (the
    Pending breadcrumb's timestamp). A real `AppState` via `app_for` would work too, but drags
    in the whole app to supply two attributes this module already fakes everything else with."""
    def __init__(self, fetch=None):
        self.extra: dict = {}
        if fetch is not None:
            self.extra["update_fetch"] = fetch

    def now(self):
        return datetime(2026, 9, 22, 12, 0, tzinfo=TZ)


def _release_body(tag: str, *, digest: str = "", size: int = 0, asset: bool = True) -> bytes:
    assets = [{"name": f"FridgeSheet-Setup-{tag.lstrip('v')}.exe",
               "browser_download_url": f"https://example.invalid/download/{tag}.exe",
               "digest": digest, "size": size}] if asset else []
    return json.dumps({"tag_name": tag, "html_url": f"https://example.invalid/releases/{tag}",
                       "assets": assets}).encode()


def test_self_update_does_nothing_when_already_current(tmp_path, monkeypatch):
    """Path 1: not newer. `download_verified` must never even be asked."""
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    monkeypatch.setattr(web_updates, "current_version", lambda: "0.5.0")
    calls = []
    monkeypatch.setattr(selfupdate, "download_verified", lambda *a, **kw: calls.append(("download", a, kw)))
    monkeypatch.setattr(selfupdate, "spawn_installer", lambda *a, **kw: calls.append(("spawn", a, kw)))
    lines = []
    state = _FakeState(fetch=lambda url: _release_body("v0.5.0", digest=UPDATE_DIGEST, size=1000))
    ok = actions.self_update(home=tmp_path, log=lines.append, settings=Settings(home=tmp_path), state=state)
    assert ok is False
    assert calls == []
    assert any("Already on 0.5.0" in ln for ln in lines)


def test_self_update_downloads_verifies_and_spawns_the_installer(tmp_path, monkeypatch):
    """Path 2: the happy path. `download_verified` gets the release's own url, digest AND
    size -- without size, `download_verified`'s free-space check has nothing to compare
    the free space against and is dead code. A Pending breadcrumb is written and the
    installer is spawned."""
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    monkeypatch.setattr(web_updates, "current_version", lambda: "0.5.0")
    dl_calls = []

    def fake_download(url, digest, dest, *, log, size=0, **kw):
        dl_calls.append({"url": url, "digest": digest, "dest": dest, "size": size})
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"pretend installer")
        return dest
    spawn_calls = []
    monkeypatch.setattr(selfupdate, "download_verified", fake_download)
    monkeypatch.setattr(selfupdate, "spawn_installer",
                        lambda installer, log_path, **kw: spawn_calls.append((installer, log_path)))
    lines = []
    fetch = lambda url: _release_body("v0.6.0", digest=UPDATE_DIGEST, size=286_000_000)   # noqa: E731
    state = _FakeState(fetch=fetch)
    ok = actions.self_update(home=tmp_path, log=lines.append, settings=Settings(home=tmp_path), state=state)
    assert ok is True
    assert len(dl_calls) == 1
    call = dl_calls[0]
    assert call["digest"] == UPDATE_DIGEST
    assert call["size"] == 286_000_000                       # the point of this test
    assert call["url"] == "https://example.invalid/download/v0.6.0.exe"
    assert len(spawn_calls) == 1
    pending = selfupdate.read_pending(tmp_path)
    assert pending is not None and pending.from_version == "0.5.0" and pending.to_version == "0.6.0"


def test_self_update_refuses_and_never_spawns_when_the_digest_is_wrong(tmp_path, monkeypatch):
    """Path 3: the one that matters most. A failed verification must not be able to execute
    anything -- `spawn_installer` is asserted never called."""
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    monkeypatch.setattr(web_updates, "current_version", lambda: "0.5.0")

    def fake_download(*a, **kw):
        raise selfupdate.UpdateError(
            "The downloaded installer does not match the checksum GitHub published for it. "
            "Nothing was installed.")
    spawn_calls = []
    monkeypatch.setattr(selfupdate, "download_verified", fake_download)
    monkeypatch.setattr(selfupdate, "spawn_installer", lambda *a, **kw: spawn_calls.append((a, kw)))
    lines = []
    fetch = lambda url: _release_body("v0.6.0", digest=UPDATE_DIGEST, size=1000)   # noqa: E731
    state = _FakeState(fetch=fetch)
    ok = actions.self_update(home=tmp_path, log=lines.append, settings=Settings(home=tmp_path), state=state)
    assert ok is False
    assert spawn_calls == []
    assert any("does not match the checksum" in ln for ln in lines)
    assert selfupdate.read_pending(tmp_path) is None          # nothing was ever handed off to


def test_self_update_refuses_when_the_release_has_no_installer(tmp_path, monkeypatch):
    """Path 4: a release with no .exe asset -- an empty digest. The real `download_verified`
    refuses this before any network call (its very first check), so it is left unmocked here;
    only `spawn_installer` is watched, to prove it is never reached."""
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    monkeypatch.setattr(web_updates, "current_version", lambda: "0.5.0")
    spawn_calls = []
    monkeypatch.setattr(selfupdate, "spawn_installer", lambda *a, **kw: spawn_calls.append((a, kw)))
    lines = []
    fetch = lambda url: _release_body("v0.6.0", digest="", size=0, asset=False)   # noqa: E731
    state = _FakeState(fetch=fetch)
    ok = actions.self_update(home=tmp_path, log=lines.append, settings=Settings(home=tmp_path), state=state)
    assert ok is False
    assert spawn_calls == []
    assert any("no installer" in ln for ln in lines)


def test_self_update_refuses_early_on_a_non_windows_host(tmp_path, monkeypatch):
    """Fix round: a Linux install must never download the 286 MB asset, write the
    breadcrumb, or announce that the installer is starting -- and today nothing checked the
    platform until `selfupdate.spawn_installer`'s dispatcher raised, which is the LAST step.
    This is the guard at the TOP of the function: neither the release fetch nor
    `download_verified` may even be reached."""
    monkeypatch.setattr(host, "IS_WINDOWS", False)
    fetch_calls = []
    monkeypatch.setattr(selfupdate, "download_verified", lambda *a, **kw: fetch_calls.append("download"))
    lines = []
    state = _FakeState(fetch=lambda url: fetch_calls.append("fetch") or _release_body(
        "v99.0.0", digest=UPDATE_DIGEST, size=286_000_000))
    ok = actions.self_update(home=tmp_path, log=lines.append, settings=Settings(home=tmp_path), state=state)
    assert ok is False
    assert fetch_calls == []                                   # neither the release check nor the download ran
    assert selfupdate.read_pending(tmp_path) is None            # no breadcrumb left for `resolve_pending` to pin
    assert any("Windows" in ln for ln in lines)


def test_self_update_gives_a_friendly_line_when_github_is_unreachable(tmp_path, monkeypatch):
    """No internet is the single most likely failure for the households this feature is for.
    `updatemod.latest_release` can raise `URLError` straight through -- it is not wrapped in
    `UpdateError` -- and left uncaught that reaches the job worker's generic handler as a raw
    `URLError: <urlopen error ...>` string, the opposite of the "one sentence a parent can
    act on" contract."""
    from urllib.error import URLError
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    monkeypatch.setattr(web_updates, "current_version", lambda: "0.5.0")

    def fetch(url):
        raise URLError("[Errno -2] Name or service not known")
    lines = []
    state = _FakeState(fetch=fetch)
    ok = actions.self_update(home=tmp_path, log=lines.append, settings=Settings(home=tmp_path), state=state)
    assert ok is False
    assert any("reach GitHub" in ln for ln in lines)
    assert not any("Errno" in ln for ln in lines)                # no raw traceback text reaches the parent


def test_self_update_gives_a_friendly_line_on_malformed_release_json(tmp_path, monkeypatch):
    """A `json.JSONDecodeError` from `latest_release` is just as uncaught as a `URLError` --
    same contract, same fix."""
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    monkeypatch.setattr(web_updates, "current_version", lambda: "0.5.0")
    lines = []
    state = _FakeState(fetch=lambda url: b"not json")
    ok = actions.self_update(home=tmp_path, log=lines.append, settings=Settings(home=tmp_path), state=state)
    assert ok is False
    assert any("reach GitHub" in ln for ln in lines)


def test_env_overrides_names_the_variable_that_wins_over_each_field(monkeypatch):
    """#148: one sentence per Settings field the environment overrides, keyed by form field."""
    assert actions.env_overrides() == {}
    monkeypatch.setenv("FRIDGESHEET_PRINTER", "")          # blank still overrides: it means "system default"
    monkeypatch.setenv("FRIDGESHEET_SHEETS_ARCHIVE", "/mnt/drive")
    monkeypatch.setenv("FRIDGESHEET_WEB_PORT", "9000")
    monkeypatch.setenv("FRIDGESHEET_NICKNAMES", "")        # parses to nothing, changes nothing: no note
    notes = actions.env_overrides()
    assert set(notes) == {"printer", "archive", "port"}
    assert notes["printer"].startswith("Set by FRIDGESHEET_PRINTER= in the environment")
    assert "/mnt/drive" in notes["archive"] and "9000" in notes["port"]
    monkeypatch.setenv("FRIDGESHEET_WEB_PORT", "x")        # load_settings ignores it, so no note
    assert "port" not in actions.env_overrides()
    monkeypatch.setenv("FRIDGESHEET_NICKNAMES", "Alex=Lex")
    monkeypatch.setenv("FRIDGESHEET_WEB_HOST", "127.0.0.1")
    notes = actions.env_overrides()
    assert "wins" in notes["nicknames"] and "FRIDGESHEET_WEB_HOST=127.0.0.1" in notes["allow_lan"]
