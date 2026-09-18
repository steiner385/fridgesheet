"""The generic table PDF a view report prints. The open-work layout is not touched by any of this."""
from __future__ import annotations

import re

from fridgesheet import sheet
from fridgesheet.web.views import Column, Group, Rendered
from tests.conftest import needs_pdftotext
from tests.web_fixtures import NOW

COLS = [Column("kid", "Kid", "text"), Column("name", "Item", "text"), Column("due", "Due", "date")]


def _rendered(groups):
    return Rendered("Weekly summary", COLS, groups)


def _page_size(path):
    """(width, height) in points, read out of the file's own `/MediaBox`.

    reportlab compresses the content streams but writes the page dictionaries as plain
    text, so the box is there to be read without poppler -- which the Windows runner does
    not have. `pdfinfo` would have been the obvious tool and is the reason this test used
    to fail there while `pdftotext` (which that runner does have) kept working.
    """
    boxes = re.findall(rb"/MediaBox\s*\[([-\d. ]+)\]", path.read_bytes())
    assert boxes, f"no /MediaBox in {path.name}"
    x0, y0, x1, y1 = (float(v) for v in boxes[0].split())
    return x1 - x0, y1 - y0


@needs_pdftotext
def test_an_ampersand_in_the_title_prints_as_itself(tmp_path):
    """The footer draws plain text on the canvas: `_esc` there printed `Art & Music` as
    `Art &amp; Music` on every page. Every `Paragraph` still goes through `_esc`."""
    r = _rendered([Group("", [{"kid": "Al", "name": "Sketch & scan", "due": "9/12"}])])
    out = tmp_path / "r.pdf"
    sheet.build_table_pdf(r, out, title="Art & Music", printed_at=NOW)
    text = sheet.pdf_text(out)
    assert "&amp;" not in text
    assert text.count("Art & Music") == 2 and "Sketch & scan" in text   # the heading and the footer


@needs_pdftotext
def test_a_flat_table_prints_its_title_headers_and_rows(tmp_path):
    r = _rendered([Group("", [{"kid": "Al", "name": "Quiz 1", "due": "9/12"},
                              {"kid": "Sam", "name": "Cell diagram", "due": "9/13"}])])
    out = tmp_path / "r.pdf"
    pages = sheet.build_table_pdf(r, out, title="Weekly summary", printed_at=NOW)
    assert pages >= 1 and out.is_file()
    text = sheet.pdf_text(out)
    assert "Weekly summary" in text and "Kid" in text and "Item" in text and "Due" in text
    assert "Quiz 1" in text and "Cell diagram" in text and "9/12" in text
    assert "printed" in text.lower()


@needs_pdftotext
def test_groups_print_their_labels(tmp_path):
    r = _rendered([Group("Al", [{"kid": "Al", "name": "Quiz 1", "due": "9/12"}]),
                   Group("Sam", [{"kid": "Sam", "name": "Cell diagram", "due": "9/13"}])])
    out = tmp_path / "r.pdf"
    sheet.build_table_pdf(r, out, title="By kid", printed_at=NOW)
    text = sheet.pdf_text(out)
    assert "Al" in text and "Sam" in text and "By kid" in text


@needs_pdftotext
def test_an_empty_report_still_prints_a_page_that_says_so(tmp_path):
    out = tmp_path / "r.pdf"
    pages = sheet.build_table_pdf(_rendered([]), out, title="Nothing", printed_at=NOW)
    assert pages == 1
    assert "No rows" in sheet.pdf_text(out)


@needs_pdftotext
def test_orientation_and_per_kid_sections_are_accepted(tmp_path):
    groups = [Group("Al", [{"kid": "Al", "name": "Quiz 1", "due": "9/12"}]),
              Group("Sam", [{"kid": "Sam", "name": "Cell diagram", "due": "9/13"}])]

    out_split = tmp_path / "split.pdf"
    out_joined = tmp_path / "joined.pdf"
    pages_split = sheet.build_table_pdf(_rendered(groups), out_split, title="Wide", printed_at=NOW, per_kid_sections=True)
    pages_joined = sheet.build_table_pdf(_rendered(groups), out_joined, title="Wide", printed_at=NOW, per_kid_sections=False)
    assert pages_split > pages_joined              # the PageBreak between groups actually fires
    text = sheet.pdf_text(out_split)
    assert "Quiz 1" in text and "Cell diagram" in text

    out_portrait = tmp_path / "portrait.pdf"
    out_landscape = tmp_path / "landscape.pdf"
    sheet.build_table_pdf(_rendered(groups), out_portrait, title="Wide", printed_at=NOW, orientation="portrait")
    sheet.build_table_pdf(_rendered(groups), out_landscape, title="Wide", printed_at=NOW, orientation="landscape")
    assert _page_size(out_portrait) != _page_size(out_landscape)
    assert _page_size(out_portrait) == (612.0, 792.0) and _page_size(out_landscape) == (792.0, 612.0)


@needs_pdftotext
def test_a_long_table_paginates_and_repeats_the_header(tmp_path):
    rows = [{"kid": "Al", "name": f"Item {i}", "due": "9/12"} for i in range(120)]
    out = tmp_path / "r.pdf"
    pages = sheet.build_table_pdf(_rendered([Group("", rows)]), out, title="Long", printed_at=NOW)
    assert pages >= 2
    text = sheet.pdf_text(out)
    assert text.count("Kid") >= 2 and "Item 119" in text


@needs_pdftotext
def test_a_truncation_note_is_printed(tmp_path):
    r = Rendered("Big", COLS, [Group("", [{"kid": "Al", "name": "Quiz 1", "due": "9/12"}])], truncated=17)
    out = tmp_path / "r.pdf"
    sheet.build_table_pdf(r, out, title="Big", printed_at=NOW, note="17 more rows are not shown")
    assert out.is_file()
    assert "17 more rows are not shown" in sheet.pdf_text(out)
