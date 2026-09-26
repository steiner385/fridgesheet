# scripts/layout_audit_measure.py
"""Render every page of a running app at six viewports and measure how it uses the screen:
the rail's width, where <main> starts and how wide it is, how much of the viewport the page
actually fills, the height of the status header, where the first heading and the first piece
of content land, page height in screens, and horizontal overflow. Screenshots go beside the
JSON. Nothing is written to the app. Used for docs/product/2026-09-26-page-layout-audit.md.

Run, against an app started from a seeded throwaway home (`scripts/layout_audit_seed.py`):

    env -u PYTHONPATH .venv/bin/python scripts/layout_audit_measure.py [base] [outdir]

`base` defaults to http://127.0.0.1:8577 and `outdir` to /tmp/layout-audit. Needs Playwright
with a Chromium (`playwright install chromium`); set PLAYWRIGHT_CHROMIUM to use another.
`VIEWPORTS=phone,desktop` limits the run to some of the seven viewports below.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8577"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/layout-audit")
OUT.mkdir(parents=True, exist_ok=True)
HOME = Path(os.environ.get("FRIDGESHEET_HOME", "/tmp/layout-audit-home"))


def _ids() -> dict[str, int]:
    conn = sqlite3.connect(HOME / "fridgesheet.db")
    conn.row_factory = sqlite3.Row
    out = {}
    for r in conn.execute("SELECT id, name FROM items WHERE name IN ('Quiz 1', 'Cell diagram')"):
        out[r["name"]] = r["id"]
    r = conn.execute("SELECT id FROM courses WHERE student_id = (SELECT id FROM students WHERE key = 'Alex') AND source = 'canvas' ORDER BY id LIMIT 1").fetchone()
    out["course"] = r["id"] if r else 5
    r = conn.execute("SELECT id FROM reports ORDER BY id LIMIT 1").fetchone()
    out["report"] = r["id"] if r else 1
    conn.close()
    return out


IDS = _ids()
PAGES = {
    "today": "/",
    "kid": "/kids/Alex?show=all",
    "kid_early": "/kids/Sam?show=all",
    "checkin": "/kids/Alex/check-in",
    "checkin_early": "/kids/Sam/check-in",
    "plan": "/kids/Alex/plan",
    "plan_print": "/kids/Alex/plan/print",
    "step": f"/kids/Alex/check-in/step?item_id={IDS.get('Quiz 1', 1)}",
    "course": f"/kids/Alex/courses/{IDS['course']}",
    "open": "/open",
    "questions": "/questions",
    "reports": "/reports",
    "report_builder": f"/reports/{IDS['report']}",
    "report_view": f"/reports/{IDS['report']}/view",
    "schedules": "/schedules",
    "changes": "/changes",
    "trends": "/trends",
    "runs": "/runs",
    "settings": "/settings",
    "diagnostics": "/diagnostics",
    "not_found": "/nowhere",
}

VIEWPORTS = {
    "phone": dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True),
    "phone_land": dict(viewport={"width": 844, "height": 390}, device_scale_factor=2, is_mobile=True, has_touch=True),
    "tablet": dict(viewport={"width": 768, "height": 1024}, device_scale_factor=2, is_mobile=True, has_touch=True),
    "tablet_land": dict(viewport={"width": 1024, "height": 768}, device_scale_factor=2, is_mobile=True, has_touch=True),
    "laptop": dict(viewport={"width": 1280, "height": 800}),
    "desktop": dict(viewport={"width": 1920, "height": 1080}),
    "wide": dict(viewport={"width": 2560, "height": 1440}),
}

MEASURE = r"""
() => {
  const vis = el => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const box = el => { if (!el) return null; const r = el.getBoundingClientRect();
    return {x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height)}; };
  const rail = document.querySelector('.rail');
  const main = document.querySelector('main');
  const header = document.querySelector('header.status');
  const stale = document.querySelector('p.stale');
  // The widest point any visible descendant of <main> reaches: how much of the page the content uses.
  let used = 0; let usedEl = '';
  if (main) for (const el of main.querySelectorAll('*')) {
    if (!vis(el)) continue; const r = el.getBoundingClientRect();
    if (r.right > used) { used = r.right; usedEl = el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.split(' ').filter(Boolean).join('.') : ''); }
  }
  const h = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
  const heads = [...document.querySelectorAll('main h1, main h2, main h3')].filter(vis);
  const firstH = heads[0] || null;
  // The first thing after the status header / stale bar that is not a heading or an eyebrow.
  let firstContent = null;
  if (main) for (const el of main.children) {
    if (el === header || el === stale || el.id === 'announce') continue;
    if (!vis(el)) continue;
    if (/^H[1-6]$/.test(el.tagName)) continue;
    firstContent = el; break;
  }
  const inter = [...document.querySelectorAll('a[href],button,input,select,textarea,summary')].filter(vis);
  const small44 = inter.filter(el => el.getBoundingClientRect().height < 44).length;
  const tables = [...document.querySelectorAll('main table')].filter(vis).map(t => { const r = t.getBoundingClientRect(); return {w: Math.round(r.width), cols: t.querySelectorAll('thead th, tr:first-child th').length}; });
  return {
    vw: innerWidth, vh: innerHeight,
    rail: box(rail), main: box(main), header: box(header), stale: box(stale),
    mainMaxWidth: main ? getComputedStyle(main).maxWidth : null,
    mainPadding: main ? getComputedStyle(main).padding : null,
    usedRight: Math.round(used), usedEl,
    unusedRightPx: Math.round(innerWidth - used),
    unusedRightPct: +((innerWidth - used) / innerWidth * 100).toFixed(1),
    pageHeight: h, screens: +(h / innerHeight).toFixed(1), overflowX: document.documentElement.scrollWidth > innerWidth,
    firstHeading: firstH ? {tag: firstH.tagName.toLowerCase(), text: firstH.innerText.trim().slice(0, 50), ...box(firstH), font: getComputedStyle(firstH).fontSize} : null,
    headings: heads.slice(0, 12).map(x => x.tagName.toLowerCase() + ': ' + x.innerText.trim().slice(0, 40)),
    firstContent: firstContent ? {tag: firstContent.tagName.toLowerCase(), cls: firstContent.className, y: box(firstContent).y} : null,
    eyebrow: !!document.querySelector('main .eyebrow'),
    intro: (() => { const p = document.querySelector('main > h2 + p.muted, main > .workspace-heading + p.muted'); return p ? p.innerText.trim().slice(0, 60) : null; })(),
    h2Count: document.querySelectorAll('main h2').length,
    tables, interactive: inter.length, shorterThan44: small44,
    bodyFont: getComputedStyle(document.body).fontSize, tier: document.body.dataset.tier || null,
  };
}
"""

report: dict[str, dict] = {}
with sync_playwright() as p:
    launch: dict = {"args": ["--no-sandbox"]}
    if os.environ.get("PLAYWRIGHT_CHROMIUM"):
        launch["executable_path"] = os.environ["PLAYWRIGHT_CHROMIUM"]
    browser = p.chromium.launch(**launch)
    only = [v for v in os.environ.get("VIEWPORTS", "").split(",") if v]
    for device, opts in VIEWPORTS.items():
        if only and device not in only:
            continue
        ctx = browser.new_context(**opts)
        page = ctx.new_page()
        for name, path in PAGES.items():
            page.goto(BASE + path, wait_until="networkidle")
            page.wait_for_timeout(150)
            m = page.evaluate(MEASURE)
            m["url"] = path
            report[f"{name}@{device}"] = m
            page.screenshot(path=str(OUT / f"{name}@{device}.png"), full_page=device not in ("wide",))
        ctx.close()
    browser.close()

(OUT / "measure.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
# A compact table for the audit: one row per page and viewport.
lines = ["page@device | vw | rail | main.x | main.w | usedRight | unused% | header.h | h.y | content.y | screens | overflowX | <44"]
for key, m in report.items():
    r = m["rail"] or {}
    mn = m["main"] or {}
    hd = m["header"] or {}
    fh = m["firstHeading"] or {}
    fc = m["firstContent"] or {}
    lines.append(f"{key} | {m['vw']} | {r.get('w', '-')}x{r.get('h', '-')} | {mn.get('x', '-')} | {mn.get('w', '-')} | {m['usedRight']} | {m['unusedRightPct']} | {hd.get('h', '-')} | {fh.get('y', '-')} | {fc.get('y', '-')} | {m['screens']} | {m['overflowX']} | {m['shorterThan44']}")
(OUT / "measure.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
