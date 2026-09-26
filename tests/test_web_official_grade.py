"""The grades preference picks the headline average. Fixture: Alex's Honors English 9 is 91.2 in
Canvas and 88 in HAC; the history fixture moves HAC 85 -> 88 and Canvas 93 -> 91.2."""
from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from fridgesheet import config, sources
from fridgesheet.web import app as webapp, views
from fridgesheet.web.stores import changes, students
from tests.web_fixtures import LOCAL_HOST_HEADERS, NOW, TZ, chart_configs, history, seed

CANVAS_GRADES = '[sources]\ngrades = "canvas"\n'


def client(home, toml: str) -> TestClient:
    (home / "config.toml").write_text(toml)
    s = config.Settings(home=home)
    config.settings_from_doc(config.load_config_doc(home / "config.toml"), s)
    application = webapp.create_app(s, worker=False)
    application.state.fridgesheet.clock = lambda: NOW
    return TestClient(application, headers=LOCAL_HOST_HEADERS)


def english(conn) -> int:
    return conn.execute("SELECT id FROM courses WHERE source = 'canvas' AND short_name = 'Honors English 9'").fetchone()["id"]


def grade_card(body: str) -> str:
    return body.split("<h3>Grade</h3>", 1)[1].split("</div>", 1)[0]


def test_grade_lines_put_the_official_source_first():
    canvas = {"current": 91.2, "letter": "A-", "average": None, "last_updated": None}
    hac = {"current": None, "letter": None, "average": 88.0, "last_updated": "9/11/2026"}
    assert [g.source for g in students.grade_lines(canvas, hac, "hac")] == ["hac", "canvas"]
    assert [g.source for g in students.grade_lines(canvas, hac, "canvas")] == ["canvas", "hac"]
    assert [g.source for g in students.grade_lines(canvas, None, "hac")] == ["canvas"]      # the gap is filled
    assert students.grade_lines(None, None, "hac") == []


def test_course_page_headline_follows_the_grades_source(tmp_path):
    conn = seed(tmp_path)
    cid = english(conn)
    conn.close()
    default = grade_card(client(tmp_path, "").get(f"/kids/Alex/courses/{cid}").text)
    assert default.index("HAC average") < default.index("Canvas current")
    assert "A-" in default and "88" in default and "91.2" in default
    flipped = grade_card(client(tmp_path, CANVAS_GRADES).get(f"/kids/Alex/courses/{cid}").text)
    assert flipped.index("Canvas current") < flipped.index("HAC average")


def _grade_labels(body: str) -> set[str]:
    return {d["label"] for c in chart_configs(body) if c["options"]["scales"]["x"].get("type") == "time"
            for d in c["data"]["datasets"]}


def test_the_trends_grade_chart_draws_only_the_official_source(tmp_path):
    """A chart must not mix sources: each class's line comes from the grades source, and the
    other source's line for the same class is not drawn. With every line official, the
    "· official" marker the course page uses would say nothing, so it is not shown."""
    history(tmp_path).close()
    labels = _grade_labels(client(tmp_path, "").get("/trends").text)
    assert "Honors English 9 (HAC average)" in labels and "Honors English 9 (Canvas current)" not in labels
    assert not any("official" in l for l in labels)
    labels = _grade_labels(client(tmp_path, CANVAS_GRADES).get("/trends").text)
    assert "Honors English 9 (Canvas current)" in labels and "Honors English 9 (HAC average)" not in labels


def test_the_course_page_chart_still_says_which_line_is_official(tmp_path):
    """The course page draws one course's own line, which may or may not be the official
    source, so its marker keeps meaning there."""
    conn = history(tmp_path)
    cid = english(conn)
    conn.close()
    labels = _grade_labels(client(tmp_path, "").get(f"/kids/Alex/courses/{cid}").text)
    assert labels == {"Honors English 9 (Canvas current)"}
    labels = _grade_labels(client(tmp_path, CANVAS_GRADES).get(f"/kids/Alex/courses/{cid}").text)
    assert labels == {"Honors English 9 (Canvas current) · official"}


def test_grade_change_events_say_which_is_official(tmp_path):
    conn = history(tmp_path)
    since = datetime(2026, 9, 1, tzinfo=TZ)
    details = [e.detail for e in changes.since(conn, since=since, limit=None) if e.kind == "course_grade"]
    assert any(d.startswith("HAC average") and d.endswith("· official") for d in details)
    assert all(not d.endswith("· official") for d in details if d.startswith("Canvas current"))
    flipped = sources.DEFAULT.with_default("canvas", "canvas")
    details = [e.detail for e in changes.since(conn, since=since, limit=None, prefs=flipped) if e.kind == "course_grade"]
    assert any(d.startswith("Canvas current") and d.endswith("· official") for d in details)


def test_report_builder_grades_rows_carry_official(tmp_path):
    conn = history(tmp_path)
    rows = [r for r, _, _ in views._grade_rows(conn, views.Definition(source="grades"), now=NOW, nicknames={})]
    assert {r["source"]: r["official"] for r in rows if r["course"] == "Honors English 9"} == {"hac": "yes", "canvas": ""}
    assert "official" in views.DEFAULT_COLUMNS["grades"]


def test_only_one_twin_is_official_when_a_rule_names_one_twin(tmp_path):
    """Review finding: grade_series resolved each twin by its own name, so a rule matching only the
    Canvas name made both the Canvas and the HAC series official -- and now that Trends draws
    only the official line, that would have drawn both again."""
    history(tmp_path).close()
    labels = _grade_labels(client(tmp_path, '[[sources.rule]]\ncourse = "Hoch"\ngrades = "canvas"\n').get("/trends").text)
    assert "Honors English 9 (Canvas current)" in labels and "Honors English 9 (HAC average)" not in labels
    assert "Algebra I (HAC average)" in labels                           # the rule is about one class
