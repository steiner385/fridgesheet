"""Command line: `fridgesheet login|set-credentials|check|refresh|status|serve|run|reports|printers|schedule|print-sheet|web|service|doctor`."""
from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import sys
import time

from . import collector
from .config import (ConfigError, ReportConfig, Settings, config_file, load_config_doc, load_settings,
                     save_config_doc, settings_from_doc)
from .host import credentials as credstore
from .host import current_user as _current_user
from .session import browser, ensure_canvas, ensure_hac


def _canvas_authed(ctx, s: Settings) -> bool:
    """Read-only session probe that shares the context's cookie jar but leaves the
    visible page alone, so polling cannot interfere with a sign-in in progress."""
    try:
        r = ctx.request.get(s.canvas_base + "/api/v1/users/self", headers={"Accept": "application/json"})
        return r.status == 200
    except Exception:
        return False


def _hac_authed(ctx, s: Settings) -> bool:
    try:
        r = ctx.request.get(s.hac_base + "/Home/WeekView")
        return r.status == 200 and s.onelogin_host not in r.url and "/Account/LogOn" not in r.url
    except Exception:
        return False


def cmd_login(args) -> int:
    """Headed one-time login. Lets you sign in by hand; the persistent profile keeps the cookies."""
    s = load_settings()
    with browser(s, headless=False) as ctx:
        page = ctx.new_page()
        page.goto(s.canvas_base + "/")
        print("A browser window is open. Sign in to Canvas (via OneLogin) if prompted.", flush=True)
        if sys.stdin.isatty():
            input("Press Enter here when Canvas shows your dashboard... ")
            page.goto(s.hac_base + "/Home/WeekView")
            input("Now make sure Home Access Center shows the Week View, then press Enter... ")
        else:
            # No terminal attached (launched by a tool or a script): input() would raise
            # EOFError instantly and close the window before anyone could sign in. Watch the
            # session state instead and finish as soon as both sites are authenticated.
            wait_min = getattr(args, "wait_minutes", 15)
            print(f"No terminal attached; watching the session for up to {wait_min} min.", flush=True)
            deadline, last, opened_hac = time.time() + wait_min * 60, None, False
            while time.time() < deadline:
                state = (_canvas_authed(ctx, s), _hac_authed(ctx, s))
                if state != last:
                    print(f"  Canvas: {'OK' if state[0] else 'waiting'}    HAC: {'OK' if state[1] else 'waiting'}", flush=True)
                    last = state
                if all(state):
                    print("Both sites authenticated; the profile now holds the cookies.", flush=True)
                    break
                if state[0] and not state[1] and not opened_hac:
                    page.goto(s.hac_base + "/Home/WeekView")  # hand them straight to HAC
                    opened_hac = True
                time.sleep(5)
            else:
                print(f"Timed out after {wait_min} min waiting for sign-in.", flush=True)
                return 1
    print("Saved. Verifying headless access...")
    return cmd_check(args)


def cmd_set_credentials(args) -> int:
    """Store the OneLogin username/password in the OS credential store (GNOME keyring on
    Linux, Credential Manager on Windows) and remember the username in config.toml."""
    load_settings()
    if not sys.stdin.isatty():
        print("set-credentials needs a terminal so the password is never echoed or logged.", file=sys.stderr)
        print("Run it yourself in a shell, or (Linux) pipe a value from your password manager", file=sys.stderr)
        print("into secret-tool, e.g.:", file=sys.stderr)
        print("  op read --no-newline 'op://Vault/<uuid>/password' | \\", file=sys.stderr)
        print(f"    secret-tool store --label 'Fridge Sheet OneLogin' service {credstore.SERVICE} key password", file=sys.stderr)
        return 2
    user = args.username or input("OneLogin username: ").strip()
    if not user:
        print("No username given.", file=sys.stderr)
        return 2
    pw = getpass.getpass("OneLogin password (not echoed): ")
    if not pw:
        print("No password given.", file=sys.stderr)
        return 2
    credstore.write(user, pw)
    del pw
    doc = load_config_doc(config_file())
    doc.setdefault("account", {})["username"] = user
    save_config_doc(config_file(), doc)
    print(f"Stored under service={credstore.SERVICE!r}; username recorded in {config_file()}.")
    print("Verify with:  fridgesheet check")
    return 0


def cmd_check(args) -> int:
    s = load_settings()
    ok = True
    with browser(s) as ctx:
        for name, fn in (("Canvas", ensure_canvas), ("HAC", ensure_hac)):
            try:
                fn(ctx, s)
                print(f"  {name}: OK")
            except Exception as e:
                ok = False
                print(f"  {name}: FAILED - {e}")
    return 0 if ok else 1


def cmd_refresh(args) -> int:
    s = load_settings()
    if args.record:
        # `--record` is what a schedule runs (the data-refresh task), and a scheduled refresh
        # has no use for a partial pull -- it exists to keep the snapshot every report and the
        # kiosk trust warm, and a household that meant to run one of these by hand still has
        # bare `refresh --no-hac`/`--no-canvas`/`--kids` for that. Rejected outright rather than
        # silently accepted: `web.actions.refresh` takes no such filters (it always calls
        # `collector.collect` with its own defaults), so passing them through here would mean
        # plumbing new parameters all the way into the one path a schedule and the Refresh now
        # button share -- for a combination nothing schedules.
        if args.no_hac or args.no_canvas or args.kids is not None:
            print("refresh --record always does a full refresh; --no-hac, --no-canvas and --kids "
                  "are not supported with it (a scheduled refresh has no use for a partial pull). "
                  "Drop --record to use those flags.", file=sys.stderr)
            return 2
        # The full path the Refresh now button takes: collect, ingest into the database the
        # web app renders from, and record the run. Bare `refresh` below writes only the
        # snapshot, which every MCP tool reads -- the database came later, with the web app.
        from .web import actions
        result = actions.refresh(home=s.home, log=lambda m: print(m), trigger="schedule")
        print(result.message)
        return 0 if result.ok else 1
    snap = collector.collect(s, include_hac=not args.no_hac, include_canvas=not args.no_canvas, kids_filter=args.kids)
    print(json.dumps(collector.summary(s, snap), indent=2))
    return 0 if all(v == "ok" for v in snap["sources"].values() if v) else 1


def cmd_status(args) -> int:
    s = load_settings()
    print(json.dumps(collector.summary(s, collector.load_snapshot(s)), indent=2))
    return 0


def cmd_serve(args) -> int:
    from .server import run
    run()
    return 0


def cmd_printers(args) -> int:
    from .host import printing
    default = printing.default_printer()
    for name in printing.list_printers():
        print(f"{'*' if name == default else ' '} {name}")
    return 0


def cmd_print_sheet(args) -> int:
    from . import print_sheet
    opts = print_sheet.Options(dry_run=args.dry_run, kid=args.kid, date=args.date, days=args.days, overdue_days=args.overdue_days,
                               force=args.force, printer=args.printer, no_refresh=args.no_refresh, reprint=args.reprint)
    return print_sheet.run(opts, load_settings())


def cmd_run(args) -> int:
    from . import runner
    opts = runner.RunOptions(dry_run=args.dry_run, force=args.force, reprint=args.reprint, date=args.date, kid=args.kid,
                             no_refresh=args.no_refresh, printer=args.printer,
                             options={"days_ahead": args.days, "overdue_days": args.overdue_days}, trigger=args.trigger)
    return runner.run(args.report, opts, load_settings())


def cmd_reports(args) -> int:
    from . import reports
    s = load_settings()
    for r in reports.available(s.home):
        rc = s.report_config(r.key, r.default_time)
        state = "enabled" if rc.enabled else "disabled"
        print(f"{r.key:<12} {r.title:<20} {state:<9} {rc.time} {','.join(rc.days)}"
              + ("" if rc.prints else "  (PDF only)"))
    return 0


def _removal_settings() -> tuple[Settings, str]:
    """The settings `schedule remove --all` runs on: the home and `config.toml`'s
    `[reports.<key>]` table names, read with nothing that writes to disk and nothing that can
    abort the run. Returns them with the reason they are degraded, or "" when nothing is.

    `load_settings` is the wrong loader for this one path, twice over -- both times because
    this caller is an uninstaller and not an ordinary command:

    - It ends with `for d in (s.home, s.profile_dir, s.cache_dir): d.mkdir(...)`. That defeats
      `_schedule_removal_keys`'s whole reason for gating the database read on
      `db_path.is_file()`: a parent who deleted `%LOCALAPPDATA%\\fridgesheet` before
      uninstalling gets the folder back, with `browser-profile` and `cache` inside it, and
      `installer.iss`'s post-uninstall message box then points at it and calls what is in it
      "kept".
    - It raises `ConfigError` for a `config.toml` tomllib cannot parse, or for a single
      `[reports.<key>].time` that is not HH:MM. `main()` has no handler, so the command would
      die with a traceback before removing anything -- and `[UninstallRun]` is `runhidden` and
      discards the exit code, so every scheduled task would survive the uninstall with nothing
      on screen saying so. `_schedule_removal_keys` degrades gracefully for a *database* it
      cannot read; the config file, which that same docstring calls the source that works
      "database or no database", cannot be the fatal one.

    A bad `time` costs only its own table's *settings*, never any table's removal: the raw
    document parsed, so every `[reports.<key>]` name in it is still taken off it directly. The
    key is all `scheduling.remove` needs -- it computes a unit or task name and nothing else.
    """
    s = Settings()
    try:
        doc = load_config_doc(config_file())
    except ConfigError as e:
        return s, str(e)                      # already names the file
    except (OSError, UnicodeDecodeError) as e:
        # Out of the `read_text` underneath `load_config_doc`: a permission the uninstaller
        # does not have, or a file some other tool wrote in an encoding it will not decode.
        # Same meaning as a parse failure here -- the config is unreadable, so remove what the
        # code reports alone can name, and say why.
        return s, f"{config_file()}: {e}"
    try:
        settings_from_doc(doc, s)
    except Exception as e:
        # Deliberately every exception, not a list of the types seen so far. `settings_from_doc`
        # reads a hand-editable file: `config.py` now type-guards the shapes that bit us here
        # (a `reports` key that is not a table -> `AttributeError`; a `days` that is not a list
        # -> `TypeError`), which is the real fix and helps every caller -- but this is the one
        # call site where an escaping exception costs the parent *every* scheduled task, with a
        # traceback `runhidden` swallows and an exit code `[UninstallRun]` never checks. So the
        # next unguarded conversion in that reader must not be able to reach here either.
        raw = doc.get("reports")
        for key in (raw if isinstance(raw, dict) else {}):
            s.reports.setdefault(str(key), ReportConfig())
        return s, f"{config_file()}: {e}"
    return s, ""


def _schedule_removal_keys(s) -> tuple[set[str], bool]:
    """Every key `schedule remove --all` must try, and whether that list is complete.

    Almost every key here is a report key, and most of this docstring is about finding those --
    but the set returned is not "every report key", it is every key this app might have
    installed a schedule under, and one of those (`host.DATA_REFRESH_KEY`) is not a report at
    all. See the note below the report-key filter for that one.

    Two sources, unioned, neither one alone enough:

    - The code reports (`reports.REPORTS`) plus `config.toml`'s `[reports.<key>]` tables
      (`s.reports`) -- the Schedules page's own record of every key it ever wrote a schedule
      for, read straight off disk with no database involved. A `view:<id>` key survives here
      even if the database that would resolve it to a title is gone, unreadable, or on a
      schema this build cannot read -- exactly the case that matters, since `scheduling.remove`
      only needs the key to compute the unit/task name, never the report itself.
    - The database's own saved-report listing, `[reports."view:<id>"]`'s other half -- but
      *only* read when `db.db_path(s.home)` already exists. `reports.available(home)` calls
      `db.open_db`, which creates the folder and an empty database as a side effect if neither
      is there yet; calling it unconditionally here would hand a parent who deleted
      `%LOCALAPPDATA%\\fridgesheet` before uninstalling a freshly recreated one back, while
      the installer's own "your data was kept" message box points right at it.

    A database that exists but cannot be read (`db.migrate` raising for a schema this downgraded
    build does not understand is the concrete case: install a build that migrates `fridgesheet.db` to
    a newer schema, roll back to an older installer, uninstall) does not silently return an empty
    saved-report list the way `reports.available` does -- that swallow is right for a page render,
    where a listing is never worth a 500, but wrong for an uninstaller deciding whether it is
    done. Here it is caught directly and reported as incomplete, so the caller's exit code says
    so -- even though the `s.reports` half above already means the actual removal attempt still
    happens for every key that config.toml remembers, database or no database.

    Whatever the two sources produce is then filtered to keys this app actually schedules
    under (`reports.is_schedulable_key`). `s.reports` is `[reports.<key>]` table names read
    raw off disk, and a hand-edited one need not be a report at all: `[reports.Web]` renders to
    "Fridge Sheet - Web", which in Task Scheduler's case-insensitive namespace *is* the web
    server's own logon task. The single-key path gates on `reports.resolve` for exactly that
    reason (`cmd_schedule`); `--all` cannot call `resolve` -- it opens, and so creates, the
    database this function just went to such trouble not to create -- so it gates on the
    spelling instead, which is the same set of keys `resolve` accepts. A skipped key is
    announced on stderr rather than dropped silently, but it does not make the run incomplete:
    it was never this app's schedule to remove.

    One key is added after that filter, not before it: `host.DATA_REFRESH_KEY`. It is not a
    report -- it lives under `[refresh]`, not `[reports.<key>]` -- so `reports.is_schedulable_key`
    correctly says no to it, and it can never appear in `keys` above no matter how thoroughly
    `config.toml` and the database are read. Yet it is exactly the kind of task this function
    exists to find: a household that ever turned the refresh schedule on has a real Task
    Scheduler task or systemd timer firing `refresh --record` on a timer, whether or not
    `[refresh]` is still in config.toml (deleted by hand, or never written because the schedule
    was installed from an older build) and whether or not `[refresh].enabled` is currently
    true. Added unconditionally -- not "if `[refresh]` is present" or "if enabled" -- because
    `scheduling.remove` is documented idempotent for a task or unit that is not there, so the
    cost of trying it when nothing was ever installed is nothing, while the cost of *not*
    trying it when something was is a data-refresh task surviving the uninstall with no config
    left to explain what it is.
    """
    from . import host, reports
    from .web import db as web_db

    keys = {r.key for r in reports.REPORTS.values()} | set(s.reports)
    complete = True
    db_path = web_db.db_path(s.home)
    if db_path.is_file():
        try:
            from .web.stores import reports as report_store
            conn = web_db.open_db(s.home)
            try:
                keys |= {f"view:{row['id']}" for row in report_store.all(conn)}
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001  an uninstaller must not mistake this for "nothing saved"
            print(f"could not list saved reports (their schedules may be left running): {e}", file=sys.stderr)
            complete = False
    ours = {k for k in keys if reports.is_schedulable_key(k)}
    for k in sorted(keys - ours):
        print(f"{k}: not a report key this app schedules under; leaving anything of that name alone",
              file=sys.stderr)
    ours.add(host.DATA_REFRESH_KEY)
    return ours, complete


def _cmd_schedule_remove_all() -> int:
    """The uninstaller's own call: remove the schedule for every report this app knows about,
    not just the default one `schedule remove` names when no report is given.

    `installer.iss`'s `[UninstallRun]` cannot enumerate a parent's saved reports itself --
    Inno Setup script is not a scripting language -- so this is where the enumeration actually
    happens (`_schedule_removal_keys`), on settings loaded without `load_settings`'s two
    side effects (`_removal_settings`). Every key found goes through the ordinary
    `scheduling.remove`, so the platform's own ownership check -- the one that refuses a
    hand-written unit or the web server's logon task -- runs exactly as it does for a single
    report. What `--all` does *not* get from `remove` is `cmd_schedule`'s `reports.resolve`
    gate, because resolving a `view:<id>` opens the database; `_schedule_removal_keys` applies
    the equivalent gate by spelling instead. A report that was never scheduled costs nothing
    here either -- `remove` is documented idempotent for a task or unit that is not there.

    One report's `SchedulingError` (a hand-written namesake unit, say) does not stop the rest
    from being tried -- an uninstall that gives up after the first refusal would leave every
    other report behind too. `NotSupported` is different: it would mean this host has no
    scheduler at all, so trying the next report could not do any better and the loop stops
    there, the same as a single `schedule remove` would. No shipped `host` module raises it for
    scheduling (both platforms have a real implementation), so that branch is insurance for a
    third platform rather than a path anything takes today.

    Exit code: 0 only when every key was removed *and* nothing had to be guessed at. A
    config.toml or a database that could not be read makes it 1, because the honest answer is
    "something may still be scheduled" -- even though `runhidden` means nobody reads it.
    """
    from .host import NotSupported, scheduling
    s, degraded = _removal_settings()
    if degraded:
        print(f"could not read the settings (schedules it knows about may be left running): {degraded}",
              file=sys.stderr)
    keys, complete = _schedule_removal_keys(s)
    ok = True
    for key in sorted(keys):
        try:
            scheduling.remove(key)
            print(f"Removed {scheduling.display_name(key)}")
        except NotSupported as e:
            print(str(e), file=sys.stderr)
            return 2
        except scheduling.SchedulingError as e:
            print(f"{key}: {e}", file=sys.stderr)
            ok = False
    return 0 if (ok and complete and not degraded) else 1


def cmd_schedule(args) -> int:
    from . import reports
    from .host import NotSupported, scheduling
    if args.all:
        # Dispatched before `load_settings`, not after: `--all` is the uninstaller's call and
        # must neither create the home folder nor die on a config file it cannot read. See
        # `_removal_settings` for both halves of why.
        if args.action != "remove":
            print("--all only works with `schedule remove`", file=sys.stderr)
            return 2
        return _cmd_schedule_remove_all()
    from . import host, refresh_schedule
    from .web import schedules as page
    s = load_settings()
    key = args.report
    try:
        if args.action == "install":
            if key == host.DATA_REFRESH_KEY:
                # `[refresh]`, installed by the very call the Schedules page makes (#146) --
                # this used to fall through to `reports.resolve` and answer "unknown report".
                rc = s.refresh
                times = refresh_schedule.refresh_times(rc.start, rc.end, rc.every_hours)
                host.check_schedule_times(times, rc.days)
                page.install_refresh(times, rc.days, home=s.home, timezone=s.timezone, scheduling=scheduling)
                print(f"Installed {scheduling.display_name(key)}: {','.join(rc.days)} at {','.join(times)}")
            else:
                r = reports.resolve(key, s.home)       # a saved view report is schedulable too (#35)
                rc = s.report_config(key, r.default_time)
                exe, a, wd = scheduling.command_for(key)
                scheduling.install(key, [rc.time], rc.days, exe, a, wd, title=r.title,
                                   home=str(s.home), timezone=s.timezone)
                print(f"Installed {scheduling.display_name(key)}: {','.join(rc.days)} at {rc.time}")
            # Only once the host has it: config.toml says on exactly when a task is there, the
            # way the Schedules page leaves it (#146).
            page.record_enabled(s.home, key, True)
        elif args.action == "remove":
            # `data-refresh` is the one escape hatch through the report-key gate below: it is
            # not a report (`reports.resolve` would raise `ReportError` for it, same as any
            # other non-report string), but it is a fixed, reserved key (`host.RESERVED_KEYS`)
            # a report can never be saved under -- so admitting it here by name does not loosen
            # what the gate protects against (`remove web` still resolves and still refuses).
            # Without it, a parent whose refresh schedule outlived its `[refresh]` config had
            # no single-key way to remove just that task; `schedule remove --all` was the only
            # door, and it removes every report's schedule too.
            if key != host.DATA_REFRESH_KEY:
                reports.resolve(key, s.home)      # the same gate `install` has: `remove web` is
            scheduling.remove(key)                # not a report, and on Windows it names the
                                                  # web server's own logon task
            # Off in config.toml too, or `doctor` fails "on in config.toml but no task is
            # installed" (#146). A table that was never written already reads as off.
            page.record_enabled(s.home, key, False, create=False)
            print(f"Removed {scheduling.display_name(key)}")
        info = scheduling.describe(key)
        state = f"next run {info.next_run}" if info.installed else "not scheduled"
        print(f"{key}: {state} (managed by {info.managed_by}" + (f", last result {info.last_result}" if info.last_result else "") + ")")
        return 0
    except NotSupported as e:
        print(str(e), file=sys.stderr)
        return 2
    except (reports.ReportError, scheduling.SchedulingError) as e:
        print(str(e), file=sys.stderr)
        return 1


def cmd_web(args) -> int:
    from .web import server
    return server.run(load_settings(), host=args.host, port=args.port, open_browser=not args.no_browser)


def cmd_service(args) -> int:
    from .host import ServiceError, service
    try:
        if args.action == "install":
            print(f"Installed {service.SERVICE_NAME}: {service.install_service()}")
        elif args.action == "remove":
            service.remove_service()
            print(f"Removed {service.SERVICE_NAME}")
        info = service.describe_service()
        print(f"{service.SERVICE_NAME}: {info.detail} (managed by {info.managed_by})")
        return 0
    except (ServiceError, OSError) as e:        # schtasks/systemctl missing is a message too (#4)
        print(str(e), file=sys.stderr)
        return 1


def _service_info():
    from .host import service
    return service.describe_service()


def _do_self_update(*, home, settings) -> int:
    from .web import actions
    lines: list[str] = []

    def log(line: str) -> None:
        lines.append(line)
        print(line)

    class _State:                       # actions.self_update wants `.extra` and `.now()`
        extra: dict = {}

        @staticmethod
        def now():
            from datetime import datetime
            return datetime.now().astimezone()

    return 0 if actions.self_update(home=home, log=log, settings=settings, state=_State()) else 1


def cmd_self_update(args) -> int:
    """Update this install to the newest release.

    No PIN here, deliberately: a shell on this machine already owns this machine, so asking
    for one would be theatre -- that check belongs to the web Settings page, which is reachable
    by anyone on the house LAN, not to an operator who is already sitting at a prompt here. Do
    not "fix" this by adding one back.

    What this DOES check is ownership. A per-user logon task only fires for its owner, and a
    per-user install lives in that owner's profile, so running this as anyone else builds a
    second copy under a different profile and leaves the running server untouched -- silently,
    reporting success. Seen on the household's Windows box, 2026-09-22: the logon task runs as
    one account while an SSH session arrives as another.
    """
    from . import host
    from .host import selfupdate_linux
    from .web import updates as updatemod
    if not host.IS_WINDOWS:
        # Refused before anything else -- including `--check`, which the README already
        # advertises as part of this Windows-only command -- rather than leaving the
        # platform check to be discovered last, wherever the flow happens to fail first.
        print(selfupdate_linux.NOT_WINDOWS, file=sys.stderr)
        return 1
    s = load_settings()
    if args.check:
        current = updatemod.current_version()
        latest, _url, _digest, _size = updatemod.latest_release()
        print(f"{current} installed; {latest} is the newest release."
              if updatemod.newer(latest, current) else f"{current} is the newest release.")
        return 0
    info, me = _service_info(), _current_user()
    # `not me` (not `me and ...`) is deliberate: getpass.getuser() can fail (no password-
    # database entry, some container/service contexts), and when the owner IS known but we
    # cannot confirm who we are, that is a reason to stop, not to proceed -- proceeding would
    # be exactly the silent second-install this check exists to prevent.
    if not args.force and info.owner and (not me or info.owner.casefold() != me.casefold()):
        who = f"you are {me!r}" if me else "this shell's account could not be determined"
        print(f"The logon task runs as {info.owner!r} and its install lives in that account's "
              f"profile; {who}. Updating from here would build a second copy under the wrong "
              f"profile and leave the running one alone. Run this as {info.owner!r}, or pass "
              f"--force if you mean to install a separate copy.", file=sys.stderr)
        return 1
    return _do_self_update(home=s.home, settings=s)


def cmd_doctor(args) -> int:
    from . import doctor
    s = load_settings()
    report, ok = doctor.run(s, s.home)
    print(report)
    return 0 if ok else 1


def main(argv=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    p = argparse.ArgumentParser(prog="fridgesheet")
    sub = p.add_subparsers(dest="cmd", required=True)
    lg = sub.add_parser("login", help="one-time headed login to seed the browser profile")
    lg.add_argument("--wait-minutes", type=int, default=15, help="how long to watch for sign-in when no terminal is attached")
    lg.set_defaults(fn=cmd_login)
    sc = sub.add_parser("set-credentials", help="store OneLogin credentials in the OS credential store")
    sc.add_argument("--username", help="prompted for if omitted; the password is always prompted")
    sc.set_defaults(fn=cmd_set_credentials)
    sub.add_parser("check", help="verify headless Canvas + HAC access").set_defaults(fn=cmd_check)
    r = sub.add_parser("refresh", help="pull everything now into the cache")
    r.add_argument("--no-hac", action="store_true")
    r.add_argument("--no-canvas", action="store_true")
    r.add_argument("--kids", nargs="*", help="first names to include (default all)")
    r.add_argument("--record", action="store_true",
                   help="also ingest into the app's database and record the run (what a schedule runs)")
    r.set_defaults(fn=cmd_refresh)
    sub.add_parser("status", help="show cache age and last source status").set_defaults(fn=cmd_status)
    sub.add_parser("printers", help="list printers; * marks the system default").set_defaults(fn=cmd_printers)
    sub.add_parser("serve", help="run the MCP server on stdio").set_defaults(fn=cmd_serve)
    rn = sub.add_parser("run", help="refresh, build one report, print it, record it")
    rn.add_argument("report", help="report key; see `fridgesheet reports`")
    rn.add_argument("--dry-run", action="store_true", help="build the PDF but do not print, record or notify")
    rn.add_argument("--kid", help="one student only (first name or nickname prefix)")
    rn.add_argument("--date", help="YYYY-MM-DD to build for (testing); bypasses the print window")
    rn.add_argument("--days", type=int, default=None, help="days ahead (default: config.toml, then 14)")
    rn.add_argument("--overdue-days", type=int, default=None, help="how far back an overdue item may be (default: config.toml, then 14)")
    rn.add_argument("--force", action="store_true", help="ignore no-print-days.txt and the print window (never reprints a day)")
    rn.add_argument("--printer", default=os.environ.get("FRIDGESHEET_PRINTER") or None, help="printer name (default: FRIDGESHEET_PRINTER if set in the shell environment, then the report's own printer, then [print] printer in config.toml or FRIDGESHEET_PRINTER in .env, then the system default)")
    rn.add_argument("--no-refresh", action="store_true", help="use the snapshot as is")
    rn.add_argument("--reprint", action="store_true", help="print again even if this date already has a printed sheet")
    rn.add_argument("--trigger", choices=["cli", "schedule"], default="cli", help=argparse.SUPPRESS)   # set by installed schedules
    rn.set_defaults(fn=cmd_run)
    sub.add_parser("reports", help="list report types and their schedules").set_defaults(fn=cmd_reports)
    sc2 = sub.add_parser("schedule", help="install, remove or show a report's scheduled run "
                                          "(systemd user timers on Linux, Task Scheduler on Windows)")
    sc2.add_argument("action", choices=["install", "remove", "show"])
    sc2.add_argument("report", nargs="?", default="open-work", help="ignored with --all")
    sc2.add_argument("--all", action="store_true",
                     help="with `remove`: every report's schedule, not just `report` -- what the uninstaller runs, "
                          "and the only way to remove a schedule left behind by a saved report that "
                          "no longer exists (`remove view:N` refuses a key that does not resolve)")
    sc2.set_defaults(fn=cmd_schedule)
    w = sub.add_parser("web", help="run the browser app (foreground); opens the browser unless --no-browser")
    w.add_argument("--host", default=None, help="bind address (default: config.toml [web], 127.0.0.1)")
    w.add_argument("--port", type=int, default=None, help="port (default: config.toml [web], 8433)")
    w.add_argument("--no-browser", action="store_true")
    w.set_defaults(fn=cmd_web)
    sv = sub.add_parser("service", help="install, remove or show the always-on web server (systemd user unit / Windows logon task)")
    sv.add_argument("action", choices=["install", "remove", "show"])
    sv.set_defaults(fn=cmd_service)
    su = sub.add_parser("self-update", help="install the newest release over this one (Windows)")
    su.add_argument("--check", action="store_true", help="say what is available; install nothing")
    su.add_argument("--force", action="store_true", help="proceed even if another account owns the install")
    su.set_defaults(fn=cmd_self_update)
    sub.add_parser("doctor", help="check Python, Chromium, the PDF engine, the credential store, printers and the scheduler; writes <home>/doctor.txt").set_defaults(fn=cmd_doctor)
    ps = sub.add_parser("print-sheet", help="refresh, build the kids' open-work sheet, and print it (CUPS)")
    ps.add_argument("--dry-run", action="store_true", help="build the PDF under ~/.fridgesheet/sheets/ but do not print or record")
    ps.add_argument("--kid", help="one student only (first name or nickname prefix)")
    ps.add_argument("--date", help="YYYY-MM-DD to build for (testing); bypasses the 2 PM window")
    ps.add_argument("--days", type=int, default=14, help="how far ahead to look (default 14)")
    ps.add_argument("--overdue-days", type=int, default=14, help="how far back an overdue item may be (default 14)")
    ps.add_argument("--force", action="store_true", help="ignore no-print-days.txt and the 2 PM window (never reprints a day)")
    ps.add_argument("--printer", default=os.environ.get("FRIDGESHEET_PRINTER") or None, help="printer name (default: FRIDGESHEET_PRINTER if set in the shell environment, then the report's own printer, then [print] printer in config.toml or FRIDGESHEET_PRINTER in .env, then the system default)")
    ps.add_argument("--no-refresh", action="store_true", help="use the snapshot as is")
    ps.add_argument("--reprint", action="store_true", help="print again even if this date already has a printed sheet")
    ps.set_defaults(fn=cmd_print_sheet)
    args = p.parse_args(argv)
    try:
        code = args.fn(args)
    except ConfigError as e:
        # A config.toml that does not read is the parent's to fix, and the message already
        # names the file and the setting: one line, not a traceback (#144).
        print(f"fridgesheet: {e}", file=sys.stderr)
        code = 2
    sys.exit(code)


def legacy_main(argv=None) -> None:
    """`lakota-grades`, the command's name before the rename: one line of notice on stderr,
    then exactly `main`. Kept for one release so a unit or shortcut written before the
    rename keeps working; `doctor` lists it under "old names"."""
    print("lakota-grades is now fridgesheet; this alias goes away in a later release.", file=sys.stderr)
    os.environ["FRIDGESHEET_LEGACY_COMMAND"] = "1"
    main(argv)


if __name__ == "__main__":
    main()
