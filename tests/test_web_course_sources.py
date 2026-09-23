"""The course page writes the one rule for this kid and this class."""
from __future__ import annotations

from fastapi.testclient import TestClient

from fridgesheet import config
from fridgesheet.web import app as webapp
from tests.web_fixtures import LOCAL_HOST_HEADERS, NOW, seed


def client(home, toml: str = "") -> tuple[TestClient, object]:
    (home / "config.toml").write_text(toml)
    s = config.Settings(home=home)
    config.settings_from_doc(config.load_config_doc(home / "config.toml"), s)
    application = webapp.create_app(s, worker=False)
    application.state.fridgesheet.clock = lambda: NOW
    return TestClient(application, headers=LOCAL_HOST_HEADERS), application


def course_id(home, short: str) -> int:
    conn = seed(home)
    cid = conn.execute("SELECT id FROM courses WHERE source = 'canvas' AND short_name = ?", (short,)).fetchone()["id"]
    conn.close()
    return cid


def rules(home):
    return config.load_config_doc(home / "config.toml").get("sources", {}).get("rule")


def test_the_control_writes_a_short_name_rule_and_the_page_follows_it(tmp_path):
    from tests.web_fixtures import canvas_grades_later
    cid = course_id(tmp_path, "Honors English 9")
    conn = seed(tmp_path)
    canvas_grades_later(conn, "Quiz 1", 20.0)        # Canvas 20/30, HAC 28/30: the preference picks one
    conn.close()
    c, _ = client(tmp_path)
    assert "20/30" in c.get(f"/kids/Alex/courses/{cid}").text
    assert "Sources for this class" in c.get(f"/kids/Alex/courses/{cid}").text
    r = c.post(f"/kids/Alex/courses/{cid}/sources", data={"assignments": "hac", "grades": ""}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/kids/Alex/courses/{cid}"
    assert rules(tmp_path) == [{"kid": "Alex", "course": "Honors English 9", "assignments": "hac"}]
    assert "28/30" in c.get(f"/kids/Alex/courses/{cid}").text          # Quiz 1 now reads HAC's score


def test_saving_again_replaces_and_default_on_both_removes(tmp_path):
    cid = course_id(tmp_path, "Honors English 9")
    c, _ = client(tmp_path)
    c.post(f"/kids/Alex/courses/{cid}/sources", data={"assignments": "hac", "grades": ""})
    c.post(f"/kids/Alex/courses/{cid}/sources", data={"assignments": "", "grades": "canvas"})
    assert rules(tmp_path) == [{"kid": "Alex", "course": "Honors English 9", "grades": "canvas"}]
    c.post(f"/kids/Alex/courses/{cid}/sources", data={"assignments": "", "grades": ""})
    assert rules(tmp_path) is None


def test_a_junk_value_counts_as_default(tmp_path):
    cid = course_id(tmp_path, "Honors English 9")
    c, _ = client(tmp_path)
    c.post(f"/kids/Alex/courses/{cid}/sources", data={"assignments": "powerschool", "grades": ""})
    assert rules(tmp_path) is None


def test_the_control_names_a_broader_rule_in_force(tmp_path):
    cid = course_id(tmp_path, "Honors English 9")
    c, _ = client(tmp_path, '[[sources.rule]]\nkid = "Alex"\ngrades = "canvas"\n')
    assert "from a rule for Alex" in c.get(f"/kids/Alex/courses/{cid}").text


def test_another_kids_course_is_404(tmp_path):
    cid = course_id(tmp_path, "Science 7")
    c, _ = client(tmp_path)
    assert c.post(f"/kids/Alex/courses/{cid}/sources", data={"assignments": "hac"}).status_code == 404
