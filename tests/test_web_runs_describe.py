"""`runs.describe`: the runner's log line, read for a parent (#40 items 4 and 16)."""
from __future__ import annotations

from fridgesheet.web.stores import runs


def _row(outcome="OK", report_key="open-work", message=""):
    return {"outcome": outcome, "report_key": report_key, "message": message}


def test_a_preview_is_previewed_with_its_pages_and_per_kid_counts():
    w = runs.describe(_row(message=r"dry-run built C:\Users\x\sheets\2026-09-17\sheet.pdf 2p Alex=23 Sam=4 Jo=14 data=9/17 18:06"))
    assert (w.kind, w.pages, w.per_kid) == ("previewed", 2, [("Alex", 23), ("Sam", 4), ("Jo", 14)])
    assert w.label == "Previewed" and w.short == "previewed · 2 pages"
    assert w.detail == ""                                   # the path never reaches a page


def test_a_print_and_a_pdf_only_run_are_told_apart():
    assert runs.describe(_row(message="printed job 39 /home/x/sheet.pdf 1p Alex=5 data=9/17 14:00")).kind == "printed"
    assert runs.describe(_row(message="PDF only (not printed) /x/sheet.pdf 1p Alex=5")).label == "PDF only, not printed"
    assert runs.describe(_row(message="printed x 1p Alex=5")).short == "printed · 1 page"


def test_refreshes_skips_and_failures_keep_their_own_words():
    assert runs.describe(_row(report_key="refresh", message="refresh 2: 296 new items")).short == "refreshed"
    assert runs.describe(_row(outcome="SKIP", message="no print day: Labor Day")).detail == "no print day: Labor Day"
    f = runs.describe(_row(outcome="FAIL", message="printer offline; PDF kept at /x.pdf"))
    assert f.kind == "failed" and "printer offline" in f.detail


def test_saved_and_data_tokens_are_not_kids():
    w = runs.describe(_row(message="dry-run built /x.pdf 2p Alex=3 saved=/mnt/drive/sheet.pdf data=9/17 18:06"))
    assert w.per_kid == [("Alex", 3)]
