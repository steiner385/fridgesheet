"""Command line: `lakota-grades login|check|refresh|status|serve|print-sheet`."""
from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import sys
import time

from . import collector
from .config import KEYRING_SERVICE, Settings, keyring_write, load_settings
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
    """Store the OneLogin username/password in the GNOME keyring (encrypted at rest,
    unlocked by PAM at login, readable by the unattended refresh timer)."""
    load_settings()
    if not sys.stdin.isatty():
        print("set-credentials needs a terminal so the password is never echoed or logged.", file=sys.stderr)
        print("Run it yourself in a shell, or pipe a value straight from your password", file=sys.stderr)
        print("manager into secret-tool, e.g.:", file=sys.stderr)
        print(f"  op read --no-newline 'op://Vault/<uuid>/password' | \\", file=sys.stderr)
        print(f"    secret-tool store --label 'Lakota OneLogin' service {KEYRING_SERVICE} key password", file=sys.stderr)
        return 2
    user = args.username or input("OneLogin username: ").strip()
    if not user:
        print("No username given.", file=sys.stderr)
        return 2
    pw = getpass.getpass("OneLogin password (not echoed): ")
    if not pw:
        print("No password given.", file=sys.stderr)
        return 2
    keyring_write("username", user)
    keyring_write("password", pw)
    del pw
    print(f"Stored under Secret Service service={KEYRING_SERVICE!r} (keys: username, password).")
    print("Verify with:  lakota-grades check")
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


def cmd_print_sheet(args) -> int:
    from . import print_sheet
    opts = print_sheet.Options(dry_run=args.dry_run, kid=args.kid, date=args.date, days=args.days, overdue_days=args.overdue_days,
                               force=args.force, printer=args.printer, no_refresh=args.no_refresh, reprint=args.reprint)
    return print_sheet.run(opts, load_settings())


def main(argv=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    p = argparse.ArgumentParser(prog="lakota-grades")
    sub = p.add_subparsers(dest="cmd", required=True)
    lg = sub.add_parser("login", help="one-time headed login to seed the browser profile")
    lg.add_argument("--wait-minutes", type=int, default=15, help="how long to watch for sign-in when no terminal is attached")
    lg.set_defaults(fn=cmd_login)
    sc = sub.add_parser("set-credentials", help="store OneLogin credentials in the GNOME keyring")
    sc.add_argument("--username", help="prompted for if omitted; the password is always prompted")
    sc.set_defaults(fn=cmd_set_credentials)
    sub.add_parser("check", help="verify headless Canvas + HAC access").set_defaults(fn=cmd_check)
    r = sub.add_parser("refresh", help="pull everything now into the cache")
    r.add_argument("--no-hac", action="store_true")
    r.add_argument("--no-canvas", action="store_true")
    r.add_argument("--kids", nargs="*", help="first names to include (default all)")
    r.set_defaults(fn=cmd_refresh)
    sub.add_parser("status", help="show cache age and last source status").set_defaults(fn=cmd_status)
    sub.add_parser("serve", help="run the MCP server on stdio").set_defaults(fn=cmd_serve)
    ps = sub.add_parser("print-sheet", help="refresh, build the kids' open-work sheet, and print it (CUPS)")
    ps.add_argument("--dry-run", action="store_true", help="build the PDF under ~/.lakota-grades/sheets/ but do not print or record")
    ps.add_argument("--kid", help="one student only (first name or nickname prefix)")
    ps.add_argument("--date", help="YYYY-MM-DD to build for (testing); bypasses the 2 PM window")
    ps.add_argument("--days", type=int, default=14, help="how far ahead to look (default 14)")
    ps.add_argument("--overdue-days", type=int, default=14, help="how far back an overdue item may be (default 14)")
    ps.add_argument("--force", action="store_true", help="ignore no-print-days.txt and the 2 PM window (never reprints a day)")
    ps.add_argument("--printer", default=os.environ.get("LAKOTA_PRINTER", "Brother_MFC_J4335DW"), help="CUPS destination (LAKOTA_PRINTER)")
    ps.add_argument("--no-refresh", action="store_true", help="use the snapshot as is")
    ps.add_argument("--reprint", action="store_true", help="print again even if this date already has a printed sheet")
    ps.set_defaults(fn=cmd_print_sheet)
    args = p.parse_args(argv)
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
