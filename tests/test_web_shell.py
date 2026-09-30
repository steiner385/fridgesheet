"""The shell as the planner's edge (the surface brief for base.html, 2026-09-30): the pages as
index tabs down the rail with the current one pulled forward, the status as the page's ruled
"as of" line, the child tabs standing on the ruled header line, and on a phone one row with a
Menu fold. In kid mode Plan and Assignments first, the rest behind More."""
from __future__ import annotations

import re
from pathlib import Path

from tests.web_fixtures import app_for, seed

WEB = Path(__file__).resolve().parents[1] / "fridgesheet" / "web"
CSS = (WEB / "static" / "app.css").read_text(encoding="utf-8")
JS = (WEB / "static" / "app.js").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"no {selector} rule"
    return m.group(1)


def _narrow() -> str:
    return "\n".join(re.findall(r"@media \(max-width: 1023px\)\s*\{(.*?)\n\}", CSS, re.S))


def _rail(body: str) -> str:
    return re.search(r'<aside class="rail">(.*?)</aside>', body, re.S).group(1)


def test_the_rail_is_the_planners_edge_and_a_page_is_a_tab():
    rail = _rule(".rail")
    assert "background: var(--wash)" in rail and "border-right: 1.5px solid var(--box)" in rail
    tab = _rule(".rail nav a")
    assert "border: 1.5px solid transparent" in tab and "border-right: 0" in tab and "border-radius: 2px" in tab
    assert "border-radius: 6px" not in tab and "background" not in tab                  # no rounded pill at rest
    current = _rule(".rail nav a.current")
    assert "background: var(--paper)" in current and "border-color: var(--box)" in current  # pulled forward, open toward the page
    assert "text-decoration: underline" in _rule(".rail nav a:hover")
    group = _rule(".rail nav .group")
    assert "letter-spacing: .08em" in group and "text-transform: uppercase" in group and "font-size: var(--type-small)" in group


def test_the_status_is_the_pages_as_of_line_in_pencil():
    rules = re.findall(r"(?m)^header\.status\s*\{([^}]*)\}", CSS)
    status = next(r for r in rules if "font-size" in r)
    assert "font-size: var(--type-small)" in status and "color: var(--muted)" in status and "border-bottom: 1px solid var(--rule)" in status
    assert "13px" not in status


def test_the_status_line_carries_words_not_chips_and_menu_is_a_tab():
    """Finish review 2026-09-30: the run's outcome and the update rode the pencil line as
    outlined pills; Menu on the phone was an underlined link beside unfilled tabs."""
    badge = _rule("header.status .badge")
    assert "border: 0" in badge and "padding: 0" in badge and "background: none" in badge
    narrow = _narrow()
    menu = re.search(r"\.rail-menu > summary\s*\{([^}]*)\}", narrow).group(1)
    assert "color: var(--ink)" in menu and "border: 1.5px solid transparent" in menu and "text-decoration: underline" not in menu
    assert re.search(r"\.rail-menu > summary:hover\s*\{[^}]*text-decoration: underline", narrow)
    assert re.search(r"\.rail-menu > summary::before\s*\{[^}]*content: \"▸\"", narrow) and "gap: .3em" in menu
    assert re.search(r"\.rail nav \.rail-more > summary::before\s*\{[^}]*margin-right: \.3em", CSS)
    coarse = "\n".join(re.findall(r"@media \(pointer: coarse\)\s*\{(.*?)\n\}", CSS, re.S))
    assert re.search(r"header\.status a\s*\{[^}]*min-height: 44px", coarse)                 # Update and printed keep 44px as words


def test_the_child_tabs_stand_on_the_ruled_header_line():
    nav = _rule(".child-nav")
    assert "border-bottom: 1.5px solid var(--box)" in nav
    tab = _rule(".child-nav a")
    assert "margin-bottom: -1.5px" in tab and "border-bottom: 0" in tab and "border-radius: 2px" in tab
    current = _rule(".child-nav a[aria-current]")
    assert "background: var(--paper)" in current and "border-color: var(--box)" in current
    assert "border-bottom: 3px solid var(--accent)" not in current                        # the old underline is gone
    assert "border-bottom-color: var(--rule)" in _rule(".child-nav + .tab-hint")           # the state line closes on a hairline under the tabs


def test_the_family_tabs_fold_behind_menu_on_a_phone(tmp_path):
    seed(tmp_path).close()
    rail = _rail(app_for(tmp_path).get("/").text)
    assert re.search(r'<details class="rail-menu" data-phone-fold open><summary>Menu</summary>\s*<nav>', rail)
    assert "display: none" in _rule(".rail-menu > summary")                                 # not drawn beside a sidebar
    narrow = _narrow()
    assert re.search(r"\.rail-menu > summary\s*\{[^}]*min-height: 44px", narrow)
    assert re.search(r"\.rail nav\s*\{[^}]*flex-wrap: wrap", narrow) and ".rail::after" not in narrow
    assert re.search(r"\.rail\s*\{[^}]*border-bottom: 1\.5px solid var\(--box\)", narrow)
    assert 'details[data-phone-fold][open]' in JS                                            # app.js folds it under the strip breakpoint


def test_kid_mode_puts_plan_and_assignments_first_and_folds_the_rest(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    c.post("/who", data={"who": "Sam"})
    rail = _rail(c.get("/kids/Sam/plan").text)
    assert re.search(r'<nav class="kid">\s*<a href="/kids/Sam/plan" class="current">Plan <span id="qcount-Sam"', rail)
    assert rail.index('href="/kids/Sam"') < rail.index('<details class="rail-more"') < rail.index('href="/kids/Sam/check-in"')
    assert rail.index('href="/kids/Sam/check-in"') < rail.index('href="/trends?kid=Sam"') < rail.index('href="/changes?kid=Sam"') < rail.index('href="/who" class="foot"')
    assert "rail-menu" not in rail                                                            # a child's row shows her tabs, no Menu
    assert re.search(r"\.rail:has\(nav\.kid\) \.brand-name\s*\{[^}]*display: none", _narrow())   # the mark alone on her phone
    checkin = _rail(c.get("/kids/Sam/check-in").text)
    assert re.search(r'<details class="rail-more" open>', checkin)                            # the fold opens on the page it holds
