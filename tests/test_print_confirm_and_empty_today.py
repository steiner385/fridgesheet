"""What the buttons promise: the printer a Print confirmation names is the one the run uses
(#127), and an empty Today page offers the Refresh that fills it (#153).

GET-only: nothing here posts a job. The host seams are faked anyway so a stray request could
never reach the real credential store, scheduler or printer list.
"""
from __future__ import annotations

import html
import re

from fridgesheet import config
from web_fixtures import app_for


def _client(home, **printers):
    c = app_for(home, worker=True)
    extra = c.app.state.fridgesheet.extra
    extra["printers"] = []
    extra["scheduling"] = object()
    extra["credstore"] = object()
    s = c.app.state.fridgesheet.settings
    s.printer = printers.pop("shared", "")
    for key, name in printers.items():
        s.reports[key.replace("_", "-")] = config.ReportConfig(printer=name)
    return c


def _confirms(page: str, hx_post: str = "/jobs/print") -> list[str]:
    return [html.unescape(m) for m in re.findall(r'hx-post="' + re.escape(hx_post) + r'"[^>]*hx-confirm="([^"]*)"', page)]


def test_dashboard_print_confirm_names_the_reports_own_printer_over_settings(tmp_path):
    c = _client(tmp_path, shared="Shared Laser", open_work="Kitchen Inkjet")
    page = c.get("/").text
    assert "Print today's sheet on Kitchen Inkjet?" in _confirms(page)
    assert "Shared Laser" not in " ".join(_confirms(page))


def test_dashboard_print_confirm_falls_back_to_settings_then_the_default(tmp_path):
    c = _client(tmp_path, shared="Shared Laser")
    assert "Print today's sheet on Shared Laser?" in _confirms(c.get("/").text)
    c.app.state.fridgesheet.settings.printer = ""
    assert "Print today's sheet on the default printer?" in _confirms(c.get("/").text)


def test_reports_print_confirms_name_the_printer_each_report_uses(tmp_path):
    c = _client(tmp_path, shared="Shared Laser", open_work="Kitchen Inkjet")
    confirms = _confirms(c.get("/reports").text)
    assert "Print Open Work Sheet on Kitchen Inkjet now?" in confirms, confirms
    # a report with no printer of its own names the shared one
    assert all(" on Kitchen Inkjet " in x or " on Shared Laser " in x for x in confirms), confirms


def test_the_empty_today_card_has_a_refresh_button_not_a_command(tmp_path):
    c = _client(tmp_path)
    page = c.get("/").text
    card = re.search(r"<h2>Nothing here yet</h2>(.*?)</div>", page, re.S).group(1)
    assert 'hx-post="/jobs/refresh"' in card and "Refresh now" in card
    assert "fridgesheet refresh</code>" not in page and "Run <code>" not in card



def test_a_saved_reports_print_confirm_names_its_own_printer(tmp_path):
    from fridgesheet.web import db
    from fridgesheet.web.stores import reports as store
    conn = db.open_db(tmp_path)
    store.seed_templates(conn, now="2026-09-15T08:00:00-04:00")
    conn.commit()
    rid = store.all(conn)[0]["id"]
    conn.close()
    c = _client(tmp_path, shared="Shared Laser", **{f"view:{rid}": "Den Printer"})
    confirms = _confirms(c.get("/reports").text)
    assert sum(x.endswith(" on Den Printer now?") for x in confirms) == 1, confirms


def test_the_reprint_confirm_names_the_printer(tmp_path):
    from fridgesheet.web import db
    pdf = tmp_path / "sheets" / "2026-09-15" / "sheet.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4")
    conn = db.open_db(tmp_path)
    conn.execute("INSERT INTO runs(report_key, started_at, finished_at, trigger, outcome, message, pdf_path) VALUES (?,?,?,?,?,?,?)",
                 ("open-work", "2026-09-15T14:00:00-04:00", "2026-09-15T14:02:00-04:00", "schedule", "OK", "printed", str(pdf)))
    conn.commit()
    conn.close()
    c = _client(tmp_path, shared="Shared Laser", open_work="Kitchen Inkjet")
    confirms = _confirms(c.get("/runs").text, "/jobs/reprint")   # Reprint prints the stored PDF (#143)
    assert confirms and all(x.endswith("on Kitchen Inkjet?") for x in confirms), confirms
