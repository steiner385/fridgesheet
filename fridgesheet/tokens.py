"""One token source for the screen and the paper.

DESIGN.md records the design system (The Student Planner); this module is where its values
live for code. Three things read it and nothing else may carry a colour or a type size of
its own:

- `web/static/app.css`: the `:root` line and the three `[data-tier="…"]` lines are generated
  from `ROOT` and `TIERS` by `scripts/tokens_css.py` (run it after changing a value here;
  `tests/test_tokens.py` fails until the CSS matches). Everything else in the stylesheet reads
  those custom properties.
- `sheet.py`: the printed sheet's status colours, rules and type ramp (`PRINT`).
- `web/charts.py`: the chart series and outcome strokes (`CHART`).

Two layers. `COLORS` is the palette by its pen-and-stamp name, one value each. `ROOT` maps
the page's roles (`--ink`, `--accent`, `--hl-due` …) onto that palette plus the type and
spacing scale; `TIERS` says what a reading tier moves. A tier redefines every token in
`TIER_TOKENS` whether or not its value differs (the Whole-Tier Rule), so no page inherits
a colour nobody designed for that tier.
"""
from __future__ import annotations

#: The palette by name (DESIGN.md, Colors). The screen's LATE word and its checkbox use the
#: darker Amber Pencil Ink (5.2:1 on Highlighter Amber, the pair the word is read in; the
#: re-critique of 2026-09-30 found the earlier #9a5b00 at 4.40:1 there); the lighter Amber
#: Pencil is a chart stroke only.
COLORS: dict[str, str] = {
    "ballpoint-blue": "#1f5fa8",
    "red-pen": "#b3261e",
    "checkmark-green": "#2e7d32",
    "amber-pencil": "#b8860b",
    "amber-pencil-ink": "#8a5200",
    "purple-stamp": "#6b3fa0",
    "teal-pencil": "#00707f",        # the sixth chart series
    "brown-pencil": "#8a6d3b",       # the "unknown" outcome on a chart
    "ink": "#1c1c1c",
    "pencil-grey": "#595959",
    "stroke-grey": "#8a8a8a",
    "ruled-grey": "#c9d3dd",
    "day-box-blue-grey": "#8fa3b8",
    "paper-white": "#ffffff",
    "planner-white": "#fffdf6",
    "red-pen-wash": "#fdecea",
    "highlighter-yellow": "#fff1a8",
    "highlighter-red": "#ffd9d4",
    "highlighter-purple": "#ead9ff",
    "highlighter-amber": "#ffe4b8",
}

#: The page's roles (the CSS custom properties, without the `--`), in the order the
#: stylesheet declares them. Colours first, then the type scale, then layout and spacing.
ROOT: dict[str, str] = {
    "ink": COLORS["ink"],
    "muted": COLORS["pencil-grey"],
    "control": COLORS["stroke-grey"],
    "rule": COLORS["ruled-grey"],
    "box": COLORS["day-box-blue-grey"],
    "paper": COLORS["paper-white"],
    "wash": COLORS["planner-white"],
    "accent": COLORS["ballpoint-blue"],
    "warn": COLORS["red-pen"],
    "ok": COLORS["checkmark-green"],
    "late": COLORS["amber-pencil-ink"],
    "check": COLORS["purple-stamp"],
    "warn-wash": COLORS["red-pen-wash"],
    "hl-due": COLORS["highlighter-yellow"],
    "hl-red": COLORS["highlighter-red"],
    "hl-check": COLORS["highlighter-purple"],
    "hl-late": COLORS["highlighter-amber"],
    "type-root": "16px",
    "type-small": "13px",
    "type-tiny": "12px",
    "page-max": "1600px",
    "measure": "760px",
    "rail": "220px",
    "pad": "24px",
    "radius": "8px",
    "s1": "4px",
    "s2": "8px",
    "s3": "12px",
    "s4": "16px",
    "s5": "24px",
    "s6": "32px",
}

#: Which palette name each colour role wears at the root, so a document can name a role's
#: colour ("Pencil Grey") and a test can hold DESIGN.md's tier variants to `TIERS`.
ROLE_OF: dict[str, str] = {
    "ink": "ink", "pencil-grey": "muted", "stroke-grey": "control", "ruled-grey": "rule",
    "day-box-blue-grey": "box", "paper-white": "paper", "planner-white": "wash",
    "ballpoint-blue": "accent", "red-pen": "warn", "checkmark-green": "ok",
    "amber-pencil-ink": "late", "purple-stamp": "check", "red-pen-wash": "warn-wash",
    "highlighter-yellow": "hl-due", "highlighter-red": "hl-red", "highlighter-purple": "hl-check",
    "highlighter-amber": "hl-late",
}

#: Every token a reading tier redefines (web/tiers.py): the colours and the three type sizes.
#: Layout and spacing never move with a tier.
TIER_TOKENS: tuple[str, ...] = (
    "ink", "muted", "rule", "box", "paper", "wash", "accent", "warn", "ok", "late", "check", "warn-wash",
    "hl-due", "hl-red", "hl-check", "hl-late", "type-root", "type-small", "type-tiny",
)

#: What each tier changes from the root. `older` is what ships at the root, kept as its own
#: tier so a later change to one leaves the households that set no grade alone. The younger
#: tiers are a touch warmer and higher in contrast, with larger type; the highlighter fills
#: are the same at every tier.
TIERS: dict[str, dict[str, str]] = {
    "early": {
        "ink": "#10151b", "muted": "#4a5568", "rule": "#b9c6d4", "box": "#7f95ad", "wash": "#fffaee",
        "accent": "#0b5cab", "warn": "#a3170f", "ok": "#1d6b27", "late": "#8a5200", "check": "#5f3594",
        "type-root": "20px", "type-small": "16px", "type-tiny": "14px",
    },
    "middle": {
        "ink": "#161b22", "muted": "#5a6474", "rule": "#ccd5de", "box": "#8aa0b5", "wash": "#fffcf4",
        "accent": "#14539b", "warn": "#a81d14", "ok": "#24702c", "late": "#915600", "check": "#653a9a",
        "type-root": "18px", "type-small": "15px", "type-tiny": "13px",
    },
    "older": {},
}


def tier_tokens(tier: str) -> dict[str, str]:
    """Every tier token with the value this tier gives it, the root's where it says nothing."""
    moved = TIERS[tier]
    return {name: moved.get(name, ROOT[name]) for name in TIER_TOKENS}


def css_lines() -> dict[str, str]:
    """The four generated lines of app.css, keyed ":root", "early", "middle", "older"."""
    def line(selector: str, values: dict[str, str]) -> str:
        return f"{selector} {{ " + " ".join(f"--{k}: {v};" for k, v in values.items()) + " }"
    out = {":root": line(":root", ROOT)}
    for tier in TIERS:
        out[tier] = line(f'[data-tier="{tier}"]', tier_tokens(tier))
    return out


#: The printed sheet (sheet.py, reportlab, points): the type ramp as (size, leading), and the
#: colours its words and rules are drawn in, by the same roles as the page.
PRINT: dict[str, object] = {
    "h1": (16, 19),
    "group": (11, 13),
    "cell": (10, 12),
    "small": (8.5, 10.5),
    "tiny": (8, 9.5),
    "footer": 7,
    "ink": ROOT["ink"],
    "muted": ROOT["muted"],
    "rule": ROOT["rule"],
    "warn": ROOT["warn"],
    "late": ROOT["late"],
    "accent": ROOT["accent"],
    "ok": ROOT["ok"],
    "check": ROOT["check"],
}

#: Charts (web/charts.py, Chart.js): the series strokes by position, and the outcome strokes
#: (docs/outcomes.md). Late is the lighter Amber Pencil here, a stroke rather than a word.
CHART: dict[str, object] = {
    "series": (COLORS["ballpoint-blue"], COLORS["red-pen"], COLORS["checkmark-green"], COLORS["purple-stamp"],
               COLORS["amber-pencil"], COLORS["teal-pencil"]),
    "outcomes": {"on_time": COLORS["checkmark-green"], "late": COLORS["amber-pencil"], "not_done": COLORS["red-pen"],
                 "done_offline": COLORS["ballpoint-blue"], "unknown": COLORS["brown-pencil"]},
}
