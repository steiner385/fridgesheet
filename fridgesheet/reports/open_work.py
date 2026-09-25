# fridgesheet/reports/open_work.py
"""The open-work sheet: one section per kid, the rows open_items says are still actionable."""
from __future__ import annotations

from datetime import date

from .. import config, late_rules, open_items, sheet
from ..web import tiers
from .base import Built, BuildContext, ReportError


def _wanted(key: str, kid: str | None, names: dict[str, str], keys=()) -> bool:
    """`--kid`: the student's first name or printed name, or else the start of one ("al" is Alex),
    or else a longer form of the first name ("alexander" is Alex).

    Each step applies only when the one before it selects nobody: `--kid Sam` is Sam, not also
    his sister Samantha, whose key it merely begins, and `--kid samant` is Samantha, not Sam
    (#134). `keys` is every student's key."""
    if not kid:
        return True
    b = kid.strip().lower()

    def names_of(k: str) -> list[str]:
        return [n for n in (k.lower(), names.get(k, "").lower()) if n]

    tests = (lambda k: b in names_of(k),
             lambda k: any(n.startswith(b) for n in names_of(k)),
             lambda k: b.startswith(k.lower()))
    for test in tests:
        if any(test(k) for k in (keys or (key,))):
            return test(key)
    return False


class OpenWorkReport:
    key = "open-work"
    title = "Open Work Sheet"
    output_dir = "sheets"
    default_time = "14:00"

    def archive_name(self, day: date) -> str:
        return f"{day.isoformat()} Open Work.pdf"

    def build(self, snap: dict, ctx: BuildContext) -> Built:
        days_ahead = config.day_option(ctx.options, "days_ahead")
        overdue_days = config.day_option(ctx.options, "overdue_days")
        rules = late_rules.load(ctx.home / "late-rules.toml", household=snap["students"])
        sheets: list[sheet.KidSheet] = []
        rows: dict[str, list[dict]] = {}
        counts = []
        for key, entry in snap["students"].items():
            if not _wanted(key, ctx.kid, ctx.nicknames, snap["students"]):
                continue
            label = ctx.nicknames.get(key, key)
            # Late rules and source rules resolve by the key, as the web does; the label is only printed (#133).
            work = open_items.open_items(entry, label, ctx.now, days_ahead=days_ahead, overdue_days=overdue_days, rules=rules,
                                         flags=ctx.flags.get(key, {}), prefs=ctx.settings.sources, student_key=key)
            diff = open_items.compare(ctx.prev_rows.get(key, []), work.items, work.handled) if ctx.prev_rows is not None else None
            # Each kid's section speaks in that kid's tier, as their pages do (kids' UX audit F11).
            sheets.append(sheet.KidSheet(label, work, diff, ctx.prev_label, tier=tiers.for_student(ctx.settings, key)))
            rows[key] = [i.to_dict() for i in work.items]
            counts.append(f"{label}={len(work.items)}")
        if not sheets:
            raise ReportError(f"no student matches --kid {ctx.kid!r}; known: {', '.join(snap['students'])}" if ctx.kid
                              else "the snapshot has no students yet; run a refresh first")
        pdf = ctx.out_dir / "sheet.pdf"
        pages = sheet.build_pdf(sheets, pdf, data_as_of=ctx.data_as_of, days_ahead=days_ahead, overdue_days=overdue_days,
                                stale_note=ctx.stale_note, printed_at=ctx.now)
        return Built(pdf=pdf, rows=rows, summary=f"{pages}p {' '.join(counts)}")
