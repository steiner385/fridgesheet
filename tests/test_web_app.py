"""The app skeleton: every page carries the header, the header reads the database, static files serve."""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from fridgesheet import config
from fridgesheet.web import app as webapp, db, ingest
from fridgesheet.web.stores import refreshes, runs, students

TZ = ZoneInfo("America/New_York")

#: `same_origin_only` checks Host on every request now, and TestClient's own default Host
#: ("testserver") is not an address this app is ever served on -- see `tests/web_fixtures.py`.
LOCAL_HOST_HEADERS = {"host": "127.0.0.1"}


def _tc(app) -> TestClient:
    """A `TestClient` for an already-built app, with a Host this app actually answers to."""
    return TestClient(app, headers=LOCAL_HOST_HEADERS)


def _snapshot(ok=True):
    return {
        # ingest.record's `started_at` prefers the snapshot's own `fetched_at` over `now` (the
        # collector's fetch time, not the moment it happens to land in the database), so this
        # is kept in the same minute as the `now=` the tests below pass to `record`.
        "fetched_at": "2026-09-15T06:05:11-04:00", "fetched_at_epoch": 1789000000,
        "sources": {"canvas": "ok", "hac": "ok" if ok else "login_required: portal timeout"}, "stale": {},
        "students": {"Alex": {"name": "Alex Example", "canvas_id": 1, "hac_name": "Alex Example",
            "canvas": {"courses": [{"id": 5, "name": "Honors English 9 S1-2027-Hoch", "course_code": "ENG9",
                "grade": {"current_score": 91.2, "final_score": None, "current_grade": "A-", "hidden": False},
                "staff": [{"name": "Michael Hoch", "email": None, "roles": ["TeacherEnrollment"]}], "assignments": []}]},
            "hac": {"week_view": [], "classes": [{"code": "13001 - 5", "name": "Honors English 9 S1", "marking_period_avg": 88.0,
                "last_updated": "9/11/2026", "assignments": [], "categories": []}]}}}}


@pytest.fixture
def home(tmp_path):
    return tmp_path


@pytest.fixture
def settings(home):
    return config.Settings(home=home)


@pytest.fixture
def client(settings):
    return _tc(webapp.create_app(settings))


def test_stores_read_an_empty_database(home):
    conn = db.open_db(home)
    assert refreshes.latest(conn) is None and runs.latest(conn) is None and students.visible(conn) == []
    conn.close()


def test_stores_read_the_seeded_database(home):
    conn = db.open_db(home)
    ingest.record(conn, _snapshot(ok=False), tz=TZ, now=datetime(2026, 9, 15, 6, 5, tzinfo=TZ))
    conn.execute("INSERT INTO runs(report_key, started_at, finished_at, trigger, outcome, message, pdf_path) VALUES (?,?,?,?,?,?,?)",
                 ("open-work", "2026-09-15T14:00:00-04:00", "2026-09-15T14:02:00-04:00", "schedule", "OK", "printed", "/x/sheet.pdf"))
    r = refreshes.latest(conn)
    assert r["started_at"].startswith("2026-09-15T06:05") and json.loads(r["sources"])["hac"].startswith("login_required")
    assert runs.latest(conn)["outcome"] == "OK"
    assert [x["outcome"] for x in runs.printed_on(conn, datetime(2026, 9, 15).date())] == ["OK"]
    al = students.by_key(conn, "Alex")
    assert al["name"] == "Alex Example" and [s["key"] for s in students.visible(conn)] == ["Alex"]
    cs = students.courses(conn, al["id"])
    assert [(c["source"], c["short_name"]) for c in cs] == [("canvas", "Honors English 9"), ("hac", "Honors English 9")]
    assert cs[0]["peer_course_id"] == cs[1]["id"] and cs[0]["teacher"] == "Michael Hoch"
    grades = students.latest_grades(conn, al["id"])
    assert grades[cs[0]["id"]]["current"] == 91.2 and grades[cs[1]["id"]]["average"] == 88.0
    conn.close()


def test_health_names_the_app_and_keeps_the_home_path_to_itself(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["app"] == "fridgesheet" and "version" in r.json()
    assert "started_at" in r.json() and "home" not in r.json()     # /health can answer the LAN


def test_dashboard_renders_with_an_empty_database(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "No refresh yet" in r.text and "Fridge Sheet" in r.text
    assert 'href="/static/app.css"' in r.text and 'src="/static/htmx.min.js"' in r.text


def test_header_shows_refresh_time_source_health_and_last_run(settings, home):
    conn = db.open_db(home)
    ingest.record(conn, _snapshot(ok=False), tz=TZ, now=datetime(2026, 9, 15, 6, 5, tzinfo=TZ))
    conn.execute("INSERT INTO runs(report_key, started_at, finished_at, trigger, outcome, message) VALUES (?,?,?,?,?,?)",
                 ("open-work", "2026-09-15T14:00:00-04:00", "2026-09-15T14:02:00-04:00", "schedule", "FAIL", "printer offline"))
    conn.close()
    r = _tc(webapp.create_app(settings)).get("/")
    assert "Tue 9/15 6:05 AM" in r.text            # dates.wd_md_time of the refresh (2026-09-15 is a Tuesday)
    assert "Canvas OK" in r.text and "HAC login_required" in r.text
    assert "FAIL" in r.text and "printer offline" in r.text
    # The rail lists every student and opens the child's check-in workspace; the original
    # All-work table at /kids/<key> is still reachable from the dashboard card and child nav.
    assert 'href="/kids/Alex/check-in"' in r.text
    assert 'href="/kids/Alex">Assignments</a>' in r.text


def test_static_files_are_served(client):
    assert client.get("/static/htmx.min.js").status_code == 200
    assert client.get("/static/app.css").status_code == 200


def test_unknown_page_is_a_404_page(client):
    r = client.get("/nope")
    assert r.status_code == 404 and "Not found" in r.text


def test_an_htmx_404_swaps_only_the_message(client):
    r = client.get("/items/999999", headers={"HX-Request": "true"})
    assert r.status_code == 404 and "Not found" in r.text and "<html" not in r.text


def test_a_path_that_cannot_be_an_id_is_the_404_page_not_json(client):
    r = client.get("/items/abc")
    assert r.status_code == 404 and "Not found" in r.text
    assert r.headers["content-type"].startswith("text/html")


def test_each_app_keeps_its_own_nicknames(home, settings):
    """Both apps exist before either renders: a filter dict shared between them would let the
    app built last name the kids on the pages of the app built first."""
    conn = db.open_db(home)
    ingest.record(conn, _snapshot(), tz=TZ, now=datetime(2026, 9, 15, 6, 5, tzinfo=TZ))
    conn.close()
    a = webapp.create_app(settings)
    b = webapp.create_app(config.Settings(home=home, nicknames={"Alex": "Al"}))
    assert a.state.fridgesheet.extra["env"].filters is not b.state.fridgesheet.extra["env"].filters
    plain = _tc(a).get("/").text
    assert ">Alex<" in plain and ">Al<" not in plain
    labelled = _tc(b).get("/").text
    assert ">Al<" in labelled and ">Alex<" not in labelled


def test_a_broken_late_rules_file_warns_in_the_header_instead_of_500ing(home, settings):
    conn = db.open_db(home)
    ingest.record(conn, _snapshot(), tz=TZ, now=datetime(2026, 9, 15, 6, 5, tzinfo=TZ))
    conn.close()
    (home / "late-rules.toml").write_text("[default\nlate_days = ", encoding="utf-8")
    c = _tc(webapp.create_app(settings))
    for path in ("/", "/kids/Alex", "/reconcile"):
        r = c.get(path)
        assert r.status_code == 200, path
        assert "cannot parse" in r.text and "late-rules.toml" in r.text, path
    (home / "late-rules.toml").write_text("[default]\nlate_days = 7\n", encoding="utf-8")
    assert "cannot parse" not in c.get("/").text                   # a good file clears the warning


def test_htmx_request_gets_only_the_partial(settings):
    r = _tc(webapp.create_app(settings)).get("/", headers={"HX-Request": "true"})
    assert "<html" not in r.text and "No refresh yet" in r.text


def test_vendored_assets_match_their_recorded_hashes():
    import hashlib, re
    from pathlib import Path
    static = Path(webapp.__file__).parent / "static"
    table = (static / "VENDOR.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| (\S+\.(?:js|css)) \|.*`([0-9a-f]{64})` \|$", table, re.M)
    assert len(rows) == 3
    for name, sha in rows:
        assert hashlib.sha256((static / name).read_bytes()).hexdigest() == sha, name



@pytest.mark.parametrize("host", ["127.0.0.1:8433/evil", "127.0.0.1/evil", "127.0.0.1?x=1", "127.0.0.1#frag", "127.0.0.1\\evil", "127.0.0.1 evil"])
def test_a_host_header_that_is_not_just_an_authority_is_refused(host):
    """#9: `urlsplit` ends the authority at `/`, `?` or `#`, so a `Host` carrying one parsed down
    to an allowed hostname and was admitted. Not a bypass (the surviving name is ours) but a
    `Host` is an authority and nothing else; like userinfo, anything more is refused."""
    s = config.Settings()
    assert not webapp._host_allowed(host, s)
    assert webapp._host_allowed("127.0.0.1:8433", s)
