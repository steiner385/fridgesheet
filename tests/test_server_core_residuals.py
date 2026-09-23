"""#3 residuals: /health on the LAN, one list of flags, clean badge classes, an MCP server
that does not read settings at import, and the sort orders nobody had pinned."""
from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

from fridgesheet import late_rules
from fridgesheet.web.stores import flags as flagstore, items, students
from tests.web_fixtures import NOW, app_for, seed

WEB = Path(__file__).resolve().parents[1] / "fridgesheet" / "web"
RULES = late_rules.LateRules(late_rules.Rule(), [], [])


def test_health_names_the_version_only_to_this_machine(tmp_path):
    """With allow_lan on, /health answers the whole network; the exact version tells anyone
    there which known bugs this copy has. The launcher and the updater ask from loopback."""
    seed(tmp_path).close()
    c = app_for(tmp_path)
    from starlette.testclient import TestClient
    here = TestClient(c.app, headers={"host": "127.0.0.1"}, client=("127.0.0.1", 50000))
    assert "version" in here.get("/health").json()
    lan = TestClient(c.app, headers={"host": "127.0.0.1"}, client=("192.168.1.77", 50000))
    body = lan.get("/health").json()
    assert body["app"] == "fridgesheet" and "version" not in body


def test_the_flag_menu_offers_every_flag_the_store_knows():
    """The five choices were written out in the template; a flag added to the store would
    never have appeared in the menu."""
    src = (WEB / "templates" / "_flag_menu.html").read_text(encoding="utf-8")
    assert '("done", "It\'s done")' not in src and "FLAG_CHOICES" in src
    assert [f for f, _ in flagstore.CHOICES] == list(flagstore.FLAGS)


def test_badge_classes_carry_no_stray_space(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    for page in ("/trends", "/changes"):
        assert not re.search(r'class="badge "', c.get(page).text), page


def test_the_mcp_server_does_not_read_settings_at_import(tmp_path):
    """A broken config.toml made `import fridgesheet.server` itself raise, so the MCP server
    died at start with a traceback. Now the first tool call is where it surfaces. Run in a
    child process: reloading the module in this one re-imports the `mcp` package badly."""
    import os
    import subprocess
    import sys
    (tmp_path / "config.toml").write_text("[reports.open-work]\ntime = \"25:00\"\n", encoding="utf-8")
    code = ("import fridgesheet.server as s\n"
            "from fridgesheet import config\n"
            "try:\n    s._settings()\nexcept config.ConfigError:\n    print('raised on first use')\n")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"} | {"FRIDGESHEET_HOME": str(tmp_path)}
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                       cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "raised on first use"


def _undated(conn, name):
    conn.execute("UPDATE items SET due = NULL WHERE name = ?", (name,))


def test_work_with_no_due_date_sorts_last_and_says_so(tmp_path):
    conn = seed(tmp_path)
    _undated(conn, "Reading log")
    alex = students.by_key(conn, "Alex")
    rows = items.list_items(conn, alex, now=NOW, rules=RULES, show="all", sort="due")
    undated = [v for v in rows if v.due is None]
    assert rows[-len(undated):] == undated and any(v.name == "Reading log" for v in undated)
    assert next(v for v in rows if v.name == "Reading log").status == "No due date"
    backwards = items.list_items(conn, alex, now=NOW, rules=RULES, show="all", sort="due", direction="desc")
    conn.close()
    assert backwards[0].due is None                  # the whole order turns round, as documented


def test_sorting_by_status_puts_fixable_work_first(tmp_path):
    conn = seed(tmp_path)
    alex = students.by_key(conn, "Alex")
    rows = items.list_items(conn, alex, now=NOW, rules=RULES, show="all", sort="status")
    conn.close()
    flags = [v.actionable for v in rows]
    assert flags == sorted(flags, reverse=True) and flags[0]
