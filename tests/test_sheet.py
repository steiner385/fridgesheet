"""The PDF builder: one document, one section per kid, letter portrait."""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("reportlab")

from fridgesheet import open_items, sheet  # noqa: E402
from tests.conftest import needs_pdftotext  # noqa: E402

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 11, 14, 0, tzinfo=TZ)


def _item(key, status, overdue, due_days=1, **kw):
    from datetime import timedelta
    d = dict(key=key, kid="Al", course="Honors Biology", name=f"Item {key}", due=NOW + timedelta(days=due_days),
             status=status, overdue=overdue, source="canvas", kind="online", points=10.0)
    d.update(kw)
    return open_items.Item(**d)


def _work(kid, items, dropped=(), handled=()):
    return open_items.OpenWork(kid=kid, as_of=NOW, items=list(items), dropped=list(dropped), handled=list(handled))


@needs_pdftotext
def test_builds_a_letter_pdf_with_a_section_per_kid(tmp_path):
    out = tmp_path / "sheet.pdf"
    sheets = [
        sheet.KidSheet("Al", _work("Al", [_item("canvas:1", "MISSING", True, -2, late_until=NOW, credit="50%"), _item("canvas:2", "DUE MON", False, 3)]),
                       diff=open_items.Diff(new={"canvas:2"}, changed={"canvas:1": "DUE THU"}, cleared=[{"course": "Latin I", "name": "Ch 1"}]), prev_label="Thu 9/10"),
        sheet.KidSheet("Sam", _work("Sam", [])),
        sheet.KidSheet("Jo", _work("Jo", [_item("hac:x", "HAC — NO GRADE", True, -3, kind="", source="hac")], dropped=[_item("canvas:9", "MISSING", True, -20)])),
    ]
    pages = sheet.build_pdf(sheets, out, data_as_of=NOW, days_ahead=14, overdue_days=14)
    data = out.read_bytes()
    assert data.startswith(b"%PDF") and pages >= 1
    text = sheet.pdf_text(out)
    assert "Al" in text and "Sam" in text and "Jo" in text
    assert "Nothing open" in text                      # Sam still gets a section
    assert "NEW" in text and "Cleared since last sheet" in text
    assert "Not shown" in text and "1 item" in text    # Jo's dropped row is counted, not listed
    assert "50% until" in text                         # deadline + credit printed on the overdue row (spelled out, kids' UX audit F11)


@needs_pdftotext
def test_stale_note_appears_in_footer(tmp_path):
    out = tmp_path / "sheet.pdf"
    sheet.build_pdf([sheet.KidSheet("Al", _work("Al", []))], out, data_as_of=NOW, days_ahead=14, overdue_days=14,
                    stale_note="refresh failed; data from 2026-09-10 06:01")
    assert "refresh failed" in sheet.pdf_text(out)


@needs_pdftotext
def test_marked_flag_and_handled_trailer_render(tmp_path):
    out = tmp_path / "sheet.pdf"
    marked = _item("canvas:1", "MISSING", True, -2, late_until=NOW, credit="50%", flag="follow_up")
    handled = _item("canvas:2", "MISSING", True, -2, late_until=NOW, credit="50%", flag="done", name="Item canvas:2 HANDLED")
    sheets = [sheet.KidSheet("Al", _work("Al", [marked], handled=[handled]))]
    sheet.build_pdf(sheets, out, data_as_of=NOW, days_ahead=14, overdue_days=14)
    text = sheet.pdf_text(out)
    assert "FOLLOW UP" in text
    assert "Handled: 1 item marked done, excused, let go or too late to submit in the app" in text   # the app's words (#129)
    assert "Item canvas:2 HANDLED" not in text


# --- kids' UX audit F11: the sheet on the fridge takes the kid's words and a readable size ----------

def _text(tmp_path, sheets):
    out = tmp_path / "sheet.pdf"
    sheet.build_pdf(sheets, out, data_as_of=NOW, days_ahead=14, overdue_days=14)
    return re.sub(r"\s+", " ", sheet.pdf_text(out, raw=True))      # one cell's words stay together


@needs_pdftotext
def test_a_young_kids_section_uses_the_childs_words(tmp_path):
    """The sheet printed the adult status words in capitals for every kid. A section for a kid
    whose grade puts them in the early or middle tier takes the phrase table's word for that
    status -- the same fact the web page shows them -- while an untiered kid's section, and the
    colour, stay as they were."""
    # One kid per PDF: poppler's text order for a two-section page differs between platforms,
    # so a section cannot be cut out of one document's text portably.
    al = _text(tmp_path, [sheet.KidSheet("Al", _work("Al", [_item("canvas:1", "MISSING", True, -2, late_until=NOW, credit="50%")]))])
    assert al.count("MISSING") == 2 and "Teacher hasn't got it" not in al             # the row and the legend
    sam = _text(tmp_path, [sheet.KidSheet("Sam", _work("Sam", [_item("canvas:2", "MISSING", True, -2, late_until=NOW, credit="50%", kid="Sam")]), tier="early")])
    assert "Teacher hasn't got it" in sam and sam.count("MISSING") == 1             # the legend keeps the key word


@needs_pdftotext
def test_an_undated_row_prints_with_no_due_date_and_no_credit_line(tmp_path):
    text = _text(tmp_path, [sheet.KidSheet("Al", _work("Al", [_item("canvas:1", "MISSING", True, due=None), _item("canvas:2", "DUE MON", False, 3)]))])
    assert "no due date" in text and "until" not in text.split("credit until")[0]


@needs_pdftotext
def test_in_class_check_has_its_own_word_colour_and_legend_entry(tmp_path):
    text = _text(tmp_path, [sheet.KidSheet("Al", _work("Al", [_item("canvas:1", "IN CLASS — CHECK", True, -2, kind="in class")]))])
    assert text.count("IN CLASS — CHECK") == 2                                        # the row and the legend
    assert sheet.STATUS_COLOR["IN CLASS — CHECK"] == sheet.PURPLE


@needs_pdftotext
def test_given_and_credit_until_are_spelled_out(tmp_path):
    text = _text(tmp_path, [sheet.KidSheet("Al", _work("Al", [_item("canvas:1", "MISSING", True, -2, late_until=NOW, credit="50%", assigned=NOW)]))])
    assert "given" in text and "50% until" in text
    assert "asg " not in text and " thru " not in text


def test_body_type_clears_ten_points():
    """8.5pt cells and 7pt sub-lines, for a reader NN/g puts at a 12pt floor on screen. Ten
    points is the smallest the two-kid page still fits on one sheet."""
    assert sheet.CELL.fontSize >= 10 and sheet.CELLB.fontSize >= 10
    assert sheet.TINY.fontSize >= 8 and sheet.SM.fontSize >= 8.5 and sheet.NOTE.fontSize >= 8.5


def test_kid_headings_are_not_coloured_like_statuses():
    """Alex's heading blue was DUE TODAY blue and Sam's purple was PAPER — CHECK purple: one
    colour, two meanings on one page. Colour is for status; a kid's name is ink."""
    assert not hasattr(sheet, "KID_COLORS")


def test_the_not_shown_line_names_the_real_overdue_window():
    """"older than two weeks" was hard-coded whatever `overdue_days` said (#130)."""
    ks = sheet.KidSheet("Jo", _work("Jo", [], dropped=[_item("canvas:9", "MISSING", True, -20)]))
    for days in (5, 14, 30):
        text = " ".join(p.text for p in sheet._tail_lines(ks, days))
        assert f"more than {days} days overdue" in text, text
        assert "two weeks" not in text
