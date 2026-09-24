"""Kids' UX audit F12: the small items. Filter options a child can read at a glance, a sort
column you can see, the app's own reasoning folded away, and a print note that is for the
printer, not the child (docs/product/2026-09-24-kids-ux-audit.md)."""
from __future__ import annotations

import re
from pathlib import Path

from tests.web_fixtures import app_for, seed

CSS = (Path(__file__).resolve().parents[1] / "fridgesheet" / "web" / "static" / "app.css").read_text(encoding="utf-8")


def _id(tmp_path, name):
    conn = seed(tmp_path)
    try:
        return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]
    finally:
        conn.close()


def test_every_filter_option_is_a_few_words(tmp_path):
    """"done, excused, let go, or too late to submit" was a sentence inside a <select>."""
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex").text
    form = re.search(r'<form class="filters".*?</form>', body, re.S).group(0)
    options = [re.sub(r"\s+", " ", o).strip() for o in re.findall(r"<option[^>]*>(.*?)</option>", form, re.S)]
    assert options, "no filter options found"
    long = [o for o in options if len(o.split()) > 4 and not o.startswith("Honors") and not o.startswith("Algebra")]
    assert not long, long


def test_the_sorted_column_is_visible_without_the_arrow():
    """The arrow was an 11-13px glyph; on the 5th grader's phone the active column should read
    as the heavy one, and the arrow follows the tier's small size."""
    assert re.search(r'th\[aria-sort="ascending"\] a,\s*th\[aria-sort="descending"\] a\s*\{[^}]*font-weight', CSS)
    for m in re.finditer(r"th \.arrow\s*\{([^}]*)\}", CSS):
        assert "var(--type-small)" in m.group(1), m.group(0)


def test_the_apps_own_pace_reasoning_folds_away(tmp_path):
    """"Fridge Sheet has no earlier grades from this class to go on, so it allows 7 days" is
    honest and it is 17 words of app reasoning on every card of a fresh install. It stays
    on the page, inside the record."""
    pid = _id(tmp_path, "Participation")
    c = app_for(tmp_path)
    kid = c.get("/kids/Alex").text
    card = re.search(r'<div class="q card" id="q-%d".*?</div>\s*</div>' % pid, kid, re.S).group(0)
    assert "allows 7 days" in card
    assert card.index('<details class="more">') < card.index("allows 7 days")
    checkin = c.get("/kids/Alex/check-in").text
    review = re.search(r'<article class="card review-card" id="qc-%d".*?</article>' % pid, checkin, re.S).group(0)
    assert "allows 7 days" in review and re.search(r"<details[^>]*>\s*<summary>[^<]*</summary>\s*<p[^>]*app-count", review)


def test_the_print_page_keeps_its_printer_note_off_the_page(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex/plan/print").text
    assert "school inventory" not in body
    assert re.search(r'<button[^>]*data-print-plan[^>]*title="', body)
