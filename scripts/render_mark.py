#!/usr/bin/env python3
"""Render the Fridge Sheet mark from its SVG into every raster the project ships.

    python3 scripts/render_mark.py

Writes, from fridgesheet/web/static/mark.svg:
  fridgesheet/web/static/favicon.svg          the same drawing (browsers take SVG directly)
  fridgesheet/web/static/mark-32.png, -180.png  header logo and the iOS home-screen icon
  fridgesheet/web/static/mark-192.png, -512.png the web app manifest's icons (Chrome's
                                                install prompt needs both sizes)
  packaging/windows/FridgeSheet.ico            the exe and installer icon (16..256 px)

Needs Pillow, and `rsvg-convert` (librsvg) on PATH -- or, without it, the Playwright
Chromium the app already installs, which draws the SVG in a page and screenshots it. The
rendered files are committed; CI does not run this, so run it whenever mark.svg changes and
commit the results together.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "fridgesheet" / "web" / "static" / "mark.svg"
STATIC = SRC.parent
ICO = ROOT / "packaging" / "windows" / "FridgeSheet.ico"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
PNG_SIZES = (32, 180, 192, 512)


def render_png(size: int, out: Path) -> None:
    if shutil.which("rsvg-convert"):
        subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size), "-o", str(out), str(SRC)], check=True)
        return
    render_png_with_chromium(size, out)


def render_png_with_chromium(size: int, out: Path) -> None:
    """The fallback: the SVG as an <img> of exactly `size` on a transparent page, screenshot
    at device scale 1, so the PNG is the drawing and nothing else."""
    from urllib.parse import quote
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": size, "height": size}, device_scale_factor=1)
        page.set_content(f'<html><body style="margin:0"><img src="data:image/svg+xml;utf8,{quote(SRC.read_text(encoding="utf-8"))}" '
                         f'width="{size}" height="{size}" style="display:block"></body></html>')
        page.screenshot(path=str(out), omit_background=True)
        browser.close()


def main() -> int:
    if not shutil.which("rsvg-convert"):
        try:
            import playwright.sync_api  # noqa: F401
        except ImportError:
            print("rsvg-convert not found (install librsvg2-bin), and no Playwright to fall back on", file=sys.stderr)
            return 1
    from PIL import Image
    shutil.copyfile(SRC, STATIC / "favicon.svg")
    for size in PNG_SIZES:
        render_png(size, STATIC / f"mark-{size}.png")
    frames = []
    tmp = ROOT / "build" / "mark"
    tmp.mkdir(parents=True, exist_ok=True)
    for size in ICO_SIZES:
        p = tmp / f"{size}.png"
        render_png(size, p)
        frames.append(Image.open(p).convert("RGBA"))
    # Pillow writes every frame from the first image's `append_images`; sizes tells it which.
    frames[-1].save(ICO, format="ICO", sizes=[(s, s) for s in ICO_SIZES], append_images=frames[:-1])
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"wrote favicon.svg, {', '.join(f'mark-{s}.png' for s in PNG_SIZES)}, {ICO.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
