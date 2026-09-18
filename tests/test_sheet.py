"""The PDF builder: one document, one section per kid, letter portrait."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("reportlab")

from lakota_grades import open_items, sheet  # noqa: E402
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
    assert "50% thru" in text                          # deadline + credit printed on the overdue row


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
    assert "Handled: 1 item marked done, excused or ignored in the app" in text
    assert "Item canvas:2 HANDLED" not in text
