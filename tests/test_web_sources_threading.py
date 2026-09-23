"""The assignments preference reaches every page, through the stores. Fixture: Alex's Quiz 1 is
MISSING in Canvas and 28/30 in HAC (tests/web_fixtures.py)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from fridgesheet import config, late_rules, sources
from fridgesheet.web import app as webapp, reconcile
from fridgesheet.web.stores import items, students
from tests.web_fixtures import LOCAL_HOST_HEADERS, NOW, seed

RULES = late_rules.LateRules(late_rules.Rule(), [], [])
HAC = sources.DEFAULT.with_default("hac", "hac")


def client(home, toml: str) -> TestClient:
    (home / "config.toml").write_text(toml)
    s = config.Settings(home=home)
    config.settings_from_doc(config.load_config_doc(home / "config.toml"), s)
    application = webapp.create_app(s, worker=False)
    application.state.fridgesheet.clock = lambda: NOW
    return TestClient(application, headers=LOCAL_HOST_HEADERS)


def quiz(views):
    return next(v for v in views if v.name == "Quiz 1")


def test_list_items_follows_prefs(tmp_path):
    conn = seed(tmp_path)
    alex = students.by_key(conn, "Alex")
    default = quiz(items.list_items(conn, alex, now=NOW, rules=RULES, show="all"))
    hac = quiz(items.list_items(conn, alex, now=NOW, rules=RULES, show="all", prefs=HAC))
    assert (default.grade, default.outcome, default.actionable) == ("Missing", "not_done", True)
    assert (hac.grade, hac.outcome, hac.actionable) == ("28/30", "done_offline", False)


def test_a_rule_for_another_class_leaves_this_one_alone(tmp_path):
    conn = seed(tmp_path)
    alex = students.by_key(conn, "Alex")
    p = sources.DEFAULT.with_rule("Alex", "Algebra I", "hac", None)
    assert quiz(items.list_items(conn, alex, now=NOW, rules=RULES, show="all", prefs=p)).grade == "Missing"


def test_dashboard_counts_follow_prefs(tmp_path):
    conn = seed(tmp_path)
    alex = students.by_key(conn, "Alex")
    before = items.dashboard_counts(conn, alex, now=NOW, rules=RULES).actionable
    after = items.dashboard_counts(conn, alex, now=NOW, rules=RULES, prefs=HAC).actionable
    assert after == before - 1


def test_the_disagreement_is_still_listed_under_hac(tmp_path):
    conn = seed(tmp_path)
    alex = students.by_key(conn, "Alex")
    qid = conn.execute("SELECT id FROM items WHERE name = 'Quiz 1'").fetchone()["id"]
    kinds = [c.kind for c in reconcile.cases(conn, alex["id"], rules=RULES, now=NOW, prefs=HAC) if c.item_id == qid]
    assert "disagree" in kinds


def test_the_kid_page_reads_the_preference_from_config(tmp_path):
    seed(tmp_path).close()
    assert "28/30" not in client(tmp_path, "").get("/kids/Alex?show=all").text
    assert "28/30" in client(tmp_path, '[sources]\nassignments = "hac"\n').get("/kids/Alex?show=all").text
