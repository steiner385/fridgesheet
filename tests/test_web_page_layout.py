"""One page layout on every page (docs/superpowers/specs/2026-09-26-page-layout-standard-design.md).

These hold the standard the way test_web_tier_css.py holds the tiers: the stylesheet's
tokens and breakpoints, and every template's use of the shared page head and table wrap.
CSS is not executed here; the browser check is scripts/layout_audit_measure.py.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.web_fixtures import app_for, seed

WEB = Path(__file__).resolve().parents[1] / "fridgesheet" / "web"
CSS = (WEB / "static" / "app.css").read_text(encoding="utf-8")
TEMPLATES = WEB / "templates"

#: Every full page: the shell pages that extend base.html, and the two print pages that do not.
PAGES = sorted(p.name for p in TEMPLATES.glob("*.html") if not p.name.startswith("_") and p.name != "base.html")


def _block(header: str) -> str:
    """One `@media (...)` block, by the text of its header. Each closes with `}` alone on a line."""
    m = re.search(r"@media \(?" + re.escape(header) + r"\)?\s*\{(.*?)^\}", CSS, re.S | re.M)
    assert m, f"no @media ({header}) block"
    return m.group(1)


def _root() -> str:
    return re.search(r":root\s*\{([^}]*)\}", CSS).group(1)


# --- section 3: one ceiling, one measure, one rail ------------------------------------------------

def test_the_root_defines_the_layout_tokens():
    root = _root()
    for tok, px in (("--page-max", 1600), ("--measure", 760), ("--rail", 220), ("--pad", 24)):
        assert re.search(rf"{tok}:\s*{px}px", root), f"{tok} is not {px}px at the root"


def test_main_has_one_ceiling_and_no_page_asks_for_another():
    main = re.search(r"(?m)^main\s*\{([^}]*)\}", CSS).group(1)
    assert "max-width: var(--page-max)" in main
    assert "var(--pad)" in main
    assert "main.wide" not in CSS
    for name in PAGES:
        assert 'class="wide"' not in (TEMPLATES / name).read_text(encoding="utf-8"), name


def test_prose_and_forms_are_bounded_by_the_measure_not_by_pixels():
    for sel in (r"\.page-head \.page-intro", r"\.checkin-intro", r"\.plan-form", r"\.finish-checkin", r"\.notice"):
        block = re.search(sel + r"\s*\{([^}]*)\}", CSS)
        assert block, sel
        assert "max-width: var(--measure)" in block.group(1), sel
    assert "760px" not in CSS.split(":root", 1)[1].split("}", 1)[1], "a pixel measure outside the token"


def test_the_shell_reads_the_rail_token():
    assert re.search(r"\.shell\s*\{[^}]*grid-template-columns:\s*var\(--rail\) minmax\(0, 1fr\)", CSS)


# --- section 2: the same blocks in the same order -------------------------------------------------

@pytest.mark.parametrize("name", PAGES)
def test_every_page_uses_the_shared_page_head(name):
    src = (TEMPLATES / name).read_text(encoding="utf-8")
    assert '{% include "_page_head.html" %}' in src, f"{name} draws its own heading"
    assert "{% set page_title" in src, f"{name} sets no page_title"
    # No page draws its title outside the head: the only <h2> a page template writes itself
    # is inside a card or a kid section, never at the top level before the head.
    head_at = src.index('{% include "_page_head.html" %}')
    assert "<h2>" not in src[:head_at], f"{name} has a heading above the page head"


def test_the_page_head_renders_crumb_title_actions_intro_in_that_order():
    src = (TEMPLATES / "_page_head.html").read_text(encoding="utf-8")
    order = [src.index(s) for s in ('class="crumb"', "<h2>", 'class="page-actions"', 'class="page-intro"')]
    assert order == sorted(order)


def test_a_page_title_is_the_rail_label(tmp_path):
    """Recognition, not recall: the words on the rail link are the words at the top of the page."""
    seed(tmp_path).close()
    c = app_for(tmp_path)
    rail = re.search(r"<nav>(.*?)</nav>", c.get("/").text, re.S).group(1)
    for path, label in (("/", "Today"), ("/open", "Open work"), ("/questions", "Questions"), ("/reports", "Reports"),
                        ("/schedules", "Schedules"), ("/changes", "Changes"), ("/trends", "Trends"), ("/runs", "Runs"),
                        ("/settings", "Settings"), ("/diagnostics", "Diagnostics")):
        assert f">{label}" in rail, label
        body = c.get(path).text
        assert f'<div class="page-head">\n  \n  <h2>{label}</h2>' in body or re.search(
            rf'<div class="page-head">\s*<h2>{re.escape(label)}</h2>', body), path


def test_a_childs_three_pages_share_the_name_and_the_tabs(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    for path in ("/kids/Alex", "/kids/Alex/check-in", "/kids/Alex/plan"):
        body = c.get(path).text
        assert re.search(r'<div class="page-head">\s*<h2>Alex</h2>', body), path
        assert body.index('class="page-head"') < body.index('class="child-nav"'), path


def test_a_sub_page_has_a_crumb_and_a_record_page_a_subtitle(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    step = c.get("/kids/Alex/check-in/step").text
    assert re.search(r'<p class="crumb"><a href="/kids/Alex/check-in#plan">← Alex’s check-in</a></p>\s*<h2>Add a task</h2>', step)
    course = c.get("/kids/Alex").text
    cid = re.search(r'/kids/Alex/courses/(\d+)', course).group(1)
    page = c.get(f"/kids/Alex/courses/{cid}").text
    assert re.search(r'<p class="crumb"><a href="/kids/Alex">← Alex</a></p>\s*<h2>[^<]+ <span class="subtitle">[^<]+</span></h2>', page)


def test_page_actions_sit_in_the_head_not_in_the_body(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    reports = c.get("/reports").text
    assert re.search(r'<p class="page-actions"><a class="button-link" href="/reports/new">New report</a></p>', reports)
    checkin = c.get("/kids/Alex/check-in").text
    assert re.search(r'<p class="page-actions">.*?Print plan</a></p>', checkin, re.S)
    diag = app_for(tmp_path, worker=True).get("/diagnostics").text      # the button needs the jobs worker
    assert re.search(r'<p class="page-actions">.*?Run diagnostics</button>', diag, re.S)


def test_what_a_post_did_is_a_notice_not_a_bare_coloured_line():
    for name in ("reports.html", "settings.html", "report_builder.html", "checkin.html"):
        src = (TEMPLATES / name).read_text(encoding="utf-8")
        assert '<p class="ok">' not in src, name
        assert 'class="notice' in src, name


# --- section 3: tables scroll in their own box, everywhere ------------------------------------------

@pytest.mark.parametrize("name", sorted(p.name for p in TEMPLATES.glob("*.html")))
def test_every_table_sits_in_a_table_wrap(name):
    src = (TEMPLATES / name).read_text(encoding="utf-8")
    for m in re.finditer(r'<table class="items', src):
        before = src[:m.start()]
        opened = before.count('<div class="table-wrap">')
        closed = len(re.findall(r"</table>\s*</div>", before))
        assert opened > closed, f"{name}: a table.items outside .table-wrap at offset {m.start()}"


def test_the_first_column_of_open_work_is_pinned_narrow():
    assert re.search(r"table\.work\.open-list th:nth-child\(1\)\s*\{[^}]*width: min\(22%, 8rem\)", CSS)


# --- section 2 and 4: the breakpoints and the status bar ----------------------------------------------

def test_the_strip_breakpoint_is_1023():
    narrow = _block("max-width: 1023px")
    assert re.search(r"\.rail nav\s*\{[^}]*display: flex", narrow)
    assert re.search(r"--pad:\s*16px", narrow)
    assert re.search(r"\.rail::after\s*\{[^}]*linear-gradient", narrow), "the strip needs its fade"
    assert "max-width: 800px" not in CSS


def test_below_1280_the_status_bar_drops_its_quiet_items_and_workspaces_stack():
    blocks = re.findall(r"@media \(max-width: 1279px\)\s*\{(.*?)^\}", CSS, re.S | re.M)
    joined = "\n".join(blocks)
    assert re.search(r"header\.status \.quiet\s*\{[^}]*display: none", joined)
    assert re.search(r"\.checkin-layout\s*\{[^}]*grid-template-columns: minmax\(0, 1fr\)", joined)
    assert re.search(r"\.checkin-side\s*\{[^}]*position: static", joined)
    # Found in Chromium: an override at equal specificity only wins if it comes later, and the
    # first draft put this block before `.checkin-layout`, so a 390px phone drew two columns.
    assert CSS.index(".checkin-layout {") < CSS.rindex(".checkin-layout { grid-template-columns: minmax(0, 1fr)")


def test_the_status_bar_marks_the_clock_and_a_good_run_quiet(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/").text
    header = re.search(r'<header class="status">(.*?)</header>', body, re.S).group(1)
    assert re.search(r'<span class="muted quiet">[^<]+</span>\s*$', header.strip() + "\n")
    src = (TEMPLATES / "_header.html").read_text(encoding="utf-8")
    assert "last_run.outcome == 'OK' %} class=\"quiet\"" in src
    assert "quiet" not in src.split("{% if job %}")[1].split("{% for w in warnings")[0], "a running job is never quiet"


def test_a_checkbox_is_a_24px_target_under_a_coarse_pointer():
    coarse = _block("pointer: coarse")
    assert re.search(r"input\[type=checkbox\], input\[type=radio\]\s*\{[^}]*width: 24px; height: 24px", coarse)


# --- the follow-ups: #191 outline, #192 chips, #195 the badge, #196 a phone on its side --------------

@pytest.mark.parametrize("path", ["/", "/open", "/trends", "/changes", "/questions", "/runs", "/reports"])
def test_the_page_title_is_the_only_h2_on_the_page(tmp_path, path):
    """#191: cards and Open work's kid sections were <h2>, siblings of the page title in the
    outline; they are sections (<h3>) with their lists as <h4>."""
    from tests.web_fixtures import history
    history(tmp_path).close()
    body = app_for(tmp_path).get(path).text
    assert body.count("<h2") == 1, path
    assert "<h2>" in body.split('class="page-head"')[1].split("</div>")[0]


def test_open_works_kids_are_sections_and_their_lists_parts_of_them(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/open").text
    assert re.search(r'<h3 class="kid-head"><a href="/kids/Alex">Alex</a></h3>', body)
    assert "<h4>Still fixable" in body and "<h4>Coming due" in body


def test_a_filter_chip_in_force_is_drawn_and_announced(tmp_path):
    """#192: `.badge.current` had no rule, so nothing said which window or kid was chosen."""
    assert re.search(r"\.badge\.current\s*\{[^}]*background: var\(--accent\)", CSS)
    seed(tmp_path).close()
    c = app_for(tmp_path)
    changes = c.get("/changes?window=7d&kid=Alex").text
    assert re.search(r'<a class="badge current" aria-current="true" href="[^"]*window=7d"', changes)
    assert re.search(r'<a class="badge current" aria-current="true" href="[^"]*kid=Alex[^"]*">Alex</a>', changes)
    assert changes.count('aria-current="true"') == 3            # window, kid, kind: one each
    trends = c.get("/trends?kid=Sam&weeks=8").text
    assert trends.count('aria-current="true"') == 2


def test_the_open_everything_choice_is_drawn_as_the_same_chips():
    """#192: the radio stays for the form and the keyboard; the label is the chip."""
    assert re.search(r"\.seg label\s*\{[^}]*border-radius: 10px", CSS)
    assert re.search(r"\.seg label:has\(input:checked\)\s*\{[^}]*background: var\(--accent\)", CSS)
    assert re.search(r"\.seg label:has\(input:focus-visible\)\s*\{[^}]*outline", CSS), "a hidden radio still needs a visible focus"


def test_the_update_badge_has_two_words_under_the_strip(tmp_path):
    """#195: the sentence wrapped a phone's bar back to two lines."""
    src = (TEMPLATES / "_header.html").read_text(encoding="utf-8")
    assert '<span class="long">Fridge Sheet {{ update.latest }} is available</span><span class="short">Update</span>' in src
    narrow = _block("max-width: 1023px")
    assert re.search(r"header\.status \.long\s*\{[^}]*display: none", narrow)
    assert re.search(r"header\.status \.short\s*\{[^}]*display: inline", narrow)
    assert re.search(r"header\.status \.short\s*\{[^}]*display: none", CSS)      # the base rule, beside a sidebar


def test_the_status_bar_is_shell_chrome_not_page_content(tmp_path):
    """#196: in the shell, the bar can share the strip's row on a phone held sideways."""
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/").text
    assert body.index('<header class="status">') < body.index("<main")
    assert body.index('<div class="shell">') < body.index('<header class="status">')
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert base.index('{% include "_header.html" %}') < base.index("<main")
    for name in PAGES:
        assert '_header.html' not in (TEMPLATES / name).read_text(encoding="utf-8"), name


def test_a_phone_held_sideways_puts_the_strip_and_the_bar_on_one_row():
    m = re.search(r"@media \(max-width: 1023px\) and \(max-height: 500px\)\s*\{(.*?)^\}", CSS, re.S | re.M)
    assert m, "no landscape block"
    block = m.group(1)
    assert re.search(r"\.shell\s*\{[^}]*grid-template-columns: minmax\(0, 1fr\) auto", block)
    assert re.search(r"\.rail\s*\{[^}]*grid-row: 1", block) and re.search(r"header\.status\s*\{[^}]*grid-row: 1", block)
    assert re.search(r"main\s*\{[^}]*grid-column: 1 / -1", block)
# --- the follow-ups: #189 the two halves on a phone, #190 one instruction sentence --------------------

def test_the_check_in_has_one_instruction_sentence_and_the_sources_hint_lives_in_the_record(tmp_path):
    """#190: the tab hint is the sentence; a second intro and the Canvas/HAC line under the tabs
    put three sentences and a glossary before the first card."""
    from fridgesheet.web import phrasing
    assert "copy.checkin_intro" not in phrasing.PHRASES
    seed(tmp_path).close()
    c = app_for(tmp_path)
    for path in ("/kids/Alex/check-in", "/kids/Alex/plan"):
        body = c.get(path).text
        above = body.split('class="child-nav"')[1].split("<section", 1)[0]     # the tabs, the hint, the intro
        assert "sources-hint" not in above, path
        assert "What went well" not in body, path
    assert "Talk it through together" in c.get("/kids/Alex/check-in").text
    # Assignments keeps the line under its tabs: its "Where it stands" column uses both words.
    assignments = c.get("/kids/Alex").text
    assert assignments.index('class="child-nav"') < assignments.index('class="sources-hint') < assignments.index("<section")


def test_a_stacked_check_in_names_its_two_halves_at_the_bottom_of_the_screen(tmp_path):
    """#189: a link each to the review queue and the plan, with their counts; not on the
    plan page (one half), not beside a sidebar (the CSS hides it from 1280px up)."""
    seed(tmp_path).close()
    c = app_for(tmp_path)
    checkin = c.get("/kids/Alex/check-in").text
    m = re.search(r'<nav class="halves" aria-label="Check-in sections"><a href="#review-heading">Review <span class="badge">(\d+)</span></a><a href="#plan">Next steps <span class="badge">(\d+)</span></a></nav>', checkin)
    assert m and int(m.group(1)) >= 1
    assert 'id="review-heading"' in checkin and 'id="plan"' in checkin
    assert 'class="halves"' not in c.get("/kids/Alex/plan").text
    assert re.search(r"\.halves\s*\{\s*display: none;\s*\}", CSS)
    wide = "\n".join(re.findall(r"@media \(max-width: 1279px\)\s*\{(.*?)^\}", CSS, re.S | re.M))
    assert re.search(r"\.halves\s*\{[^}]*position: sticky; bottom: 0", wide)
    assert re.search(r"\.halves a\s*\{[^}]*min-height: 44px", wide)


# --- the follow-ups: #193 a report row's controls, #194 the builder as a form ------------------------

def test_a_saved_reports_row_keeps_preview_and_print_and_folds_the_rest(tmp_path):
    from fridgesheet.web import db
    from fridgesheet.web.stores import reports as store
    seed(tmp_path).close()
    conn = db.open_db(tmp_path)
    store.seed_templates(conn, now="2026-09-15T08:00:00-04:00")
    conn.close()
    body = app_for(tmp_path, worker=True).get("/reports").text
    row = re.search(r'<td><a href="/reports/(\d+)/view".*?</tr>', body, re.S).group(0)
    assert row.count("<button>Preview</button>") == 1 and row.count("<button>Print</button>") == 1
    more = re.search(r'<details class="row-more"><summary>More</summary>(.*?)</details>', row, re.S).group(1)
    for text in (">Edit</a>", ">CSV</a>", ">JSON</a>", 'class="danger">Delete</button>'):
        assert text in more, text
    # One "Refresh data first" for the page, included by every job button; none per row.
    assert body.count('id="refresh-first"') == 1
    assert 'name="refresh_first"' not in row
    assert row.count('hx-include="#refresh-first"') == 2


def test_the_report_view_offers_the_exports_beside_edit(tmp_path):
    from fridgesheet.web import db
    from fridgesheet.web.stores import reports as store
    seed(tmp_path).close()
    conn = db.open_db(tmp_path)
    store.seed_templates(conn, now="2026-09-15T08:00:00-04:00")
    rid = conn.execute("SELECT id FROM reports ORDER BY id LIMIT 1").fetchone()["id"]
    conn.close()
    head = re.search(r'<p class="page-actions">(.*?)</p>', app_for(tmp_path).get(f"/reports/{rid}/view").text, re.S).group(1)
    assert f'href="/reports/{rid}"' in head and f'href="/reports/{rid}/export.csv"' in head and f'href="/reports/{rid}/export.json"' in head


def test_the_builder_is_laid_out_like_the_other_forms(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/reports/new").text
    form = re.search(r'<form[^>]*id="builder"[^>]*>(.*?)</form>', body, re.S).group(0)
    assert 'class="card builder-form"' in form
    assert form.count('class="settings-grid"') >= 3
    for legend in ("Kids", "Columns", "Sort", "Filters", "Chart"):
        assert re.search(rf"<legend>{legend}\b", form), legend
    assert "<p><label>" not in form                                     # the inline prose layout is gone
    assert 'id="customRange"' in form and 'id="chartFields"' in form and 'id="chartSeries"' in form
    assert re.search(r"\.builder-form\s*\{[^}]*max-width: var\(--measure\)", CSS)


# --- the follow-up: #186 Settings, five screens on a phone --------------------------------------------

def test_settings_folds_the_licences_and_the_late_rules_and_marks_where_save_stops(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    body = c.get("/settings").text
    about = re.search(r"<h3>About</h3>(.*?)</section>", body, re.S).group(1)
    assert re.search(r'<details class="fold"><summary>Fridge Sheet \S+ <span class="muted">', about)   # closed: the version line shows
    assert "MIT" in about                                                                               # the licences are still there
    rules = re.search(r'<form class="card" id="late-rules".*?</form>', body, re.S).group(0)
    fold = re.search(r'<details class="fold" >\s*<summary>(\d+) quarters? and (\d+) rules? set — show and edit</summary>', rules)
    assert fold, "the quarters and rules fold, closed on a fresh load"
    assert rules.index("<legend>Default</legend>") < rules.index('<details class="fold"') < rules.index("<legend>Quarters")
    assert 'name="quarter_date"' in rules and 'id="rule-row-tmpl"' in rules
    below = body.split('<div class="settings-below">', 1)[1]
    assert below.lstrip().startswith("<p class=\"field-help seam\">Save above keeps the cards above it.") or \
        re.match(r"\s*\{#.*?#\}\s*<p class=\"field-help seam\">", below, re.S) or 'class="field-help seam"' in below.split("<section", 1)[0]
    assert re.search(r"\.settings-below\s*\{[^}]*border-top", CSS)


def test_a_saved_or_failed_late_rules_edit_comes_back_open(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    bad = c.post("/settings/late-rules", data={"default_late_days": "x", "default_credit": "?"}).text
    assert '<details class="fold" open>' in bad
    good = c.post("/settings/late-rules", data={"default_late_days": "14", "default_credit": "?", "quarter_date": ["2026-10-15"]}).text
    assert '<details class="fold" open>' in good and "Saved late-rules.toml" in good
# --- the follow-up: #187 Runs and Changes fit a phone without a swipe ----------------------------------

def test_runs_and_changes_are_four_columns_with_the_context_under_the_name(tmp_path):
    from fridgesheet.web import db
    from fridgesheet.web.stores import runs
    from tests.web_fixtures import history
    history(tmp_path).close()
    conn = db.open_db(tmp_path)
    runs.record(conn, "open-work", "2026-09-15T07:00:00-04:00", "2026-09-15T07:01:00-04:00", "schedule", "OK", "Printed 1 page")
    conn.close()
    c = app_for(tmp_path)
    runs_page = c.get("/runs").text
    assert re.findall(r"<th>([^<]*)</th>", runs_page) == ["Started", "Report", "Outcome", "Message"]
    assert re.search(r"<td>Open Work Sheet<small class=\"by\">On a schedule</small></td>", runs_page)
    changes = c.get("/changes?window=30d").text
    assert re.findall(r"<th>([^<]*)</th>", changes) == ["When", "What", "Item", "Detail"]
    assert re.search(r'<small class="under"><a href="/kids/Alex">Alex</a> · Honors English 9 · canvas</small>', changes)
    assert 'colspan="4"' in changes and 'colspan="7"' not in runs_page
    assert re.search(r"table\.items td > small\s*\{[^}]*display: block", CSS)


def test_the_print_pages_keep_the_head_on_screen_and_drop_its_chrome_on_paper():
    printing = _block("print")
    assert ".print-page .crumb" in printing and ".print-page .page-actions" in printing
    assert ".print-page .page-head.screen-only" in printing
    view = (TEMPLATES / "report_view.html").read_text(encoding="utf-8")
    assert 'page_head_class = "screen-only"' in view          # the card carries the printed title
    plan = (TEMPLATES / "plan_print.html").read_text(encoding="utf-8")
    assert "screen-only" not in plan                          # the head is the printed title
