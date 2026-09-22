# Age-appropriate UI (design)

Date: 2026-09-22. Asked for by the maintainer: *"how can we make the most important
interfaces more usable/simpler for kids. target UI complexity/look&feel/colors/etc. based on
child grade."*

## 1. The problem

The app was built for a parent and grew a surface a child now sits in front of — the
check-in workspace, the plan, the Open work page, the kid page. All of them render the same
way for every reader. The household's three kids are in **5th, 7th and 9th grade**:
elementary, middle and high school, one each. One interface cannot be right for all three.

The specific failure is not decoration. A fifth grader reading `past credit`, `disagree` and
`9/26 7:20am` is reading vocabulary built for an adult who already holds the model. The
words are accurate and the page is unusable.

## 2. What this is, and what it is not

**Same information, same controls, different presentation.** Every tier shows every row and
offers every action. Grade changes type size, density, colour and wording — a skin and a
vocabulary, not a different app.

It is **not** progressive disclosure of features, and **not** a separate young-child screen.
Both were considered and rejected: two designs is two things to keep working forever, and
hiding rows from a child is the failure this project is least able to detect, because the
child would never report it.

### The constraint that governs the wording axis

This app's discipline is never to say more than the sources support. `docs/outcomes.md` is
the binding statement of it, and PR #19 removed a fabricated due hour on exactly these
grounds. Age-appropriate language therefore means **simpler true statements**, never
friendlier approximations.

| allowed | forbidden | why |
|---|---|---|
| `due tomorrow morning` | `finish by bedtime` | 7:20am is a fact; bedtime is invented |
| `Teacher hasn't got it` | `Oops, you forgot!` | `missing` is Canvas's flag, not a verdict on the child |
| `Ask your teacher` | `Something's wrong` | names the action; states no fault |

A phrase that adds a fact the sources did not give is a bug, at any tier.

## 3. Where grade lives

A new key in `[kids]`, beside the nicknames already there:

```toml
[kids]
nicknames = { Douglas = "Doug" }
grades    = { Douglas = 9, Melanie = 7, Kayla = 5 }
```

Parsed in `config.settings_from_doc` alongside `nicknames` (`config.py:308`) and with the
same shape tolerance: a value of the wrong shape keeps the default rather than raising,
because a `TypeError` escaping config parsing tracebacks out of `schedule remove --all`,
which the uninstaller runs hidden with its exit code discarded.

`Settings.grades: dict[str, int]`.

**Rejected: inferring grade from course names.** The signal is there —
`Math Plus 5th Gr`, `Adv Science 7`, `Honors English 9` — and it is unreliable. `Latin I`,
`Concert Band`, `STEAM` and `Design & Modeling` carry no marker, and a kid taking one
advanced class reads as older than they are. Silent wrongness in a setting nobody thinks to
check is worse than three values typed once a year. A parent editing `config.toml` by hand
is already the documented path for `[kids]`.

**No grade set means today's interface, byte for byte.** The feature is opt-in and additive;
an unset or unparseable grade yields the empty tier, which is the current stylesheet and the
current words. This is what makes it safe to ship: a household that never opens Settings
sees no change.

## 4. Tiers

One pure function, the only place the mapping lives:

```python
def tier(grade: int | None) -> str:
    """"early" (K-5), "middle" (6-8), "older" (9-12), or "" when no grade is set."""
```

| grade | tier | reader |
|---|---|---|
| unset, or unparseable | `""` | today's interface |
| K–5 | `early` | Kayla |
| 6–8 | `middle` | Melanie |
| 9–12 | `older` | Douglas |
| outside 0–12 | `""` | a typo must not silently pick a tier |

Three tiers rather than thirteen because school structure already clusters this way, the
difference between 6th and 7th grade is not real, and thirteen palettes is more than a
one-person project can keep good.

`older` and `""` render identically today. They are kept distinct because `older` is a
deliberate statement about a 9th grader and `""` is the absence of information; a later
change to the `older` tier must not silently alter every household that set no grade.

## 5. What varies

The tier is one attribute on `<body>`: `data-tier="early"`. Everything downstream is CSS
custom properties and a phrase table. No template forks on tier.

| axis | `early` (K–5) | `middle` (6–8) | `older` (9–12) |
|---|---|---|---|
| root type | 20px | 18px | 16px (today) |
| density | one card per row | roomy table | today's table |
| colour | high contrast, warm accent | today + stronger status | today |
| wording | short true statements | medium | full vocabulary |

`app.css` already defines its palette as tokens on `:root` (`--ink`, `--muted`, `--rule`,
`--paper`, `--wash`, `--accent`, `--warn`, `--ok`), so the colour and type axes are three
blocks redefining those under `:root[data-tier="early"]` and friends, plus one new
`--type-root`. No existing rule changes.

### Wording

| concept | `early` | `middle` | `older` |
|---|---|---|---|
| due `9/26 7:20am` | due tomorrow morning | due tomorrow 7:20am | 9/26 7:20am |
| `Missing` | Teacher hasn't got it | Marked missing | Missing |
| `Zero` | Marked 0 — ask about it | Scored 0 | Zero |
| `disagree` | Ask your teacher | Sources disagree | disagree |
| `past credit` | Too late to fix | Past the credit window | past credit |
| `one source` | Only one system lists it | Only HAC lists it | one source |
| `paper no grade` | Paper — hand it in | Paper, no grade yet | paper no grade |
| `actionable` | Can still fix | Still fixable | actionable |

Every `early` phrase is the same fact in fewer words. None adds a claim.

### Colour never carries meaning alone

A status that is red at `older` is red **and** a word at `early`. This is the accessibility
requirement and the age requirement at once: a young reader should not have to know that red
means late.

## 6. Mechanism

- `config.Settings.grades` — the new setting (§3).
- `web/tiers.py` — `tier(grade)`, and `for_student(settings, student_key)` returning the
  tier string for one child. Pure; no I/O.
- `web/app.py::page_context` — adds `tier`, resolved from the student the page is about.
  Pages with no single student resolve to `""`.
- `templates/base.html` — `<body data-tier="{{ tier }}">`.
- `static/app.css` — three `:root[data-tier=…]` blocks.
- `web/phrasing.py` — one table, `(concept, tier) -> str`, `older` being today's word.
  Two fallbacks, both to the current word rather than to a blank: a concept present in the
  table but with no entry for this tier yields its `older` entry, and a concept absent from
  the table yields the string it was given, unchanged. A word nobody has translated is shown
  as it is today; it is never dropped.
- A `phrase` Jinja filter, registered in `_filters` beside `nickname` and `trigger_words`.

Templates call `{{ v.status | phrase(tier) }}`. They never branch on tier. A vocabulary
expressed as `{% if tier == 'early' %}` scattered through fifteen templates is a parallel
implementation of the phrase table, which is the pattern this codebase explicitly rejects
and which reviews in this repo have already found three times.

### Scope

Pages a child reads: the kid page, Open work, check-in, plan and plan print.

The Dashboard is the family kiosk view and stays at `""`. Settings, Reports, Schedules,
Runs, Trends, Changes and Diagnostics are parent tools and stay at `""`. Tiering them would
mean maintaining three presentations of surfaces no child opens.

## 7. Testing

1. **`tier()`** — each band, the boundaries (5/6 and 8/9), `None`, a negative, 13, a
   non-integer.
2. **Config** — `grades` absent, not a table, a non-integer value, a grade for a key that is
   not a student. Each keeps the default; none raises.
3. **`page_context`** — the right tier for each of three students; `""` for a page with no
   student; `""` when the setting is absent.
4. **Phrasing** — a mapped concept in all three tiers; an unmapped concept falls back to the
   `older` word rather than a blank.
5. **CSS** — each `data-tier` block defines every token it overrides, and no block removes
   one (a half-defined tier is a page with inherited colours nobody designed).
6. **The parity test, which is the point:**

   > For each tier, every item row rendered for `older` is rendered for `early` too.

   Same fixture, same filters, three renders, same set of item ids. Different words, same
   facts. This is the structural guarantee that simplification cannot drift into
   concealment — the failure this feature is most exposed to and the one a child would never
   report.

7. **No fabricated facts** — every phrase in the table for a given concept is checked to
   contain no time, date or number that the `older` phrase does not. A phrase table is
   copy, and copy is where invented precision returns.

## 8. Out of scope

- **Per-grade tuning** (a different look for 6th and 7th). Three tiers, deliberately.
- **A child login or per-child device memory.** The app has no login by design; the tier
  follows the student whose page is open, not the person reading it.
- **Tiering the parent tools.** §6.
- **Inferring grade from course names.** §3 — recorded as rejected, with the reason, so it
  is not re-proposed as an obvious improvement.
- **Changing which rows a child sees.** §2. If a household wants a child to see less, that
  is a filter, and it belongs to the existing flag and filter model, not to grade.
