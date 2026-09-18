# fridgesheet/print_sheet.py
"""`fridgesheet print-sheet`: the original command, now an alias for `run open-work`.

Kept so the systemd unit, the desktop shortcuts and the tests keep working unchanged.
The behaviour lives in runner.py and reports/open_work.py.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import collector
from .config import Settings
from .runner import SKIP_SEED, RunOptions, archive_copy, data_as_of, parse_skip_days, school_year  # noqa: F401  (re-exports)
from .runner import run as _run


@dataclass
class Options:
    dry_run: bool = False
    kid: str | None = None
    date: str | None = None
    days: int = 14
    overdue_days: int = 14
    force: bool = False
    printer: str | None = None
    no_refresh: bool = False
    reprint: bool = False


def run(opts: Options, settings: Settings, *, now=None, refresh=collector.collect, lp=None) -> int:
    """`lp` is the injected CUPS `subprocess.run` used by the tests; when given, printing goes
    through the Linux adapter with it and desktop notifications are off."""
    print_pdf = None
    if lp is not None:
        from .host import printing_linux
        print_pdf = lambda pdf, printer, title: printing_linux.print_pdf(pdf, printer, title, run=lp)  # noqa: E731
    ro = RunOptions(dry_run=opts.dry_run, force=opts.force, reprint=opts.reprint, date=opts.date, kid=opts.kid,
                    no_refresh=opts.no_refresh, printer=opts.printer,
                    options={"days_ahead": opts.days, "overdue_days": opts.overdue_days}, notify=lp is None)
    return _run("open-work", ro, settings, now=now, refresh=refresh, print_pdf=print_pdf)
