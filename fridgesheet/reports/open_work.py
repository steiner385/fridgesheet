# fridgesheet/reports/open_work.py
"""The open-work sheet: one section per kid, the rows open_items says are still actionable."""
from __future__ import annotations

from datetime import date

from .. import late_rules, open_items, sheet
from .base import Built, BuildContext, ReportError


def _wanted(key: str, kid: str | None, names: dict[str, str]) -> bool:
    if not kid:
        return True
    a, b = key.lower(), kid.lower()
    return a.startswith(b) or b.startswith(a) or names.get(key, "").lower().startswith(b)


class OpenWorkReport:
    key = "open-work"
    title = "Open Work Sheet"
    output_dir = "sheets"
    default_time = "14:00"

    def archive_name(self, day: date) -> str:
        return f"{day.isoformat()} Open Work.pdf"

    def build(self, snap: dict, ctx: BuildContext) -> Built:
        days_ahead = int(ctx.options.get("days_ahead") or 14)
        overdue_days = int(ctx.options.get("overdue_days") or 14)
        rules = late_rules.load(ctx.home / "late-rules.toml")
        sheets: list[sheet.KidSheet] = []
        rows: dict[str, list[dict]] = {}
        counts = []
        for key, entry in snap["students"].items():
            if not _wanted(key, ctx.kid, ctx.nicknames):
                continue
            label = ctx.nicknames.get(key, key)
            work = open_items.open_items(entry, label, ctx.now, days_ahead=days_ahead, overdue_days=overdue_days, rules=rules, flags=ctx.flags.get(key, {}), prefs=ctx.settings.sources)
            diff = open_items.compare(ctx.prev_rows.get(key, []), work.items, work.handled) if ctx.prev_rows is not None else None
            sheets.append(sheet.KidSheet(label, work, diff, ctx.prev_label))
            rows[key] = [i.to_dict() for i in work.items]
            counts.append(f"{label}={len(work.items)}")
        if not sheets:
            raise ReportError(f"no student matches --kid {ctx.kid!r}; known: {', '.join(snap['students'])}")
        pdf = ctx.out_dir / "sheet.pdf"
        pages = sheet.build_pdf(sheets, pdf, data_as_of=ctx.data_as_of, days_ahead=days_ahead, overdue_days=overdue_days,
                                stale_note=ctx.stale_note, printed_at=ctx.now)
        return Built(pdf=pdf, rows=rows, summary=f"{pages}p {' '.join(counts)}")
