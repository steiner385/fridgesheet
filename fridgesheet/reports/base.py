# fridgesheet/reports/base.py
"""What a report is: one PDF for one day, built from the snapshot. The runner does
everything around it (guards, refresh, archive, print, record, notify)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from ..config import Settings


class ReportError(RuntimeError):
    """The report could not be built; the runner logs it as FAIL."""


@dataclass
class BuildContext:
    settings: Settings
    home: Path
    day: date
    now: datetime                    # tz-aware; the moment printed on the page
    out_dir: Path                    # <home>/<report.output_dir>/<day>/, already created
    kid: str | None                  # --kid filter, or None for everyone
    nicknames: dict[str, str]        # snapshot first name -> printed name
    prev_rows: dict | None           # rows.json from the most recent earlier day, if any
    prev_label: str | None           # e.g. "Thu 9/10"
    stale_note: str | None           # footer note when the refresh failed but data is fresh enough
    options: dict                    # report-specific: config.toml [reports.<key>] merged with CLI overrides
    data_as_of: datetime             # oldest fetch time in the snapshot
    # student key -> {item key -> active flag}, from the database; item keys only identify an
    # item within one student, so each kid gets their own map.
    flags: dict[str, dict[str, str]] = field(default_factory=dict)
    #: "" when this build is the day's real sheet; otherwise what it is instead -- "preview"
    #: for a dry run or a `--date` build, the kid for a `--kid` one (`runner.build_variant`).
    #: Reports put it in the PDF's name through `pdf_path`, so a side build never lands on
    #: the file the scheduled run printed (#143).
    variant: str = ""
    #: The app's database, when the runner could open it: the open-work sheet reads its rows
    #: from there, the same decided rows the Open work page shows, whenever it holds the
    #: snapshot being built (#137). None means the snapshot alone.
    conn: object | None = None

    def pdf_path(self, stem: str) -> Path:
        """`<out_dir>/<stem>.pdf` for the real sheet, `<stem>-<variant>.pdf` for a side build."""
        return self.out_dir / (f"{stem}-{self.variant}.pdf" if self.variant else f"{stem}.pdf")


@dataclass
class Built:
    pdf: Path
    rows: dict                       # written to rows.json; the next run gets it as prev_rows
    summary: str                     # for the log line and the toast, e.g. "2p Alex=5 Sam=2"


class Report(Protocol):
    key: str                         # "open-work": CLI, config section, task name
    title: str                       # "Open Work Sheet": app and toasts
    output_dir: str                  # "sheets" for open-work (existing paths); "reports/<key>" for new ones
    default_time: str                # "14:00"

    def archive_name(self, day: date) -> str: ...
    def build(self, snap: dict, ctx: BuildContext) -> Built: ...
