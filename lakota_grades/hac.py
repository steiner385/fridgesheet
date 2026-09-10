"""Home Access Center (PowerSchool eSchoolPlus) scraping.

HAC has no API. We read two pages per student:
  - Home/WeekView       -> current average per class
  - Classes/Classwork   -> every assignment with score/points/category, plus category subtotals
Selectors were verified against Lakota's HAC in September 2026.
"""
from __future__ import annotations

import logging
import re
from playwright.sync_api import Page, TimeoutError as PWTimeout

from .config import Settings

log = logging.getLogger("lakota.hac")

_AVG_RE = re.compile(r"Marking Period Avg\.\s*([\d.]+)%")
_UPD_RE = re.compile(r"Last Updated:\s*([\d/]+)")
_CLASS_RE = re.compile(r"^\s*(\S+ - \d+)\s+(.*?)\s*(?:\(Last Updated.*)?$")


class HAC:
    def __init__(self, page: Page, settings: Settings):
        self.page = page
        self.s = settings

    # ---- student switching ----------------------------------------------
    def current_student(self) -> str:
        el = self.page.locator("#sg-student-name, .sg-banner-student-name, span.sg-banner-text").first
        try:
            return el.inner_text(timeout=3000).strip()
        except PWTimeout:
            return ""

    def students(self) -> list[str]:
        """Open the Change-student dialog and list names, then close it."""
        self.page.goto(self.s.hac_base + "/Home/WeekView", wait_until="domcontentloaded")
        btn = self.page.get_by_role("button", name=re.compile("Change", re.I)).first
        try:
            btn.click(timeout=5000)
        except PWTimeout:
            return [self.current_student()]  # single-student account
        names = []
        for a in self.page.locator("#StudentPicker a, .sg-student-picker a, a[onclick*='Student']").all():
            t = a.inner_text().strip()
            if t and t not in names:
                names.append(t)
        self.page.keyboard.press("Escape")
        return names

    def select_student(self, name: str) -> None:
        self.page.goto(self.s.hac_base + "/Home/WeekView", wait_until="domcontentloaded")
        if name.lower() in self.current_student().lower():
            return
        self.page.get_by_role("button", name=re.compile("Change", re.I)).first.click()
        self.page.get_by_text(name, exact=False).first.click()
        self.page.wait_for_load_state("domcontentloaded")
        if name.lower() not in self.current_student().lower():
            raise RuntimeError(f"Could not switch HAC to student '{name}' (showing '{self.current_student()}')")

    # ---- pages -------------------------------------------------------------
    def week_view(self) -> list[dict]:
        self.page.goto(self.s.hac_base + "/Home/WeekView", wait_until="domcontentloaded")
        rows = []
        for tr in self.page.locator("table.sg-asp-table tr").all():
            tds = tr.locator("td").all()
            if len(tds) < 2:
                continue
            first = tds[0].inner_text().strip()
            avg = tds[1].inner_text().strip()
            if not first or not re.match(r"^[\d.]+$", avg):
                continue
            lines = [l.strip() for l in first.splitlines() if l.strip()]
            rows.append({"class": lines[0], "detail": " | ".join(lines[1:]), "current_average": float(avg)})
        return rows

    def _classwork_frame(self):
        self.page.goto(self.s.hac_base + "/Classes/Classwork", wait_until="domcontentloaded")
        # Classwork renders inside an iframe on Lakota's HAC; fall back to the main page.
        try:
            self.page.wait_for_selector("iframe, .AssignmentClass", timeout=15000)
        except PWTimeout:
            pass
        for f in self.page.frames:
            try:
                if f.locator(".AssignmentClass").count():
                    return f
            except Exception:
                continue
        return self.page.main_frame

    def classwork(self) -> list[dict]:
        frame = self._classwork_frame()
        frame.wait_for_selector(".AssignmentClass", timeout=20000)
        classes = []
        for block in frame.locator(".AssignmentClass").all():
            header = " ".join(block.locator(".sg-header").first.inner_text().split())
            m = _CLASS_RE.match(header)
            avg = _AVG_RE.search(header)
            upd = _UPD_RE.search(header)
            cls = {
                "code": m.group(1) if m else None,
                "name": m.group(2) if m else header,
                "marking_period_avg": float(avg.group(1)) if avg else None,
                "last_updated": upd.group(1) if upd else None,
                "assignments": [],
                "categories": [],
            }
            for tr in block.locator("table.sg-asp-table tr.sg-asp-table-data-row").all():
                cells = [" ".join(td.inner_text().split()) for td in tr.locator("td").all()]
                if len(cells) >= 6 and re.match(r"\d{2}/\d{2}/\d{4}", cells[0] or ""):
                    cls["assignments"].append({
                        "due": cells[0], "assigned": cells[1], "name": cells[2], "category": cells[3],
                        "score": _num(cells[4]), "score_raw": cells[4], "points": _num(cells[5]),
                        "percent": cells[10] if len(cells) > 10 else None,
                    })
                elif len(cells) == 4:  # category subtotal row: Category | points | total | percent
                    cls["categories"].append({"category": cells[0], "earned": _num(cells[1]), "possible": _num(cells[2]), "percent": cells[3]})
            classes.append(cls)
        return classes


def _num(s: str | None):
    if s is None:
        return None
    s = s.strip()
    if s == "" or s.upper().startswith("EX") or s.upper() == "N/A":
        return None
    try:
        return float(s)
    except ValueError:
        return None
