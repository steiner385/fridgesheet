# Web app E: docs, the QR code, and the polish that makes this giveable

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the app's own documentation true again after Plan D part 2 moved the
schedule controls, finish the one spec'd feature still missing (the phone QR code), clear
the deferrals worth clearing, and leave a checklist Tony can actually run on a Windows PC
before tagging a release.

**Architecture:** Mostly prose and one small module. `docs/windows.md` and `README.md` are
the two surfaces a stranger reads first and both now describe a Settings page that no longer
has the controls they name. `fridgesheet/qr.py` is a new pure function — URL in, SVG
string out — with no image library and no network, rendered inline next to the LAN URL the
Settings page already computes. The release checklist is a document, not an action: the
manual checks and the tag are Tony's to perform.

**Tech Stack:** Python 3.12, FastAPI + Jinja2 + htmx (no build step), `segno` for QR
encoding (see Decision 1), pytest.

**Spec:** `docs/superpowers/specs/2026-09-15-fridgesheet-web-app-design.md` — sections 8 (access
and security, which is where the QR code is specified), 11 (packaging, the friend,
compatibility), 13 (plan E).

**Issues closed:** #28 (windows.md), #29 (README, cross-references, deferred polish),
#30 (real-PC checklist and the release — the checklist half; the tag stays Tony's).

## Global Constraints

- Python 3.12. One new runtime dependency is permitted by Decision 1 and no others.
- **No JavaScript test harness exists in this repo.** Add no client-side logic that would
  need one. The QR code is rendered server-side as inline SVG.
- **Never run a real `systemctl` or `schtasks`; never write into `~/.config/systemd/user`;
  never touch `~/.fridgesheet` beyond reading metadata with `stat`.** The machine has the
  owner's live units, which print a real household's school work every weekday at 2 PM.
  `tests/conftest.py`'s `_no_real_scheduler` fixture now enforces the first of these — do
  not weaken, bypass or "simplify" it, and do not reach for a real command to prove a point.
- **Never tag a release, and never run the manual Windows checks.** Task 5 writes the
  checklist; a human runs it.
- The app talks only to OneLogin, Canvas and HAC. The QR encoder must be offline —
  no remote chart or image service, ever, for a URL that names the household's LAN.
- `tests/test_packaging.py::test_windows_page_exists_and_names_the_limitations` asserts a
  list of phrases appear in `docs/windows.md`. Extend it; do not weaken it.
- The test command is
  `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest -q`.
  Baseline is **546 passing**.
- Commit messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

---

## Decisions this plan makes

**Decision 1 — the QR code uses `segno`, a new runtime dependency.**
The alternatives were vendoring a pure-Python encoder next to `htmx.min.js` in `VENDOR.md`,
or writing one. A QR encoder is Reed-Solomon error correction plus a bit-placement
specification; it is about 250 lines to write correctly and it is the kind of code that is
wrong in ways tests written by its own author do not catch. `segno` 1.6.6 is a pure-Python
wheel (`py3-none-any`) that emits SVG directly, so PyInstaller bundles it without a hook and
the "no build step" rule is untouched. The project already carries ten runtime dependencies
including reportlab and playwright; one more pure-Python one is not a change in character.

Verified against the published wheel rather than taken on trust: its only `Requires-Dist` is
`importlib-metadata; python_version < "3.10"`, so on this project's floor it has **no
dependencies at all**; and it is **BSD-3-Clause** (Copyright 2016-2025 Lars Heuer), not MIT
as first assumed. That matters beyond pedantry — `docs/windows.md` has a "Credits and
licences" section naming every bundled component's licence, and Task 3 must add segno to it
with the right one.

**This is the decision in this plan most worth a second opinion, so flag it to Tony before
Task 3 rather than after.** If he would rather not add a dependency, the task becomes
"vendor `qrcodegen.py` (Project Nayuki, MIT, single file) under `fridgesheet/_vendor/`
and add it to `VENDOR.md` with a SHA-256 pin" — same public interface, same tests, one extra
file to keep.

**Decision 2 — the release checklist is a document, not a task an agent performs.**
Issue #30 says "manual checks on a real Windows PC as a standard user with a real printer;
then tag v0.3.0." No agent can do either half honestly. Task 5 writes
`docs/release-checklist.md` with every check spelled out so it can be worked through by
hand, and the plan stops there.

**Decision 3 — the deferrals are triaged, not swept in.**
Issues #31–#36 hold roughly thirty items. Task 4 fixes the ones that are user-visible or
cheap-and-adjacent, and explicitly leaves the rest, each with a reason. A plan that promised
to clear six issues would be a plan that ran out of budget in the middle of one.

---

## File structure

**Created:**
- `fridgesheet/qr.py` — one public function, URL to inline SVG. No I/O, no network.
- `docs/release-checklist.md` — what a human does on a real Windows PC before a tag.
- `tests/test_qr.py`

**Modified:**
- `docs/windows.md` — the schedule paragraphs, which Plan D part 2 made false.
- `README.md` — sections 5, 6 and "The browser app".
- `fridgesheet/web/routes/settings.py` and `templates/settings.html` — render the QR.
- `tests/test_packaging.py` — extend the phrase list.
- `tests/test_web_settings_page.py` — the QR renders only when the LAN toggle is on.
- Whatever Task 4's triage selects.

---

### Task 1: `docs/windows.md` stops describing controls that no longer exist

Plan D part 2 removed the "Print the sheet automatically on school days" checkbox and the
"Print time" field from the Settings page and moved schedules to a new `/schedules` page.
This page still tells a first-time reader to tick that box. It is the single most-read
document in the project and it is currently wrong in the one step that decides whether the
app ever prints anything.

**Files:**
- Modify: `docs/windows.md`
- Test: `tests/test_packaging.py:113-118`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing code-level.

- [ ] **Step 1: Read the page against the app**

Read `docs/windows.md` end to end, then read `fridgesheet/web/templates/settings.html`
and `fridgesheet/web/templates/schedules.html`. Write down every sentence in the page
that names a control, and mark it present or absent. At minimum these are wrong today:

- "First run" step 1 ends `Tick **Print the sheet automatically on school days**, then
  **Save**; once a login has passed, saving installs the scheduled task.` — that checkbox
  and that print-time field are gone from Settings.
- The same step tells the reader to pick "the print time" on Settings. Also gone.
- Nothing in the page mentions the **Schedules** page, which is now where both live, nor
  that a schedule can name its own printer or be PDF-only.
- "If something goes wrong" names the task `"Fridge Sheet - open-work"`. Still correct for
  the built-in report, but a saved view report's task is named `Fridge Sheet - view 7`, and
  a reader looking for a schedule they made will not find it under the old name.

- [ ] **Step 2: Write the failing test**

Extend the existing phrase list in `tests/test_packaging.py` rather than adding a new test —
it is the established way this page is pinned:

```python
def test_windows_page_exists_and_names_the_limitations():
    page = (ROOT / "docs" / "windows.md").read_text(encoding="utf-8")
    for phrase in ("SmartScreen", "More info", "Run anyway", "multi-factor", "logged in", "%LOCALAPPDATA%\\fridgesheet",
                   "Test login", "Print now", "no-print-days.txt", "late-rules.toml", "doctor.txt", "Task Scheduler", "Uninstall",
                   "Schedules", "PDF only"):
        assert phrase in page, phrase
    # The Settings page lost these two controls in Plan D part 2; a page that still tells a
    # parent to tick a checkbox that is not there is worse than one that says nothing.
    assert "Print the sheet automatically on school days" not in page
```

- [ ] **Step 3: Run it to verify it fails**

Run: `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest tests/test_packaging.py -q`
Expected: FAIL — `assert "Schedules" in page` (the page has no such word), and the negative
assertion fails too because the stale sentence is still there.

- [ ] **Step 4: Rewrite the affected passages**

Rewrite "First run" step 1 so it stops at Settings-page business (username, password,
printer, days ahead, nicknames, Save), and add a new numbered step for the Schedules page
covering: choosing a report, ticking days, setting a time, choosing a printer or leaving it
at the shared one, and the PDF-only option for a report you want built but not printed. Say
plainly that saving there is what installs the Windows task.

Keep the page's existing voice: second person, short sentences, no jargon, and every claim
concrete enough to check. It is written for a parent, not a developer — match that. Do not
restructure sections that are still accurate.

Also correct the Task Scheduler paragraph so a reader can find a task for a report they
built themselves, and mention that turning a schedule off on the Schedules page removes it.

- [ ] **Step 5: Run the test and the suite**

Run: `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest -q`
Expected: 546 passing, with `test_windows_page_exists_and_names_the_limitations` now green.

- [ ] **Step 6: Commit**

```bash
git add docs/windows.md tests/test_packaging.py
git commit -m "docs.windows: the Settings page no longer holds the schedule

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: the README describes the app that exists

`README.md` section 5 tells a reader to copy systemd units by hand and run `systemctl --user
enable`; section 6 describes `print-sheet` and a hand-written timer as the way the sheet gets
printed. The app now writes its own timers, from a page, for any report. The "The browser
app" paragraph predates the Changes, Trends, Reports and Schedules pages.

**Files:**
- Modify: `README.md:93-130` (sections 5 and 6), `README.md:183-186` ("The browser app")
- Test: none — no test asserts README content, and adding one to pin prose would pin the
  wrong thing. Correctness here is a reviewer's judgement against the running app.

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

- [ ] **Step 1: Establish what is actually true**

Run the app's own help and page list against a scratch home — never the real one:

```bash
env -u PYTHONPATH FRIDGESHEET_HOME=/tmp/fridgesheet-plan-e \
  ~/fridgesheet/.venv/bin/python -m fridgesheet.cli --help
env -u PYTHONPATH FRIDGESHEET_HOME=/tmp/fridgesheet-plan-e \
  ~/fridgesheet/.venv/bin/python -m fridgesheet.cli schedule --help
```

and read `fridgesheet/web/templates/base.html` for the real navigation list. Write the
README from what those say, not from what the old README says.

- [ ] **Step 2: Rewrite section 5**

`systemd/fridgesheet-refresh.{service,timer}` in the repo are still the right way to
pre-fetch, and Tony runs them — keep that. But add that report *printing* schedules are no
longer installed by hand: `fridgesheet schedule install <key>` or the Schedules page writes
`fridgesheet-<key>.{service,timer}` and enables them, and the app refuses to touch a unit it did
not write (it marks its own with a comment line on the first line). A reader with existing
hand-written units needs to know both that they are safe and that the app will not manage
them.

- [ ] **Step 3: Rewrite section 6**

Keep `print-sheet` documented — it still exists and Tony's live unit calls it — but lead with
`fridgesheet run <key>`, which is what a schedule executes and what supports any report.
Cover: a report key is `open-work` or `view:<id>`; `fridgesheet reports` lists them with
their schedule and whether they are PDF-only; `--printer` beats the report's own printer
which beats `[print].printer`.

- [ ] **Step 4: Rewrite "The browser app"**

List the pages that exist now — Dashboard, per-kid, Reconcile, Reports, Schedules, Changes,
Trends, Runs, Settings, Diagnostics — one clause each, and say what the Schedules page is
for. Keep it to a paragraph or two; the README is a developer's orientation, and
`docs/windows.md` is where a parent goes.

- [ ] **Step 5: Check every command you wrote actually runs**

For each command in the sections you touched, run it against the scratch home with `--help`
or a read-only subcommand and confirm it exists and spells its flags the way you wrote them.
**Do not run `schedule install`, `schedule remove`, or anything that prints.** Paste what you
ran into your report.

- [ ] **Step 6: Run the suite and commit**

```bash
env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest -q
git add README.md
git commit -m "README: the app writes its own timers, and has pages the README never named

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: the phone QR code

Spec section 8: the "Allow other devices on this network" toggle "rebinds to `0.0.0.0` and
shows the LAN URL **and a QR code for a phone**." The LAN URL half has existed since Plan B
(`actions.lan_url`); the QR code has never been built. It is the last unimplemented sentence
in the spec.

**Before starting this task, confirm Decision 1 with Tony** — it adds a runtime dependency.
The fallback (vendoring a single MIT file) is spelled out in the Decisions section and has
the same public interface, so only Step 3 changes if he prefers it.

**Files:**
- Create: `fridgesheet/qr.py`, `tests/test_qr.py`
- Modify: `pyproject.toml` (dependencies), `fridgesheet/web/routes/settings.py`,
  `fridgesheet/web/templates/settings.html`, `docs/windows.md` ("Credits and licences" —
  segno is **BSD-3-Clause**, Copyright 2016-2025 Lars Heuer; that section names the licence
  of every bundled component and a newly bundled one belongs in it)
- Test: `tests/test_qr.py`, `tests/test_web_settings_page.py`

**Interfaces:**
- Consumes: `actions.lan_url(port) -> str | None` (already exists,
  `fridgesheet/web/actions.py:348`).
- Produces: `qr.svg(text: str, *, size_px: int = 160) -> str` — a complete, standalone
  `<svg>` element as a string, safe to drop inline into a page.

- [ ] **Step 1: Write the failing test**

Create `tests/test_qr.py`:

```python
"""The QR code the Settings page shows when the LAN toggle is on.

Rendered server-side as inline SVG: there is no JavaScript test harness in this repo, and a
URL naming the household's LAN must never be sent to a remote chart service to be drawn.

`ElementTree.fromstring` below parses only what `qr.svg` just produced, one line earlier, to
assert it is well-formed -- it is never fed untrusted input, so the XXE and entity-expansion
hazards that make `defusedxml` the right default elsewhere do not apply, and adding a test
dependency for a threat model this test does not have would be noise. If this file ever
parses XML from anywhere else, that stops being true.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest

from fridgesheet import qr


def test_svg_is_a_standalone_element_a_page_can_inline():
    out = qr.svg("http://192.168.1.42:8433/")
    assert out.startswith("<svg") and out.rstrip().endswith("</svg>")
    ET.fromstring(out)                       # parses as XML, so a template can inline it safely
    assert "<script" not in out.lower()


def test_the_svg_scales_to_the_size_asked_for():
    small, large = qr.svg("http://192.168.1.42:8433/", size_px=80), qr.svg("http://192.168.1.42:8433/", size_px=320)
    assert 'width="80"' in small and 'height="80"' in small
    assert 'width="320"' in large and 'height="320"' in large


def test_different_urls_make_different_codes():
    """A cached or hard-coded image would pass every other test in this file."""
    a = qr.svg("http://192.168.1.42:8433/")
    b = qr.svg("http://192.168.1.99:8433/")
    assert a != b


def test_a_long_url_still_encodes():
    """The LAN URL is short, but nothing stops a future caller passing something longer, and
    silently truncating a QR code produces one that scans to the wrong address."""
    out = qr.svg("http://" + "a" * 200 + ".example.org:8433/some/deep/path")
    ET.fromstring(out)


def test_empty_text_is_refused_rather_than_drawn():
    """A blank QR is a code that scans to nothing; the caller has a bug and should hear about it."""
    with pytest.raises(ValueError):
        qr.svg("")


def test_nothing_in_the_svg_reaches_the_network():
    out = qr.svg("http://192.168.1.42:8433/")
    assert not re.search(r"https?://(?!www\.w3\.org)", out), "the SVG must not reference a remote resource"
```

The `www.w3.org` exception in the last test is the SVG namespace declaration, which is an
identifier and not a fetch.

- [ ] **Step 2: Run it to verify it fails**

Run: `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest tests/test_qr.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fridgesheet.qr'`.

- [ ] **Step 3: Implement**

Add to `pyproject.toml`'s `dependencies`, keeping the list alphabetical:

```toml
    "segno>=1.6",
```

Install it into the venv the tests use before continuing.

Create `fridgesheet/qr.py`:

```python
# fridgesheet/qr.py
"""A QR code as inline SVG, for the LAN address a phone needs.

Server-side and offline on purpose. The text encoded here is the address of the household's
own machine on its own network; handing that to a remote chart service to be drawn would put
it somewhere the spec promises nothing goes (section 8: the server talks only to OneLogin,
Canvas and HAC). Inline SVG also means no image file to write, serve or clean up, and no
client-side code -- this repo has no JavaScript test harness.
"""
from __future__ import annotations

import io

import segno


def svg(text: str, *, size_px: int = 160) -> str:
    """`text` as a QR code: a complete `<svg>` element, sized `size_px` square.

    Raises `ValueError` on empty text -- a blank code scans to nothing, which is a caller's
    bug worth hearing about rather than a blank square on a page.
    """
    if not text:
        raise ValueError("a QR code needs something to encode")
    buf = io.StringIO()
    segno.make(text, error="m").save(
        buf, kind="svg", xmldecl=False, svgns=True, omitsize=False,
        unit="", scale=1, border=2, svgclass=None, lineclass=None,
    )
    out = buf.getvalue()
    # segno sizes the element in modules; the page wants a fixed pixel box that scales with
    # the module count rather than against it, so the viewBox does the scaling.
    return out.replace("<svg", f'<svg width="{size_px}" height="{size_px}"', 1)
```

**Implementer's note:** `segno`'s `save(kind="svg")` keyword set varies across versions and
the exact call above may need adjusting — the contract that matters is the one the tests
assert, not this snippet. If `omitsize`/`unit`/`svgclass` are not accepted by the installed
version, read `segno`'s own docstring and produce an element that satisfies the tests:
standalone `<svg>`, carrying literal `width="<size_px>"` and `height="<size_px>"`, a
`viewBox` so it scales, no `<script>`, and no remote reference. Say in your report what you
actually called and why.

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest tests/test_qr.py -q`
Expected: PASS, 6 tests.

Then eyeball it once — a QR code that parses as XML but does not scan is a passing test suite
and a broken feature:

```bash
env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -c \
  "from fridgesheet import qr; open('/tmp/qr.svg','w').write(qr.svg('http://192.168.1.42:8433/'))"
```

Open `/tmp/qr.svg` and scan it with a phone. Report what the phone resolved it to. If you
cannot scan it, say so plainly rather than claiming it works.

- [ ] **Step 5: Render it on the Settings page**

`templates/settings.html:22-23` already shows the LAN URL when `lan_url` is set. Put the QR
beside it. The route computes the SVG — templates in this codebase stay presentational:

In `fridgesheet/web/routes/settings.py`'s `_page()`, alongside the existing
`lan_url=actions.lan_url(form.port) if form.allow_lan else None`, add a `lan_qr` computed
from that same URL when it is not `None`, and pass it to the template. Guard it: a QR
failure must not take the Settings page down with it, since the page is where a parent fixes
everything else. Log and fall back to `None`, the way `printer_names` already degrades.

In the template, render it inside the existing `{% if lan_url %}` block. Jinja autoescaping
is on (`app.py`), so an SVG string interpolated normally will be escaped into visible markup
— mark it safe explicitly, and put a one-line comment saying why that is sound here (the
string is generated by `qr.svg` from a URL the server computed, never from user input).

- [ ] **Step 6: Test the page**

Add to `tests/test_web_settings_page.py`:

```python
def test_the_lan_toggle_shows_a_qr_code_for_the_phone(tmp_path):
    """Spec section 8: the toggle shows the LAN URL *and* a QR code. A parent standing in the
    kitchen should not have to type an IP address into a phone."""
    c, _ = _client(tmp_path)
    body = c.post("/settings", data={**FORM, "password": "pw", "allow_lan": "on"}).text
    assert "<svg" in body and "</svg>" in body
    assert "&lt;svg" not in body                 # marked safe, not escaped into visible markup


def test_no_qr_code_when_the_app_is_loopback_only(tmp_path):
    c, _ = _client(tmp_path)
    body = c.post("/settings", data={**FORM, "password": "pw"}).text
    assert "<svg" not in body
```

Check `_client`'s signature and `FORM`'s contents in that file before writing these — both
changed in Plan D part 2.

- [ ] **Step 7: Run the suite and commit**

```bash
env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest -q
git add pyproject.toml fridgesheet/qr.py fridgesheet/web/routes/settings.py \
        fridgesheet/web/templates/settings.html tests/test_qr.py tests/test_web_settings_page.py
git commit -m "web.settings: a QR code for the phone, drawn on this machine

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: the deferrals worth clearing

Issues #31–#36 hold about thirty items. This task clears the ones that are user-visible or
cheap-and-adjacent and leaves the rest, each with a stated reason.

**Files:**
- Modify: as the triage selects. Expect `fridgesheet/host/scheduling_windows.py`,
  `fridgesheet/host/scheduling_linux.py`, `fridgesheet/web/schedules.py`,
  `fridgesheet/reports/__init__.py`, `tests/test_host_scheduling_linux.py`.

**Interfaces:**
- Consumes: everything Plan D part 2 produced.
- Produces: nothing new.

- [ ] **Step 1: Fix these, in this order**

Each is small and each has a reason it is worth doing now rather than never:

1. **`web/schedules.py`'s `forget` refuses to delete a never-scheduled report when systemd
   is unreachable** (#36). A server started outside a user D-Bus session cannot delete a
   brand-new report, and the page blames a schedule that never existed. Skip the `remove`
   call when `describe` already reported `installed=False` **and** no `[reports.<key>]`
   table exists. Test both branches.
2. **`web/schedules.py`'s `_unmanageable` message names `fridgesheet-print-sheet.timer` for every
   key** (#36). A parent blocked on report 5 is handed a command that does nothing for
   report 5. Name the unit actually in the way. Test with a non-`open-work` key.
3. **`reports/__init__.py` still accepts `view:007`** (#36). It resolves to report 7 but
   renders `fridgesheet-view-007.timer` and stores a second `[reports."view:007"]` table that the
   Schedules page can never show or remove. Reject any spelling where
   `raw != str(int(raw))`. Test `007`, `7`, `0`.
4. **`host/scheduling_linux.py`'s `_FOREIGN_UNITS` does not name `service_linux.UNIT_FILE`**
   (#36). Windows refuses the web server's own task by name; Linux relies on the marker
   check happening to fail. Import the name — do not re-spell it — and refuse it explicitly,
   so the promise is not platform-conditional. Test it.
5. **`host/scheduling_windows.py` imports `DAY_NAMES` and never uses it** (#31-#36 roll-up);
   `_DAY_TAGS`'s keys, `host.DAY_NAMES` and `routes/schedules.py`'s `DAYS` are three
   spellings of one list. Build `_DAY_TAGS` from `DAY_NAMES` and have `routes/schedules.py`
   import it rather than keeping a fourth. One list, one place.
6. **`tests/test_host_scheduling_linux.py` has an unused `pathlib.Path` import**, and
   `test_a_pdf_only_report_builds_and_archives_but_never_prints` asserts nothing about the
   archive its name claims. Either assert the archive copy or rename the test to what it
   checks. Prefer asserting — the archive is real behaviour worth pinning.

- [ ] **Step 2: Leave these, and say so in your report**

Do **not** fix, and name the reason when you report:

- `safe_key`'s non-injectivity — the key space is closed, and making it injective means
  either ugly escaped unit names or a dependency from a pure string function onto the report
  registry.
- `install` leaving both unit files on disk when `daemon-reload`/`enable` fails — matches
  `host/service_linux.py` exactly; changing one without the other splits a convention.
- `config.py`'s `bool(sect.get("print", True))` accepting `print = "false"` — matches the
  `enabled` convention two lines above; same reasoning.
- `web/db.py`'s unused `schedules` table — dropping it needs a schema migration, which this
  plan does not open.
- `_table`/`_settings_for` duplicated between `web/schedules.py` and `web/actions.py` —
  a shared helper is right when a third caller appears.
- `describe`'s per-report subprocess cost on every `/schedules` render — real, but it is a
  caching design and belongs in its own change with its own measurements.
- The `manageable=False` row leaving time/days/printer interactively editable — no data-loss
  path; cosmetic.

- [ ] **Step 3: TDD each fix**

For each of the six, write the failing test first, run it, watch it fail for the stated
reason, implement, watch it pass. Commit them in coherent groups — by issue or by module,
not one commit per line.

- [ ] **Step 4: Run the suite**

Run: `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest -q`
Expected: 546 + your new tests, all passing.

- [ ] **Step 5: Commit**

Group as above; every message ends with the trailer.

---

### Task 5: the release checklist a human runs

Issue #30 wants manual checks on a real Windows PC and then a tag. This task writes the
checklist. **It does not run it and it does not tag.**

**Files:**
- Create: `docs/release-checklist.md`
- Modify: `README.md` — one line in "Releasing the Windows installer" pointing at it.

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

- [ ] **Step 1: Gather what is actually known**

Read `README.md`'s "Releasing the Windows installer" section, `.github/workflows/release.yml`,
`tests/test_packaging.py`, and issue #33's note that the installer has no pre-install stop.
The checklist must be built from what CI already proves versus what only a human on a real PC
can prove — do not ask a human to re-check something CI gates.

- [ ] **Step 2: Write the document**

`docs/release-checklist.md`, covering at least:

- **What CI already proves** (so the human skips it): the suite on both runners, the Windows
  build, the tag-matches-`pyproject.toml` gate, the SumatraPDF licence pin, and that the
  temporary branch trigger is absent from `release.yml`.
- **The known hazard, first and prominently**: issue #33 — the installer has no pre-install
  stop, so an upgrade lands on a running app. Until that is fixed, the human must exit Lakota
  Sheet (and end its logon task) before running the installer, and the checklist must say so
  at the top rather than in a footnote.
- **A standard-user install on a real PC**: SmartScreen path, no admin prompt, desktop
  shortcut, the logon task registered, the app opening in a browser.
- **First run as the friend would do it**: Settings (username, password, printer), Test
  login, Refresh now, Preview, Print now against a **real printer** — including that the page
  comes out duplex if the printer supports it.
- **A schedule end to end**: set one on the Schedules page for a few minutes ahead, leave the
  PC logged in, and confirm it printed and that Runs shows it. This is the one thing no test
  anywhere covers, because no test may touch a real scheduler.
- **The phone**: the LAN toggle, restart, scan the QR code from Task 3 with an actual phone,
  and confirm the Settings page refuses to take a password from it.
- **Uninstall**: both tasks removed, data left behind, the Credential Manager entry named.
- **Then, and only then, the tag**: the exact command, and a line saying the tag is the
  maintainer's to push.

Write it as checkboxes a person ticks, with the expected result beside each. Assume the
reader is Tony on a Saturday, not a QA department.

- [ ] **Step 3: Cross-reference it**

Add one line to `README.md`'s "Releasing the Windows installer" section pointing at
`docs/release-checklist.md` as the pre-tag gate.

- [ ] **Step 4: Run the suite and commit**

```bash
env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest -q
git add docs/release-checklist.md README.md
git commit -m "docs: the checklist a human runs before a tag

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## After the last task

1. **Whole-branch review** on the most capable model, with the spec and this plan. Pay
   attention to: whether the docs now agree with the app in every particular a reader could
   check; whether the QR path can ever reach the network; whether Task 4's fixes disturbed
   the ownership guarantees Plan D part 2 established.
2. **One fix wave**, then a scoped re-review of it.
3. **File residuals** as a GitHub issue in the series and close #28, #29, and the checklist
   half of #30 — leaving #30 open for the tag itself.
4. **Push and watch CI on both runners.** Poll with
   `gh run view <id> --json status,conclusion,jobs`; do not use `gh run watch`, which blocks.
5. **Stop before tagging.** The tag is Tony's, after he has run Task 5's checklist on a real
   PC.
