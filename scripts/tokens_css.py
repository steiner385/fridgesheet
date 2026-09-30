"""Write the token lines of app.css from fridgesheet/tokens.py.

    python scripts/tokens_css.py            # rewrite the :root and [data-tier] lines in place
    python scripts/tokens_css.py --check    # exit 1 if the stylesheet is out of date

The stylesheet has no build step; these four lines are the one part of it that is generated,
and tests/test_tokens.py holds them equal to the source. Run from the repository root.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fridgesheet import tokens  # noqa: E402

CSS = ROOT / "fridgesheet" / "web" / "static" / "app.css"
PATTERNS = {
    ":root": re.compile(r"^:root \{.*\}$", re.M),
    **{tier: re.compile(r'^\[data-tier="%s"\]\s*\{.*\}$' % tier, re.M) for tier in tokens.TIERS},
}


def rewrite(text: str) -> str:
    for key, line in tokens.css_lines().items():
        text, n = PATTERNS[key].subn(lambda _m, line=line: line, text, count=1)
        if n != 1:
            raise SystemExit(f"app.css has no {key} token line to rewrite")
    return text


def main(argv: list[str]) -> int:
    before = CSS.read_text(encoding="utf-8")
    after = rewrite(before)
    if "--check" in argv:
        if after != before:
            print("app.css token lines differ from fridgesheet/tokens.py; run scripts/tokens_css.py")
            return 1
        print("app.css token lines match fridgesheet/tokens.py")
        return 0
    if after != before:
        CSS.write_text(after, encoding="utf-8")
        print("rewrote the token lines of app.css")
    else:
        print("app.css already matches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
