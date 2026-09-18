"""Home Access Center (PowerSchool eSchoolPlus) scraping.

HAC has no API. We read two pages per student:
  - Home/WeekView       -> current average per class
  - Classes/Classwork   -> every assignment with score/points/category, plus category subtotals
Selectors were verified against Lakota's HAC in September 2026.
"""
from __future__ import annotations

import logging
import re
import time
from playwright.sync_api import Page, TimeoutError as PWTimeout

from .config import Settings

log = logging.getLogger("lakota.hac")

_AVG_RE = re.compile(r"Marking Period Avg\.\s*([\d.]+)%")
_UPD_RE = re.compile(r"Last Updated:\s*([\d/]+)")
_CLASS_RE = re.compile(r"^\s*(\S+ - \d+)\s+(.*?)\s*(?:\(Last Updated.*)?$")

# Verified against Lakota's HAC, September 2026.
_CHOOSER = ".sg-banner-chooser"          # banner element that opens the student dialog
_PICKER_ROW = ".sg-student-picker-row"   # one row per student inside #StudentPicker
_PICKER_NAME = ".sg-picker-student-name" # just the name, without "Building: NN Grade: NN"
_BANNER_NAME = "span.sg-banner-text, .sg-banner-chooser, #sg-student-name"
_LEGACY_IFRAME = "sg-legacy-iframe"      # Classwork renders inside this frame


class HAC:
    def __init__(self, page: Page, settings: Settings):
        self.page = page
        self.s = settings

    # ---- student switching ----------------------------------------------
    def current_student(self) -> str:
        el = self.page.locator(_BANNER_NAME).first
        try:
            return " ".join(el.inner_text(timeout=3000).split())
        except PWTimeout:
            return ""

    def _open_picker(self) -> bool:
        """Open the student dialog. There is no button labelled "Change" -- the banner
        element showing the current student's name is itself the control."""
        try:
            self.page.locator(_CHOOSER).first.click(timeout=5000)
            self.page.wait_for_selector(_PICKER_ROW, timeout=8000)
            return True
        except PWTimeout:
            return False

    def _close_picker(self) -> None:
        for label in ("Cancel", "Close"):
            b = self.page.get_by_role("button", name=label, exact=True).first
            try:
                if b.is_visible(timeout=1000):
                    b.click()
                    self.page.wait_for_timeout(400)
                    return
            except Exception:
                continue
        self.page.keyboard.press("Escape")

    def students(self) -> list[str]:
        """Every student on the account, from the picker dialog."""
        self.page.goto(self.s.hac_base + "/Home/WeekView", wait_until="domcontentloaded")
        if not self._open_picker():
            cur = self.current_student()
            return [cur] if cur else []          # single-student account
        names = []
        for el in self.page.locator(_PICKER_NAME).all():
            n = " ".join(el.inner_text().split())
            if n and n not in names:
                names.append(n)
        self._close_picker()
        if not names:
            cur = self.current_student()
            return [cur] if cur else []
        return names

    def select_student(self, name: str) -> None:
        self.page.goto(self.s.hac_base + "/Home/WeekView", wait_until="domcontentloaded")
        if _same_student(name, self.current_student()):
            return
        if not self._open_picker():
            raise RuntimeError(f"Could not open the HAC student picker to select {name!r}")
        row = self.page.locator(_PICKER_ROW).filter(has_text=name).first
        if not row.count():
            self._close_picker()
            raise RuntimeError(f"No HAC picker row for {name!r}; available: {self.students()}")
        # Click the <label>: the row div is not clickable, and checking the radio alone does
        # nothing -- #StudentPicker is a POST form that only commits via its Submit button.
        row.locator("label").first.click()
        self.page.get_by_role("button", name="Submit", exact=True).first.click()
        self.page.wait_for_load_state("domcontentloaded")
        self.page.wait_for_timeout(1200)
        if not _same_student(name, self.current_student()):
            raise RuntimeError(f"Could not switch HAC to student {name!r} (showing {self.current_student()!r})")

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

    def _classwork_frame(self, timeout_s: float = 40.0):
        """Return the frame that actually holds the class blocks.

        Classwork renders inside an iframe named sg-legacy-iframe. The original code scanned
        page.frames once, immediately after domcontentloaded -- at that instant the iframe
        element exists but its document has not rendered, so every frame reported zero
        .AssignmentClass nodes, the scan fell through to main_frame, and the caller then
        waited 20s for a selector that was never going to appear there. Poll instead.
        """
        self.page.goto(self.s.hac_base + "/Classes/Classwork", wait_until="domcontentloaded")
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            frames = sorted(self.page.frames, key=lambda f: f.name != _LEGACY_IFRAME)
            for f in frames:
                try:
                    if f.locator(".AssignmentClass").count():
                        return f
                except Exception:
                    continue
            self.page.wait_for_timeout(500)
        log.warning("No frame exposed .AssignmentClass within %ss; falling back to the main frame", timeout_s)
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


def _same_student(target: str, current: str) -> bool:
    """HAC banner and picker both render "First Last"; tolerate either being a subset."""
    t, c = " ".join((target or "").lower().split()), " ".join((current or "").lower().split())
    return bool(t and c and (t in c or c in t))


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
