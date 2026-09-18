# scripts/hac_key_spike.py
"""Throwaway check for spec risk 15.1: are HAC item keys stable, and do HAC rows link
to their Canvas twins? Reads the real ~/.lakota-grades (or LAKOTA_GRADES_HOME) and
prints a report. Nothing is written.

Run:  env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python scripts/hac_key_spike.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lakota_grades.matching import match_course, norm_name, same_item, short_course  # noqa: E402

home = Path(os.environ.get("LAKOTA_GRADES_HOME") or Path.home() / ".lakota-grades")
snap = json.loads((home / "cache" / "snapshot.json").read_text())


def hac_key(course: str, name: str) -> str:
    return f"hac:{short_course(course)}:{norm_name(name)}"


linked = hac_only = 0
collisions: Counter[str] = Counter()
raw_names: dict[str, list[str]] = defaultdict(list)
for kid, entry in snap["students"].items():
    canvas = {c["name"]: c for c in (entry.get("canvas") or {}).get("courses") or []}
    for h in (entry.get("hac") or {}).get("classes") or []:
        peer = match_course(h["name"], canvas)
        peer_names = [a["name"] for a in (peer or {}).get("assignments", [])]
        for row in h.get("assignments", []):
            if any(same_item(row["name"], n) for n in peer_names):
                linked += 1
            else:
                hac_only += 1
                key = f"{kid}|{hac_key(h['name'], row['name'])}"
                collisions[key] += 1
                raw_names[key].append(row["name"])
dupes = {k: n for k, n in collisions.items() if n > 1}
print(f"HAC rows: {linked} linked to a Canvas assignment, {hac_only} HAC-only, {len(dupes)} duplicate HAC-only keys")
for k in list(dupes)[:10]:
    print("  duplicate:", k)
    for name in raw_names[k]:
        print("    raw name:", name)

# Stability: do the HAC keys the sheet used on earlier days still resolve to the same rows today?
today_keys = {f"{kid}|{hac_key(h['name'], r['name'])}" for kid, e in snap["students"].items()
              for h in (e.get("hac") or {}).get("classes") or [] for r in h.get("assignments", [])}
for day in sorted((home / "sheets").glob("*/rows.json")):
    rows = json.loads(day.read_text())
    hac_rows = [(kid, r) for kid, items in rows.items() for r in items if r["key"].startswith("hac:")]
    seen = sum(1 for kid, r in hac_rows if f"{kid}|hac:{r['course']}:{norm_name(r['name'])}" in today_keys)
    print(f"{day.parent.name}: {len(hac_rows)} HAC rows on that sheet, {seen} still present under the same key today")
