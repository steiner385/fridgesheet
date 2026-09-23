"""A saved view report, wearing the same Report protocol as the open-work sheet.

Everything around a report -- the guards, the refresh, the archive copy, the `runs` row, the
toast, the lock -- lives in the runner, so a view report gets all of it by being a `Report`
and nothing more.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .. import sheet
from ..naming import safe_name
from ..web import db, views
from .base import Built, BuildContext, ReportError


@dataclass
class ViewReport:
    report_id: int
    name: str
    definition: str                  # the stored JSON

    @property
    def key(self) -> str:
        return f"view:{self.report_id}"

    @property
    def title(self) -> str:
        return self.name

    @property
    def output_dir(self) -> str:
        return f"reports/view-{self.report_id}"

    default_time = "16:00"

    def archive_name(self, day: date) -> str:
        """`reports.name` is user-editable and reaches the filesystem here, so it is reduced to
        what a file name needs -- the same `safe_name` the CSV/JSON download uses."""
        return f"{day.isoformat()} {safe_name(self.name)}.pdf"

    def build(self, snap: dict, ctx: BuildContext) -> Built:
        """The snapshot is unused: a view reads the database, which the runner has just ingested."""
        conn = db.open_db(ctx.home)
        try:
            d = views.from_json(self.definition)
            rendered = views.build(conn, d, now=ctx.now, rules=_rules(ctx), nicknames=ctx.nicknames,
                                   prefs=ctx.settings.sources)
        except views.ViewError as e:
            raise ReportError(f"{self.name}: {e}") from None
        finally:
            conn.close()
        pdf = ctx.out_dir / "report.pdf"
        note = f"{rendered.truncated} more rows are not shown" if rendered.truncated else None
        pages = sheet.build_table_pdf(rendered, pdf, title=d.title or self.name, printed_at=ctx.now,
                                      orientation=d.orientation, per_kid_sections=d.per_kid_sections, note=note)
        n = sum(len(g.rows) for g in rendered.groups)
        rows = {"columns": [c.id for c in rendered.columns],
                "rows": [r for g in rendered.groups for r in g.rows]}
        return Built(pdf=pdf, rows=rows, summary=f"{pages}p {n} rows")


def _rules(ctx: BuildContext):
    from .. import late_rules
    return late_rules.load(ctx.home / "late-rules.toml")
