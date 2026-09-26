# scripts/layout_audit_seed.py
"""Seed a throwaway home for `layout_audit_measure.py`: the test fixture household (three
refreshes, so Changes and Trends have rows), its dates shifted so the fixture's "today" is this
machine's today, grades set so Alex is the older tier and Sam the early one, one finished
check-in with two planned steps, two runs, and the starter reports. Then start the app on it:

    FRIDGESHEET_HOME=/tmp/layout-audit-home env -u PYTHONPATH .venv/bin/python scripts/layout_audit_seed.py
    FRIDGESHEET_HOME=/tmp/layout-audit-home env -u PYTHONPATH .venv/bin/python -m fridgesheet.cli web --no-browser --port 8577

Run from the repository root so `tests.web_fixtures` and this checkout's `fridgesheet` import.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import web_fixtures as fx  # noqa: E402
from fridgesheet.web import db, ingest  # noqa: E402
from fridgesheet.web.stores import plans, reports as report_store, runs  # noqa: E402

HOME = Path(os.environ.get("FRIDGESHEET_HOME", "/tmp/layout-audit-home"))
SHIFT = (date.today() - fx.NOW.date()).days


def _shift_iso(m: re.Match) -> str:
    d = date.fromisoformat(m.group(0)) + timedelta(days=SHIFT)
    return d.isoformat()


def _shift_us(m: re.Match) -> str:
    mm, dd, yyyy = (int(x) for x in m.group(0).split("/"))
    d = date(yyyy, mm, dd) + timedelta(days=SHIFT)
    return f"{d.month:02d}/{d.day:02d}/{d.year}" if len(m.group(1)) == 2 else f"{d.month}/{d.day}/{d.year}"


def shift(obj):
    if isinstance(obj, str):
        s = re.sub(r"\d{4}-\d{2}-\d{2}", _shift_iso, obj)
        return re.sub(r"(\d{1,2})/\d{1,2}/\d{4}", _shift_us, s)
    if isinstance(obj, list):
        return [shift(x) for x in obj]
    if isinstance(obj, dict):
        return {k: shift(v) for k, v in obj.items()}
    return obj


if HOME.exists():
    shutil.rmtree(HOME)
HOME.mkdir(parents=True)
(HOME / "config.toml").write_text('[kids]\ngrades = { Alex = 9, Sam = 5 }\n', encoding="utf-8")

conn = db.open_db(HOME)
for snap in fx._history_snapshots():
    snap = shift(snap)
    ingest.record(conn, snap, tz=fx.TZ, now=datetime.fromisoformat(snap["fetched_at"]))
now = (fx.NOW + timedelta(days=SHIFT)).isoformat()
today = date.today()
alex = conn.execute("SELECT id FROM students WHERE key = 'Alex'").fetchone()["id"]
quiz = conn.execute("SELECT id FROM items WHERE name = 'Quiz 1'").fetchone()["id"]
lab = conn.execute("SELECT id FROM items WHERE name = 'Lab notebook'").fetchone()["id"]
step = dict(title="Quiz 1", next_step="Ask Mr Hoch whether the paper quiz was recorded", owner="Alex", state="planned",
            planned_for=today.isoformat(), minutes=10, position=1, family_account="Handed it in on paper Friday.", recorded_by="Mom",
            evidence="")
plans.save(conn, alex, step, now=now, request_key="audit-step-1", item_id=quiz)
step2 = dict(step, title="Lab notebook", next_step="Bring the notebook in tomorrow", minutes=None, position=2, family_account="", recorded_by="")
plans.save(conn, alex, step2, now=now, request_key="audit-step-2", item_id=lab)
plans.finish(conn, alex, now=now, next_check=(today + timedelta(days=7)).isoformat(), available_minutes=40,
             summary="Quiz first, then the notebook. Dad helps Thursday.", request_key="audit-checkin-1", recorded_by="Mom")
runs.record(conn, "open-work", f"{today.isoformat()}T07:00:00-04:00", f"{today.isoformat()}T07:01:12-04:00", "schedule", "OK",
            "Printed 1 page: Alex=3 Sam=2")
runs.record(conn, "refresh", f"{(today - timedelta(days=1)).isoformat()}T06:00:00-04:00", f"{(today - timedelta(days=1)).isoformat()}T06:02:30-04:00",
            "schedule", "FAIL", "HAC: timed out waiting for the gradebook")
report_store.seed_templates(conn, now=now)
conn.close()
print(f"seeded {HOME} (dates shifted {SHIFT} days)")
