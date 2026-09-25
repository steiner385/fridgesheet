"""One Canvas class failing on a refresh must not make its work vanish (#140).

Two refreshes through the collector with a fake Canvas: the second 403s Algebra I. The
class is carried from the first snapshot, so its items are ingested as seen in this refresh
(`reconcile.live_items` keeps only those), the refresh still counts as good for the 24-hour
rule, and the header names the carried class instead of saying "Canvas OK" and nothing else.
"""
from __future__ import annotations

import copy
import html
from contextlib import contextmanager
from datetime import timedelta

from fridgesheet import collector
from fridgesheet.config import Settings
from fridgesheet.web import actions, db, ingest, reconcile, staleness
from fridgesheet.web.stores import refreshes
from tests.web_fixtures import NOW, TZ, app_for, snapshot

SNAP = snapshot()
KIDS = list(SNAP["students"].values())


def _course(cid):
    return next(c for e in KIDS for c in e["canvas"]["courses"] if c["id"] == cid)


class FakeCanvas:
    fail: dict = {}          # course id -> exception `course` raises for it

    def __init__(self, ctx, s):
        pass

    def observed_students(self):
        return [{"name": e["name"], "id": e["canvas_id"], "courses": [c["id"] for c in e["canvas"]["courses"]]} for e in KIDS]

    def course(self, cid):
        if cid in self.fail:
            raise self.fail[cid]
        c = _course(cid)
        return {"id": c["id"], "name": c["name"], "course_code": c["course_code"]}

    def course_grade(self, cid, uid):
        return dict(_course(cid)["grade"])

    def assignments(self, cid, uid):
        return copy.deepcopy(_course(cid)["assignments"])

    def people(self, cid):
        return copy.deepcopy(_course(cid)["staff"])


class FakeHAC:
    def __init__(self, page, s):
        self.entry = None

    def students(self):
        return [e["hac_name"] for e in KIDS]

    def select_student(self, name):
        self.entry = next(e for e in KIDS if e["hac_name"] == name)

    def week_view(self):
        return []

    def classwork(self):
        return copy.deepcopy(self.entry["hac"]["classes"])


def _settings(home) -> Settings:
    s = Settings(home=home)
    s.cache_dir.mkdir(parents=True, exist_ok=True)
    return s


def _collect(s: Settings, monkeypatch, fail: dict | None = None) -> dict:
    @contextmanager
    def fake_browser(settings, **kw):
        yield object()

    monkeypatch.setattr(collector, "browser", fake_browser)
    monkeypatch.setattr(collector, "ensure_canvas", lambda ctx, s: None)
    monkeypatch.setattr(collector, "ensure_hac", lambda ctx, s: object())
    monkeypatch.setattr(collector, "Canvas", FakeCanvas)
    monkeypatch.setattr(collector, "HAC", FakeHAC)
    monkeypatch.setattr(FakeCanvas, "fail", fail or {})
    return collector.collect(s)


def test_a_403_on_one_class_keeps_its_work_live_and_the_header_names_it(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    conn = db.open_db(tmp_path)
    ingest.record(conn, _collect(s, monkeypatch), tz=TZ, now=NOW - timedelta(days=1))

    snap = _collect(s, monkeypatch, fail={6: RuntimeError("403 Forbidden")})
    r = ingest.record(conn, snap, tz=TZ, now=NOW)

    # The carried class's item was seen in this refresh, so it is still live (not dropped).
    alex = conn.execute("SELECT id FROM students WHERE key = 'Alex'").fetchone()["id"]
    assert "Homework 4" in {row["name"] for row in reconcile.live_items(conn, alex, NOW)}
    # A refresh with a carried class is still a good refresh for the 24-hour rule: the
    # household's data is complete, one class of it is just a pull older.
    assert refreshes.latest(conn)["ok"] == 1
    assert staleness.check(conn, NOW + timedelta(hours=1)) is None
    assert r.carried == ("Alex's Algebra I",) and r.missing == ()
    assert "1 class carried from an older pull: Alex's Algebra I" in r.note()
    conn.close()

    body = html.unescape(app_for(tmp_path).get("/").text)      # Jinja renders ' as &#39;
    assert "Canvas OK (1 class carried from" in body
    assert "Alex's Algebra I (403 Forbidden)" in body


def test_a_class_that_failed_with_nothing_to_carry_is_named_as_not_fetched(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    conn = db.open_db(tmp_path)
    r = ingest.record(conn, _collect(s, monkeypatch, fail={6: RuntimeError("403 Forbidden")}), tz=TZ, now=NOW)
    conn.close()

    assert r.carried == () and r.missing == ("Alex's course 6",)
    body = html.unescape(app_for(tmp_path).get("/").text)
    assert "Canvas OK (1 class not fetched: Alex's course 6 (403 Forbidden))" in body


def test_a_clean_refresh_says_only_canvas_ok(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    conn = db.open_db(tmp_path)
    r = ingest.record(conn, _collect(s, monkeypatch), tz=TZ, now=NOW)
    row = refreshes.latest(conn)
    conn.close()

    assert r.note() == "" and row["carried"] is None
    body = app_for(tmp_path).get("/").text
    assert "Canvas OK</span>" in body and "carried" not in body


def test_the_refresh_action_logs_the_carried_class(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    conn = db.open_db(tmp_path)
    ingest.record(conn, _collect(s, monkeypatch), tz=TZ, now=NOW - timedelta(days=1))
    conn.close()
    snap = _collect(s, monkeypatch, fail={6: RuntimeError("403 Forbidden")})
    lines: list[str] = []

    result = actions.refresh(home=tmp_path, log=lines.append, settings=s, collect=lambda settings: snap, now=NOW)

    assert result.ok
    assert "1 class carried from an older pull: Alex's Algebra I" in result.message
    assert any(line.startswith("ingested") and "Alex's Algebra I" in line for line in lines)
