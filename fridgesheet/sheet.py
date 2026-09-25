"""The printed sheet: one letter-portrait PDF, one section per kid, built with reportlab.

Colour is carried by text only (status words, NEW tags); there are no fills, so a page costs
about as much ink as plain black text and still reads when photocopied. Colour means status
and nothing else: a kid's name is ink, so blue cannot be both Alex and DUE TODAY.

The sheet is the surface a kid reads without a screen, so each kid's section takes that
kid's tier (web/tiers.py): the status column says "Teacher hasn't got it" to a 5th grader
where it says MISSING to a parent, in the same colour. Layout, columns and the legend do not
change with the tier (kids' UX audit F11).
"""
from __future__ import annotations

import io
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .dates import due_time, long_date, md, time12, wd_md, wd_md_time
from .open_items import HANDLED_FLAGS, MARKED_FLAGS, Diff, Item, OpenWork
from .web import phrasing

RED, AMBER, BLUE, GREEN, PURPLE, GREY = (colors.HexColor(h) for h in ("#B3261E", "#B26A00", "#1A5FB4", "#1E7A3E", "#6C3FA0", "#555555"))
STATUS_COLOR = {
    "MISSING": RED, "ZERO": RED, "LATE": AMBER,
    "PAPER — CHECK": PURPLE, "IN CLASS — CHECK": PURPLE, "HAC — NO GRADE": PURPLE,
    "DUE TODAY": BLUE, "DUE TONIGHT": BLUE, "DUE TOMORROW": BLUE,
}
#: The web page's status phrase -> the sheet's word for it: one table, read this way to print
#: the page's rows (`reports.open_work.sheet_status`) and the other way to say a word in a
#: kid's tier (`status_word`), so the two surfaces cannot name one fact differently (#137).
STATUS_WORD = {"Missing": "MISSING", "Zero": "ZERO", "Late, ungraded": "LATE", "Paper, check": "PAPER — CHECK",
               "In class, check": "IN CLASS — CHECK", "HAC, no grade": "HAC — NO GRADE"}

# 10pt cells and 8pt sub-lines: the kid reading the fridge is the reader NN/g puts at a 12pt
# floor on screen, and 8.5/7 was the smallest text in the whole product. Two kids still fit
# one page.
H1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=16, leading=19)
SM = ParagraphStyle("sm", fontName="Helvetica", fontSize=8.5, leading=10.5)
CELL = ParagraphStyle("cell", fontName="Helvetica", fontSize=10, leading=12)
CELLB = ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=10, leading=12)
TINY = ParagraphStyle("tiny", fontName="Helvetica", fontSize=8, leading=9.5)
NEWTAG = ParagraphStyle("new", fontName="Helvetica-Bold", fontSize=8.5, leading=10, textColor=GREEN)
WAS = ParagraphStyle("was", fontName="Helvetica-Oblique", fontSize=8, leading=9.5, textColor=GREY)
NOTE = ParagraphStyle("note", fontName="Helvetica", fontSize=8.5, leading=10.5, textColor=GREY)

COL_WIDTHS = [0.28, 0.42, 1.12, 1.10, 2.03, 0.35, 0.72, 1.48]   # inches; sums to 7.5
MARGIN = 0.5 * inch


@dataclass
class KidSheet:
    label: str
    work: OpenWork
    diff: Diff | None = None
    prev_label: str | None = None
    tier: str = ""                   # web/tiers.py: "early", "middle", "older" or "" (no grade set)


#: The sheet's status word -> the web page's, so the phrase table can say it for the kid's tier.
#: Older and no-tier sections keep the capitals the parent knows from the legend.
_STATUS_KEY = {word: phrase for phrase, word in STATUS_WORD.items()}


def status_word(status: str, tier: str) -> str:
    """"MISSING" for a parent; "Teacher hasn't got it" for a 5th grader; "Due today" rather than
    DUE TODAY for either young tier. Same fact, same colour, the kid's words."""
    if tier not in ("early", "middle"):
        return status
    key = _STATUS_KEY.get(status)
    if key:
        return phrasing.phrase(key, tier)
    head, _, rest = status.partition(" ")       # DUE TODAY / DUE TONIGHT / DUE TOMORROW / DUE TUE
    rest = rest.lower() if rest.lower() in ("today", "tonight", "tomorrow") else rest.title()
    return f"{head.title()} {rest}".strip()


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt_due(d: datetime | None, *, from_canvas: bool = True) -> str:
    """The due date as the sheet prints it, with the time when there is one to print; "no due
    date" for undated work the teacher has marked (#137).

    This used to suppress 23:59 outright, which was right for HAC (whose 23:59 the app
    invents, since HAC gives no time) and wrong for Canvas (whose 23:59 a teacher really
    set). `dates.due_time` draws that line once, for the sheet and the pages both -- them
    disagreeing is what kept a 7:20am deadline looking the same as an 11:59pm one.
    """
    if d is None:
        return "no due date"
    s = wd_md(d)
    t = due_time(d, from_canvas=from_canvas)
    return f"{s} {t}" if t else s


def fmt_pts(p: float | None) -> str:
    if p is None:
        return "—"
    return str(int(p)) if float(p).is_integer() else str(p)


def _checkbox() -> Table:
    return Table([[""]], colWidths=[11], rowHeights=[11], style=[("BOX", (0, 0), (-1, -1), 0.75, colors.black)])


def marker(flag: str) -> str:
    """The status column's marker for a follow-up or ask-the-teacher item: the answer's own
    button, in capitals, from the one label table (#129)."""
    return phrasing.flag_label(flag, "button").upper()


def handled_words() -> str:
    """"done, excused, let go or too late to submit": the answers that take an item off the
    sheet, in the words the app uses for them, for the Handled trailer."""
    states = [phrasing.flag_label(f, "state") for f in HANDLED_FLAGS]
    return ", ".join(states[:-1]) + f" or {states[-1]}"


def _status_cell(it: Item, tier: str = "") -> Paragraph:
    style = ParagraphStyle("st", parent=CELLB, textColor=STATUS_COLOR.get(it.status, colors.black))
    text = _esc(status_word(it.status, tier))
    if it.flag in MARKED_FLAGS:
        text += f'<br/><font name="Helvetica-Bold" size="8" color="#6C3FA0">{_esc(marker(it.flag))}</font>'
    if it.overdue and it.late_until:
        credit = f"{it.credit} " if it.credit and it.credit != "?" else ""
        text += f'<br/><font name="Helvetica" size="8" color="#555555">{_esc(credit)}until {wd_md(it.late_until)}</font>'
    return Paragraph(text, style)


def _delta_cell(it: Item, diff: Diff | None):
    if diff is None:
        return ""
    if it.key in diff.new:
        return Paragraph("NEW", NEWTAG)
    if it.key in diff.changed:
        return Paragraph("was<br/>" + _esc(diff.changed[it.key].split(" ")[0].lower()), WAS)
    return ""


def _section(ks: KidSheet, date_line: str, days_ahead: int, overdue_days: int) -> list:
    work, diff = ks.work, ks.diff
    n_new = len(diff.new) if diff else 0
    n_cleared = len(diff.cleared) if diff else 0
    since = f" &nbsp;·&nbsp; {len(work.items)} open"
    if diff is not None:
        since += f", {n_new} new, {n_cleared} cleared since last sheet ({_esc(ks.prev_label or '?')})"
    head = [
        Paragraph(f"{_esc(ks.label)} — open work", H1),
        Paragraph(f"{date_line} &nbsp;·&nbsp; next {days_ahead} days plus overdue within {overdue_days}{since}", SM),
        Spacer(1, 5),
    ]
    if not work.items:
        body = [Paragraph("Nothing open. Nice work.", CELL)]
        tail = _tail_lines(ks, overdue_days)
        return [KeepTogether(head + body + tail), Spacer(1, 12)]

    data = [["", "", "Due / assigned", "Course", "Assignment", "Pts", "Via", "Status"]]
    for it in work.items:
        asg = wd_md(it.assigned) if it.assigned else "—"
        # `source` is "canvas", "hac" or "both"; only the ones Canvas knows carry a real time.
        due_cell = Paragraph(f'{_esc(fmt_due(it.due, from_canvas=it.source != "hac"))}'
                             f'<br/><font size="8">given {asg}</font>', CELL)
        via = it.source.capitalize() + (f" · {it.kind}" if it.kind else " · —")
        data.append([_checkbox(), _delta_cell(it, diff), due_cell, Paragraph(_esc(it.course), CELL), Paragraph(_esc(it.name), CELL),
                     fmt_pts(it.points), Paragraph(_esc(via), TINY), _status_cell(it, ks.tier)])
    style = [
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 10),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 10),
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.black),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (5, 0), (5, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]
    for i in range(2, len(data)):
        if work.items[i - 1].overdue != work.items[i - 2].overdue:
            style.append(("LINEABOVE", (0, i), (-1, i), 1, colors.black))
    tail = _tail_lines(ks, overdue_days)
    if tail:
        # Spanning rows inside the table, so the trailer can never be orphaned on the next page.
        for t in tail:
            data.append([t] + [""] * 7)
            r = len(data) - 1
            style += [("SPAN", (0, r), (-1, r)), ("LINEBELOW", (0, r), (-1, r), 0, colors.white), ("TOPPADDING", (0, r), (-1, r), 4)]
        style.append(("LINEBELOW", (0, len(data) - 1 - len(tail)), (-1, len(data) - 1 - len(tail)), 1, colors.black))
    else:
        style.append(("LINEBELOW", (0, -1), (-1, -1), 1, colors.black))
    t = Table(data, colWidths=[w * inch for w in COL_WIDTHS], repeatRows=1)
    t.setStyle(TableStyle(style))
    return [KeepTogether(head + [t]) if len(data) <= 8 else None, *([] if len(data) <= 8 else head + [t]), Spacer(1, 12)]


def _tail_lines(ks: KidSheet, overdue_days: int) -> list:
    out = []
    if ks.diff and ks.diff.cleared:
        names = " &nbsp;·&nbsp; ".join(f"{_esc(r.get('course', ''))}: {_esc(r.get('name', ''))}" for r in ks.diff.cleared[:10])
        more = f" &nbsp;· and {len(ks.diff.cleared) - 10} more" if len(ks.diff.cleared) > 10 else ""
        out.append(Paragraph(f"<b>Cleared since last sheet:</b> {names}{more}", SM))
    if ks.work.handled:
        n = len(ks.work.handled)
        out.append(Paragraph(f"Handled: {n} item{'s' if n != 1 else ''} marked {handled_words()} in the app", NOTE))
    if ks.work.dropped:
        n = len(ks.work.dropped)
        pts = fmt_pts(sum((i.points or 0) for i in ks.work.dropped))
        out.append(Paragraph(f"Not shown: {n} item{'s' if n != 1 else ''} past the late window or more than {overdue_days} days overdue ({pts} pts)", NOTE))
    return out


def _legend(data_as_of: datetime, stale_note: str | None) -> list:
    sw = lambda label, hexcolor: f'<font color="{hexcolor}"><b>{label}</b></font>'
    lines = [
        Spacer(1, 4),
        Paragraph(sw("MISSING / ZERO", "#B3261E") + " past due or scored 0 &nbsp; " + sw("LATE", "#B26A00") + " turned in late, not graded &nbsp; "
                  + sw("PAPER — CHECK / IN CLASS — CHECK / HAC — NO GRADE", "#6C3FA0") + " no grade yet: ask &nbsp; " + sw("DUE TODAY / TOMORROW", "#1A5FB4")
                  + " &nbsp; later due dates in black &nbsp; <i>credit until date</i> = last day the teacher still takes it", SM),
        Spacer(1, 2),
        Paragraph("<b>Via</b> where it was read (Canvas, HAC, Both) · how it is turned in (online, paper, in class) &nbsp; "
                  + sw("NEW", "#1E7A3E") + " not on the last sheet &nbsp; <i>was …</i> status changed since the last sheet &nbsp; "
                  f"Data as of {wd_md_time(data_as_of)}", SM),
    ]
    if stale_note:
        lines.append(Paragraph(f'<font color="#B3261E"><b>Note:</b> {_esc(stale_note)}</font>', SM))
    return lines


def build_pdf(sheets: list[KidSheet], out_path: Path, *, data_as_of: datetime, days_ahead: int, overdue_days: int,
              stale_note: str | None = None, printed_at: datetime | None = None) -> int:
    """Write the PDF and return its page count."""
    printed_at = printed_at or data_as_of
    date_line = long_date(printed_at)
    story = []
    for ks in sheets:
        story.extend(f for f in _section(ks, date_line, days_ahead, overdue_days) if f is not None)
    story.extend(_legend(data_as_of, stale_note))
    pages = {"n": 0}

    def footer(canvas, doc):
        pages["n"] = max(pages["n"], doc.page)
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        canvas.drawRightString(letter[0] - MARGIN, 0.4 * inch, f"fridgesheet · printed {md(printed_at)} {time12(printed_at)} · page {doc.page}")
        canvas.restoreState()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(out_path), pagesize=letter, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=0.55 * inch,
                            bottomMargin=0.65 * inch, title=f"Open work {printed_at:%Y-%m-%d}", author="fridgesheet")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return pages["n"]


def pdf_text(path: Path, *, raw: bool = False) -> str:
    """Plain text of a PDF via poppler's pdftotext (for tests and spot checks). `-layout` keeps
    the columns, which is what a spot check wants; it also interleaves a wrapped cell with its
    neighbours line by line, so a test that reads one cell's whole phrase asks for `raw`."""
    if not shutil.which("pdftotext"):
        raise RuntimeError("pdftotext (poppler-utils) is not installed")
    # `-enc UTF-8` is understood by poppler's pdftotext and xpdf's (the one the Windows CI
    # runner has, which writes Latin-1 by default and so lost the em dash in "IN CLASS —
    # CHECK"); the bytes are decoded here rather than by `text=True`, which would pick the
    # console code page on Windows. An empty answer is reported with the whole result, since a
    # test reads the text and would otherwise fail three lines later on a bare None.
    args = ["pdftotext", "-enc", "UTF-8", *([] if raw else ["-layout"]), str(path), "-"]
    p = subprocess.run(args, capture_output=True, check=True)
    if not p.stdout:
        raise RuntimeError(f"pdftotext produced no text: {p!r}")
    return p.stdout.decode("utf-8", errors="replace")


TABLE_HEAD = ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8.5, leading=10.5)
GROUP_HEAD = ParagraphStyle("gh", fontName="Helvetica-Bold", fontSize=11, leading=13, spaceBefore=6)


def build_table_pdf(rendered, out_path: Path, *, title: str, printed_at: datetime,
                    orientation: str = "portrait", per_kid_sections: bool = False, note: str | None = None,
                    chart_png: bytes | None = None) -> int:
    """A view report: a title, then one table per group, each with a repeating header row.

    Deliberately plain beside the open-work sheet's bespoke layout -- a report the parent
    designed should look like what they designed, not like the sheet.
    """
    page = landscape(letter) if orientation == "landscape" else letter
    width = page[0] - 2 * MARGIN
    cols = rendered.columns
    col_width = width / max(1, len(cols))
    story: list = [Paragraph(_esc(title), H1), Paragraph(long_date(printed_at), SM), Spacer(1, 8)]
    if chart_png:
        from reportlab.lib.utils import ImageReader
        img_w, img_h = ImageReader(io.BytesIO(chart_png)).getSize()
        story += [Image(io.BytesIO(chart_png), width=width, height=width * img_h / img_w), Spacer(1, 10)]
    if not rendered.groups:
        story.append(Paragraph("No rows matched this report.", CELL))
    for g in rendered.groups:
        if g.label:
            story.append(Paragraph(_esc(g.label), GROUP_HEAD))
        data = [[Paragraph(_esc(c.label), TABLE_HEAD) for c in cols]]
        for row in g.rows:
            data.append([Paragraph(_esc(str(row.get(c.id, ""))), CELL) for c in cols])
        t = Table(data, colWidths=[col_width] * len(cols), repeatRows=1)
        t.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, 0), 1, colors.black),
            ("LINEBELOW", (0, 1), (-1, -2), 0.25, colors.HexColor("#D9D9D9")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)
        story.append(PageBreak() if per_kid_sections and g is not rendered.groups[-1] else Spacer(1, 10))
    if note:
        story.append(Spacer(1, 6))
        story.append(Paragraph(_esc(note), NOTE))
    pages = {"n": 0}

    def footer(canvas, doc):
        pages["n"] = max(pages["n"], doc.page)
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        # Plain text on the canvas, not markup: `_esc` here would print a title's `&` as `&amp;`.
        canvas.drawRightString(page[0] - MARGIN, 0.4 * inch,
                               f"fridgesheet · {title} · printed {md(printed_at)} {time12(printed_at)} · page {doc.page}")
        canvas.restoreState()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(out_path), pagesize=page, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=0.55 * inch, bottomMargin=0.65 * inch,
                            title=f"{title} {printed_at:%Y-%m-%d}", author="fridgesheet")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return pages["n"]
