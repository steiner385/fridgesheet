"""Render the mockups to PNG. Throwaway: `python shoot.py` from this folder with a venv that
has Playwright and Chromium."""
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PAGES = ("cards", "assignments", "plan")

with sync_playwright() as p:
    browser = p.chromium.launch()
    desktop = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    phone = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    for name in PAGES:
        url = (HERE / f"{name}.html").as_uri()
        for ctx, suffix in ((desktop, "desktop"), (phone, "phone")):
            page = ctx.new_page()
            page.goto(url)
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(HERE / f"{name}-{suffix}.png"), full_page=True)
            page.close()
    browser.close()
print("done")
