#!/usr/bin/env python3
"""Render the Fridge Sheet mark from its SVG into every raster the project ships.

    python3 scripts/render_mark.py

Writes, from fridgesheet/web/static/mark.svg:
  fridgesheet/web/static/favicon.svg          the same drawing (browsers take SVG directly)
  fridgesheet/web/static/mark-32.png, -180.png  header logo and the iOS home-screen icon
  packaging/windows/FridgeSheet.ico            the exe and installer icon (16..256 px)

Needs `rsvg-convert` (librsvg) on PATH and Pillow. The rendered files are committed; CI
does not run this, so run it whenever mark.svg changes and commit the results together.
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
PNG_SIZES = (32, 180)


def render_png(size: int, out: Path) -> None:
    subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size), "-o", str(out), str(SRC)], check=True)


def main() -> int:
    if not shutil.which("rsvg-convert"):
        print("rsvg-convert not found (install librsvg2-bin)", file=sys.stderr)
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
