"""Command line: `lakota-grades login|refresh|status|serve`."""
from __future__ import annotations

import argparse
import json
import logging
import sys

from . import collector
from .config import load_settings
from .session import browser, ensure_canvas, ensure_hac


def cmd_login(args) -> int:
    """Headed one-time login. Lets you sign in by hand; the persistent profile keeps the cookies."""
    s = load_settings()
    with browser(s, headless=False) as ctx:
        page = ctx.new_page()
        page.goto(s.canvas_base + "/")
        print("A browser window is open. Sign in to Canvas (via OneLogin) if prompted.")
        input("Press Enter here when Canvas shows your dashboard... ")
        page.goto(s.hac_base + "/Home/WeekView")
        input("Now make sure Home Access Center shows the Week View, then press Enter... ")
    print("Saved. Verifying headless access...")
    return cmd_check(args)


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
    print(json.dumps({"fetched_at": snap["fetched_at"], "sources": snap["sources"], "students": list(snap["students"])}, indent=2))
    return 0 if all(v == "ok" for v in snap["sources"].values() if v) else 1


def cmd_status(args) -> int:
    s = load_settings()
    snap = collector.load_snapshot(s)
    print(json.dumps({"fresh": collector.snapshot_is_fresh(s, snap), **({k: snap[k] for k in ("fetched_at", "sources")} if snap else {})}, indent=2))
    return 0


def cmd_serve(args) -> int:
    from .server import run
    run()
    return 0


def main(argv=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    p = argparse.ArgumentParser(prog="lakota-grades")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login", help="one-time headed login to seed the browser profile").set_defaults(fn=cmd_login)
    sub.add_parser("check", help="verify headless Canvas + HAC access").set_defaults(fn=cmd_check)
    r = sub.add_parser("refresh", help="pull everything now into the cache")
    r.add_argument("--no-hac", action="store_true")
    r.add_argument("--no-canvas", action="store_true")
    r.add_argument("--kids", nargs="*", help="first names to include (default all)")
    r.set_defaults(fn=cmd_refresh)
    sub.add_parser("status", help="show cache age and last source status").set_defaults(fn=cmd_status)
    sub.add_parser("serve", help="run the MCP server on stdio").set_defaults(fn=cmd_serve)
    args = p.parse_args(argv)
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
