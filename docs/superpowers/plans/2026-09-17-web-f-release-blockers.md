# Web app F: the residuals that block a release or damage the product

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clear the residuals that stop `v0.3.0` being tagged or that a parent can see going wrong, and leave the rest in their issues.

**Architecture:** Six independent fixes across the installer, the Trends page's chart bootstrap, the web app's request guard, the job lock, and two one-liners. Nothing here is new capability; every task removes a defect an earlier plan's whole-branch review found and deliberately deferred.

**Tech Stack:** Python 3.12, FastAPI + Jinja2 + htmx (no build step), Inno Setup, uPlot 1.6.31 (vendored), pytest.

**Spec:** `docs/superpowers/specs/2026-09-15-fridgesheet-web-app-design.md` — sections 5 (Trends), 8 (access and security), 9 (jobs), 11 (packaging).

**Issues:** clears the lead items of **#33** and **#34**, the two one-liners in **#37**, and unblocks **#30** (the tag).

## Global Constraints

- Python 3.12, standard library only for anything new. No new runtime dependency.
- **There is no JavaScript test harness in this repo** (#34 names this explicitly, and every plan so far has refused to add one). `static/app.js` is therefore verified by **measuring a real browser**, not by a test. Chrome DevTools tooling is available in this environment; Task 2 requires real measurements and refuses eyeballing.
- **Never run a real `systemctl` or `schtasks`; never touch `~/.fridgesheet`; never tag anything.** The machine has the owner's live units — `fridgesheet-print-sheet.{service,timer}` prints a real household's school work every weekday at 2 PM. `tests/conftest.py`'s `_no_real_scheduler` fixture enforces the first; do not weaken, bypass or "simplify" it. Any real server run uses `FRIDGESHEET_HOME=/tmp/fridgesheet-plan-f` on a free port and is stopped afterwards.
- **No Windows machine is available here.** Task 1 changes the installer and cannot be run; its verification is the packaging test plus a careful reading, and its real proof is the release checklist a human works through. Say so rather than implying otherwise.
- The test command is `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest -q`. Baseline is **578 passing**.
- Commit messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

---

## Decisions this plan makes

**Decision 1 — scope is impact, not issue number.** Issues #31–#37 hold roughly a hundred items. This plan takes the ones that block the tag or that a parent sees, and leaves the rest where they are. A plan promising to close seven issues is a plan that runs out of budget inside the second one.

**Decision 2 — the child-name question is settled here, having been surfaced twice without an answer.** `fridgesheet/collector.py` carries real children's full names in a docstring; the same names are the test fixture across seven files. **Ruling: scrub the shipped-source docstring, leave the test fixtures.** The docstring ships to another family inside the installer; the fixtures do not ship and renaming them across seven files is churn with no recipient. If the owner wants the fixtures scrubbed too, that is a separate mechanical change. `packaging/windows/installer.iss`'s `AppPublisher` and the `LICENSE` copyright line stay — deliberate attribution, not leaked identifiers.

**Decision 3 — the `Host` allowlist is in scope even though the spec accepts network isolation as the boundary.** #33 argues it belongs beside the QR code, and the QR code shipped in Plan E. A page on an attacker domain that resolves to `127.0.0.1` currently passes both the same-origin check and the loopback password gate. Closing it is a handful of lines against a threat the spec calls out of scope, which is a good trade when the app is about to be given to someone else.

---

## File structure

**Modified:**
- `packaging/windows/installer.iss` — a `[Code]` `PrepareToInstall` that stops the running app.
- `fridgesheet/web/static/app.js`, `fridgesheet/web/static/app.css`, `fridgesheet/web/templates/_chart.html` — chart sizing and resize redraw.
- `fridgesheet/web/app.py` — the `Host` allowlist in `same_origin_only`.
- `fridgesheet/runner.py` — the lock's staleness guarantee.
- `fridgesheet/cli.py`, `fridgesheet/reports/__init__.py` — the two #37 one-liners.
- `fridgesheet/collector.py` — Decision 2.
- `tests/test_packaging.py`, `tests/test_web_app.py`, `tests/test_runner.py`, `tests/test_host_scheduling.py` — the covering tests.

---

### Task 1: the installer stops the app before overwriting it

**This is the item blocking the tag.** The logon task keeps `FridgeSheet.exe` and its `_internal` DLLs open around the clock, so every upgrade over a working install hits locked files. Inno's Restart Manager will at best show "Setup was unable to close the following applications", at worst demand a reboot. Release run 35002354271 proved only a clean first install, and the smoke test cannot catch it.

**Files:**
- Modify: `packaging/windows/installer.iss` (`[Code]` section, line 57 onward)
- Test: `tests/test_packaging.py`

**Interfaces:**
- Consumes: the logon task name, which is `service_windows.NAME` — import it rather than re-spelling it if the test needs it.
- Produces: nothing code-level.

- [ ] **Step 1: Read what is there**

Read `packaging/windows/installer.iss` end to end, and `tests/test_packaging.py::test_installer_script_matches_the_spec`. Note the existing `[Code]` section and what it already does — you are adding to it, not replacing it. Note also that `[Run]` installs the service *after* files are copied, so the ordering you need is: stop → copy → reinstall service.

- [ ] **Step 2: Write the failing test**

Extend the packaging test, which is how every other installer invariant in this repo is pinned:

```python
    # An upgrade lands on a running app: the logon task holds FridgeSheet.exe and its
    # _internal DLLs open, so Inno hits locked files unless setup stops it first. #33.
    assert "PrepareToInstall" in iss
    assert 'schtasks' in iss and '/End' in iss and 'Fridge Sheet - web' in iss
```

- [ ] **Step 3: Run it to verify it fails**

Run: `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest tests/test_packaging.py -q`
Expected: FAIL — `assert "PrepareToInstall" in iss`.

- [ ] **Step 4: Implement**

Add to the `[Code]` section a `PrepareToInstall` that ends the logon task and the running process. Inno calls `PrepareToInstall` before any file is copied, which is the window you need. Sketch — adapt to the file's existing Pascal style:

```pascal
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  // The logon task holds FridgeSheet.exe and its _internal DLLs open around the clock, so an
  // upgrade over a working install would hit locked files. Ending the task stops the server
  // it started; the [Run] section re-registers and restarts it after the files are in place.
  Exec('schtasks.exe', '/End /TN "Fridge Sheet - web"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  // A copy the parent started from the shortcut is not the task's child, so end it too. Both
  // calls are best-effort: a missing task or no running process is the ordinary case on a
  // first install, and neither should stop the installer.
  Exec('taskkill.exe', '/IM FridgeSheet.exe /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;
```

**Do not check `ResultCode` and fail the install on it.** On a first install there is no task and no process, and both commands return non-zero; treating that as an error would break the case that currently works.

Consider whether `AppMutex` is a better fit and say why you chose what you chose. The trade: `AppMutex` makes Inno wait and prompt the user politely, but requires the server to actually hold a named mutex, which is a code change in `web/__main__.py` and cannot be verified here either. `PrepareToInstall` needs no app change and is testable by reading. Either is defensible; pick one, implement it, and record the reasoning.

- [ ] **Step 5: Run the tests**

Run the focused file, then the whole suite. Expected: 578 + your assertions, all passing.

- [ ] **Step 6: Say plainly what you could not verify**

You have no Windows machine. Write in your report, in these terms: the packaging test proves the script contains the stop; nothing here proves it *works*. The proof is a human running `docs/release-checklist.md`'s upgrade step on a real PC. Add that upgrade step to the checklist if it is not already there — install, run, then install again over the top and confirm no "Setup was unable to close the following applications" dialog.

- [ ] **Step 7: Commit**

```bash
git add packaging/windows/installer.iss tests/test_packaging.py docs/release-checklist.md
git commit -m "installer: stop the running app before overwriting it

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: the Trends charts stop overflowing their boxes

The most visible defect in the app. Plan C's review measured it in Chrome: the grades holder's content box is 242px while uPlot's root is 330px (title 27 + plot 242 + legend 61); the weekly holder is 202px against 260px. **88px and 58px of overflow.** `.chart` sets no `overflow`, and uPlot appends the title and the legend table as *siblings* of the sized wrapper — so the grades legend prints on top of the "Missing, late and on time, by week" heading, and the weekly legend on top of the table header beneath it. Both are illegible in a full-page screenshot.

The cause is precise and worth stating: `app.js` measures the holder's content box and hands that height to uPlot as the **plot** height, but uPlot then adds a title and a legend *around* the plot. The holder is told to be 220px by an inline style in `_chart.html`; uPlot draws 220px of plot plus ~88px of furniture.

**Files:**
- Modify: `fridgesheet/web/static/app.js`, `fridgesheet/web/static/app.css`, `fridgesheet/web/templates/_chart.html`

**Interfaces:**
- Consumes: uPlot 1.6.31, vendored with a SHA-256 pin in `VENDOR.md` — do not upgrade it.
- Produces: nothing code-level.

- [ ] **Step 1: Reproduce and measure, before changing anything**

Start the app against a scratch home with seeded data on a free port:

```bash
env -u PYTHONPATH FRIDGESHEET_HOME=/tmp/fridgesheet-plan-f \
  ~/fridgesheet/.venv/bin/python -m fridgesheet.cli web --no-browser --port 8461
```

Open `/trends`, and measure — do not eyeball. Chrome DevTools tooling is available; use it to report, for **each** chart holder: the holder's `clientHeight`, the uPlot root's `offsetHeight`, and the heights of `.u-title` and `.u-legend`. Those four numbers are the before-state and your report must contain them. If the page has no data to chart, seed it or say so; a chart with nothing in it does not reproduce the bug.

- [ ] **Step 2: Fix the sizing**

Two shapes are defensible; the plan does not dictate which, but it does require that you say why:

- **Let the holder grow.** Drop the inline `height` from `_chart.html`, give `.chart` a `min-height`, and pass uPlot a plot height that is a sensible constant. The page reflows to whatever the furniture needs, and nothing can overflow because nothing is clipped to a fixed box.
- **Subtract the furniture.** Keep the fixed holder, construct uPlot, measure `.u-title` and `.u-legend`, then `setSize` the plot to `holder - title - legend`. Exact, but it draws twice and depends on uPlot's DOM shape, which is the thing that changed under you in the first place.

Whichever you choose, the acceptance condition is the same and is measured, not asserted: **for every chart, the uPlot root's `offsetHeight` must be less than or equal to the holder's `clientHeight`**, and the legend must not paint over the heading that follows it.

- [ ] **Step 3: Add the resize redraw**

uPlot is constructed once with a fixed pixel size, so resizing the window leaves the chart at its old dimensions. Add a `resize` listener that recomputes the box and calls `setSize`. Debounce it — a resize fires continuously during a drag, and `setSize` redraws the canvas. Keep the listener count bounded: one per chart, or one shared listener that walks the charts.

- [ ] **Step 4: Measure again, in the same way**

Re-measure all four numbers per chart and put the before/after table in your report. Take a full-page screenshot of `/trends` and confirm by looking at it that no legend sits on top of a heading. Then resize the window and confirm the chart follows.

- [ ] **Step 5: Run the suite**

Run: `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest -q`
Expected: 578 passing. There is no JS harness, so the suite proves only that you broke no Python; say that in your report rather than implying the suite covers this.

- [ ] **Step 6: Stop the server and commit**

```bash
git add fridgesheet/web/static/app.js fridgesheet/web/static/app.css fridgesheet/web/templates/_chart.html
git commit -m "web.trends: a chart fits the box it is given, and follows a resize

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: a `Host` allowlist on the request guard

`fridgesheet/web/app.py:240-246`'s `same_origin_only` compares `Origin` to `Host`. A page on an attacker domain whose DNS resolves to `127.0.0.1` sends `Origin: http://evil.example` and `Host: evil.example` — the two match, the check passes, and `loopback()` sees a 127.0.0.1 client address, so the OneLogin password gate opens too.

Spec section 8 accepts network isolation as the security boundary, so this is inside the stated risk. It is also a handful of lines, and the app is about to be handed to someone else. Decision 3 rules it in.

**Files:**
- Modify: `fridgesheet/web/app.py:239-246`
- Test: `tests/test_web_app.py`

**Interfaces:**
- Consumes: `settings.web_port`, `settings.web_allow_lan`, and `actions.lan_url`'s notion of this machine's LAN address.
- Produces: nothing later tasks use.

- [ ] **Step 1: Write the failing test**

```python
def test_a_host_header_this_app_does_not_answer_to_is_refused(tmp_path):
    """The same-origin check compares Origin to Host, so an attacker domain resolving to
    127.0.0.1 satisfies it -- both headers say `evil.example` and they match. Spec section 8
    accepts network isolation as the boundary, but the host we answer to is knowable, so
    checking it costs little and closes a hole that the loopback password gate is behind."""
    c, _ = _client(tmp_path)
    r = c.post("/settings", data={**FORM}, headers={"Host": "evil.example", "Origin": "http://evil.example"})
    assert r.status_code == 403


def test_the_addresses_this_app_does_answer_to_are_accepted(tmp_path):
    c, _ = _client(tmp_path)
    for host in ("127.0.0.1:8433", "localhost:8433", "127.0.0.1"):
        r = c.post("/settings", data={**FORM}, headers={"Host": host, "Origin": f"http://{host}"})
        assert r.status_code != 403, host
```

Check `tests/test_web_app.py`'s existing client helper and `FORM` before writing these — both moved in earlier plans.

- [ ] **Step 2: Run it to verify it fails**

Expected: FAIL — the first test gets 200 or 400, not 403, because the two headers match each other.

- [ ] **Step 3: Implement**

In `same_origin_only`, add a host check before the origin comparison. Allow `127.0.0.1`, `localhost`, `::1`, any of those with the configured port, and — **only when `allow_lan` is on** — this machine's LAN address. Compare the hostname part case-insensitively and ignore the port when the port matches the configured one.

Be careful with two things. A `Host` header may or may not carry the port. And when `allow_lan` is on, the LAN address is what a phone legitimately sends, so a static allowlist of loopback names would lock the phone out — which is the feature Plan E just finished building. Reuse `actions._lan_probe`/`lan_url`'s existing notion of the address rather than inventing a second one, and make it injectable so the test does not depend on the machine's network (Plan E hit exactly that and fixed it).

Refuse with the same 403 and the same short HTML the existing check returns; a parent should not see a different failure for this.

- [ ] **Step 4: Run the tests, including the phone path**

Run the focused file, then the whole suite. Then start a server with `allow_lan` on against the scratch home and confirm a request carrying the LAN `Host` still works — the Plan E QR code points a phone at exactly that.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/app.py tests/test_web_app.py
git commit -m "web: answer only to the addresses this app is actually served on

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: the job lock stops claiming a guarantee it loses

`web/jobs.py`'s worker docstring says `run.lock` stops an abandoned job and its replacement from both printing. That holds for 45 minutes: `runner.Lock.acquire` deletes any lock older than `LOCK_STALE_SECONDS`, and nothing refreshes the file during a run. So a job hung long enough to be displaced at 15 minutes reaches the stale threshold at 45, a second job takes the lock while the first still believes it holds it, and the first's `release()` then unlinks the *second's* lock file.

**Files:**
- Modify: `fridgesheet/runner.py` (the `Lock` class), and `fridgesheet/web/jobs.py`'s docstring
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes: `runner.LOCK_STALE_SECONDS`.
- Produces: whatever you add to `Lock`.

- [ ] **Step 1: Decide which half to fix, and say why**

#33 offers both: refresh the lock's mtime during a run, or say plainly in the comment that the guard expires. They are not equivalent.

Refreshing is the real fix and is small — a long run is the case the lock exists for, and a lock that expires under exactly that case is the wrong shape. But it needs something to do the refreshing, and the runner has no heartbeat.

The cheaper honest option is the release-side fix that closes the actual damage: **make `release()` unlink only a lock this process still owns.** Write the pid (or a token) into the lock file on acquire, and on release compare before unlinking. The stale-takeover still happens, but the displaced job can no longer delete the live job's lock — which is the part that turns a stale lock into two concurrent prints.

**Ruling: do the release-side ownership check, and correct the docstring to say the guard expires after `LOCK_STALE_SECONDS`.** It removes the damage without inventing a heartbeat, and the docstring stops overclaiming either way. Note in your report if you think the heartbeat is worth a follow-up.

Read `runner.Lock` before writing anything — the file already writes a pid for the Windows case (`web.lock` locks a byte at 1 MiB for the same reason), so there may be a pattern to follow.

- [ ] **Step 2: Write the failing test**

```python
def test_a_stale_takeover_cannot_have_its_lock_deleted_by_the_job_it_displaced(tmp_path):
    """`acquire` deletes a lock older than LOCK_STALE_SECONDS, so a long-hung job's lock is
    taken over while that job still believes it holds it. Its `release()` must then not unlink
    the lock now held by someone else -- that is what lets two runs print at once."""
    path = tmp_path / "run.lock"
    first = runner.Lock(path)
    assert first.acquire()
    os.utime(path, (0, 0))                      # age it past the stale threshold
    second = runner.Lock(path)
    assert second.acquire()                     # the takeover this test is about
    first.release()                             # the displaced job, finishing late
    assert path.is_file(), "the displaced job deleted the live job's lock"
    second.release()
    assert not path.is_file()
```

- [ ] **Step 3: Run it to verify it fails**

Expected: FAIL — `the displaced job deleted the live job's lock`.

- [ ] **Step 4: Implement, and correct the docstring**

Ownership check in `release()`, plus a docstring in `web/jobs.py` that says what is actually true: the lock stops two runs printing until it goes stale at `LOCK_STALE_SECONDS`, after which a second run can take it — and the displaced run will no longer delete the new holder's lock.

- [ ] **Step 5: Run the tests and commit**

```bash
git add fridgesheet/runner.py fridgesheet/web/jobs.py tests/test_runner.py
git commit -m "runner: a displaced job cannot delete the lock that displaced it

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: the two #37 one-liners

Both were found in Plan E's own final fix wave and rated non-blocking. Both are one line.

**Files:**
- Modify: `fridgesheet/cli.py`, `fridgesheet/reports/__init__.py`
- Test: `tests/test_host_scheduling.py`, `tests/test_report_view.py`

- [ ] **Step 1: `_removal_settings` catches what it promises to catch**

Its docstring promises "nothing that can abort the run", but it catches only `ConfigError`. A `config.toml` whose top-level `reports` is not a table makes `settings_from_doc` do `"oops".items()` → `AttributeError`, uncaught. That is the same harm class as the Critical this function was written to fix: a traceback before any removal, swallowed by Inno's `runhidden`.

Write the failing test first — a `config.toml` containing `reports = "oops"`, asserting `--all` still removes the built-in report and exits 1. Then widen the except on the `settings_from_doc` call; the salvage loop already `isinstance`-guards its input.

- [ ] **Step 2: `_VIEW_KEY_RE` anchors at the end of the string**

`reports/__init__.py`'s `_VIEW_KEY_RE` uses `$`, which matches before a trailing newline, so `is_schedulable_key("view:7\n")` and `resolve("view:7\n")` both accept it where the old `isdigit()` check rejected it. `safe_key` folds it to the same unit so no foreign object is reachable — but `web/schedules.py` writes `[reports.<key>]` verbatim for any key `resolve` accepts, so it would create a duplicate config table for one timer. That is the hazard the comment two lines below claims to prevent.

Test `"view:7\n"`, `"view:7 "` and `"view:7"`, then change `$` to `\Z` (or use `fullmatch`). Both call sites share the pattern, which is the payoff of the shared-pattern refactor.

- [ ] **Step 3: Run the suite and commit**

```bash
git add fridgesheet/cli.py fridgesheet/reports/__init__.py tests/test_host_scheduling.py tests/test_report_view.py
git commit -m "cli, reports: catch what the docstring promises, anchor what the comment claims

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: the children's names leave the shipped source

Per Decision 2. `fridgesheet/collector.py`'s `_first_name` docstring explains a real parsing bug using real children's full names — "First name from either 'Alex Example' (Canvas) or 'STEIN, ALEX' (HAC)" — and that file ships inside the installer to another family.

**Files:**
- Modify: `fridgesheet/collector.py`

- [ ] **Step 1: Rewrite the docstring**

Keep the technical content exactly — the two source formats and why they differ are the whole point, and the bug it describes (HAC keying a kid under `'Stein,'` while Canvas keyed the same kid under `'Alex'`) is real and worth recording. Replace the names with a neutral example that shows the same shapes, e.g. `'Alex Rivera'` (Canvas) and `'RIVERA, ALEX'` (HAC).

- [ ] **Step 2: Check the rest of the shipped source**

`grep -rniE "stein|alex|katherine|jo" fridgesheet/` and report every hit. Leave the `steiner385/...` GitHub URLs (a public repo identifier) and anything under `tests/` (fixtures, which do not ship). Report what you found either way.

- [ ] **Step 3: Run the suite and commit**

The suite must still pass unchanged — this is a docstring.

```bash
git add fridgesheet/collector.py
git commit -m "collector: a neutral example for the name-format bug

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## After the last task

1. **Whole-branch review** on the most capable model, with the spec and this plan. Pay attention to: whether Task 3's allowlist locks out the phone the QR code points at; whether Task 2's resize listener leaks across page navigations; whether Task 4's ownership check breaks the Windows `web.lock` path, which locks a byte for the same purpose.
2. **One fix wave**, then a scoped re-review of it.
3. **File residuals**, and update #33, #34 and #37 to strike what this plan cleared.
4. **Merge to `main`, push, and poll CI on both runners** with `gh run view <id> --json status,conclusion,jobs`. Not `gh run watch`, which blocks.
5. **Do not tag.** #30 stays open until a human has worked through `docs/release-checklist.md` on a real Windows PC — including, now, the upgrade-over-a-running-install step Task 1 adds.
