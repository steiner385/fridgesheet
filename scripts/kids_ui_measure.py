# scripts/kids_ui_measure.py
"""Render the child-facing pages of a running app and measure what a child would meet:
body type size, the tier attribute, words in <main>, interactive elements and how many of
them are under 24 px (WCAG 2.5.8) and under 44 px, the smallest rendered font, page height
in screens, and horizontal overflow. Screenshots go beside the JSON. Nothing is written to
the app. Used for docs/product/2026-09-24-kids-ux-audit.md.

Run, against an app started from a seeded throwaway home (see the audit, section 3):

    env -u PYTHONPATH ~/fridgesheet/.venv/bin/python scripts/kids_ui_measure.py <label> <kid> [base] [outdir]

`label` names the run ("early", "older"); `kid` is the student key; `base` defaults to
http://127.0.0.1:8433 and `outdir` to /tmp/kids-ui-<label>. Needs Playwright with a Chromium
(`playwright install chromium`); set PLAYWRIGHT_CHROMIUM to an executable to use another.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

label = sys.argv[1] if len(sys.argv) > 1 else "run"
kid = sys.argv[2] if len(sys.argv) > 2 else "Alex"
BASE = sys.argv[3] if len(sys.argv) > 3 else "http://127.0.0.1:8433"
OUT = Path(sys.argv[4] if len(sys.argv) > 4 else f"/tmp/kids-ui-{label}")
OUT.mkdir(parents=True, exist_ok=True)

PAGES = {
    "kid": f"/kids/{kid}?show=all",
    "checkin": f"/kids/{kid}/check-in",
    "plan": f"/kids/{kid}/plan",
    "plan_print": f"/kids/{kid}/plan/print",
    "step": f"/kids/{kid}/check-in/step",
    "open": "/open",
    "questions": "/questions",
    "today": "/",
}

MEASURE = r"""
() => {
  const vis = el => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const inter = [...document.querySelectorAll('a[href],button,input,select,textarea,summary,[role=button]')].filter(vis);
  const boxes = inter.map(el => { const r = el.getBoundingClientRect();
    return {tag: el.tagName.toLowerCase(), text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 40),
            w: Math.round(r.width), h: Math.round(r.height)}; });
  const small24 = boxes.filter(b => b.w < 24 || b.h < 24);
  const small44 = boxes.filter(b => b.h < 44);
  const textEls = [...document.querySelectorAll('body *')].filter(el => vis(el) && [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()));
  const sizes = textEls.map(el => parseFloat(getComputedStyle(el).fontSize));
  const hist = {}; sizes.forEach(s => { hist[s] = (hist[s] || 0) + 1; });
  const main = document.querySelector('main') || document.body;
  const h = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
  const first = document.querySelector('main button.primary, main .button-link, main .answers button');
  return {
    bodyFont: getComputedStyle(document.body).fontSize, tier: document.body.dataset.tier || null,
    pageHeight: h, screens: +(h / innerHeight).toFixed(1), overflowX: document.documentElement.scrollWidth > innerWidth,
    mainWords: main.innerText.split(/\s+/).filter(Boolean).length,
    interactive: inter.length, smallerThan24: small24.length, shorterThan44: small44.length,
    small24: small24.slice(0, 20), small44Sample: small44.slice(0, 20),
    fontSizes: hist, minFont: Math.min(...sizes),
    firstPrimaryActionY: first ? Math.round(first.getBoundingClientRect().top + scrollY) : null,
    headings: [...document.querySelectorAll('main h2, main h3')].filter(vis).map(x => x.innerText.trim().slice(0, 60)),
    details: document.querySelectorAll('details').length, detailsOpen: document.querySelectorAll('details[open]').length,
  };
}
"""

report: dict[str, dict] = {}
with sync_playwright() as p:
    launch: dict = {"args": ["--no-sandbox"]}
    if os.environ.get("PLAYWRIGHT_CHROMIUM"):
        launch["executable_path"] = os.environ["PLAYWRIGHT_CHROMIUM"]
    browser = p.chromium.launch(**launch)
    for device, opts in (("desktop", dict(viewport={"width": 1280, "height": 800})),
                         ("phone", dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True))):
        ctx = browser.new_context(**opts)
        page = ctx.new_page()
        for name, path in PAGES.items():
            page.goto(BASE + path, wait_until="networkidle")
            report[f"{label}/{name}/{device}"] = page.evaluate(MEASURE)
            page.screenshot(path=str(OUT / f"{label}-{name}-{device}.png"), full_page=True)
        ctx.close()
    browser.close()

(OUT / f"report-{label}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
for key, m in report.items():
    print(f"{key:34s} font={m['bodyFont']:>5} tier={str(m['tier']):6s} words={m['mainWords']:4d} inter={m['interactive']:3d} "
          f"<24px={m['smallerThan24']:2d} <44px={m['shorterThan44']:3d} screens={m['screens']:4} minFont={m['minFont']} overflowX={m['overflowX']}")
print(f"screenshots and report-{label}.json in {OUT}")
