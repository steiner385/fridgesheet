# In-app self-update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A parent updates Fridge Sheet to the newest release from the Settings page, behind a PIN; an operator does the same with `fridgesheet self-update` from a shell.

**Architecture:** `web/updates.py` keeps *noticing* a new release and gains the asset's sha256. A new platform-split `host/selfupdate*` module *does* the update: verify preconditions, stream-download the asset while hashing it, refuse on any mismatch, write a breadcrumb, then spawn the installer **detached** so it escapes the `taskkill /T` tree the installer itself uses to kill the app. The app is then killed by that installer and restarted by `[Run]`'s `service install`. The next start reads the breadcrumb and reports what happened.

**Tech Stack:** Python 3.12, FastAPI + Jinja2, `hashlib`/`hmac` (stdlib — no new dependency), `subprocess` with Windows creation flags, Inno Setup (unchanged), pytest.

**Spec:** `docs/superpowers/specs/2026-09-22-in-app-self-update-design.md`

## Global Constraints

- **Windows only.** `selfupdate_linux` exists and refuses; it never raises `AttributeError`.
- **No new runtime dependency.** PIN hashing uses `hashlib.pbkdf2_hmac`; comparison uses `hmac.compare_digest`.
- **The PIN plaintext is never written anywhere** — not to `config.toml`, not to a log, not into a rendered form field.
- **Nothing executes on a digest mismatch.** Refuse, delete the file, say so.
- **The installer is spawned detached** — `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`. A child process would be killed by the installer's own `taskkill /IM FridgeSheet.exe /T /F` (`packaging/windows/installer.iss:117`).
- **Installer flags, exactly:** `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG=<path>`.
- **No installer (`.iss`) changes.** `[Run]`'s `service install` has no `skipifsilent` and ends in `schtasks /Run`, so a silent install already re-registers and restarts the server.
- **`[web] check_updates = false` disables this feature completely** — no button, and the route refuses. The parent turned off the app's one outbound call; self-update must not reinstate it.
- Tests never reach GitHub. `updates.DEFAULT_FETCH` is replaced in `conftest`, and `state.extra["update_fetch"]` injects per-app.

## Review Focus

1. **A second job displaces an update mid-flight.** `Worker.submit` abandons the current job to take the slot, but the abandoned thread keeps running — so a parent clicking *Refresh now* during an update would get an installer fired at them anyway, killing the app mid-refresh. Pinned in Task 7.
2. **Two updates at once.** Two 286 MB downloads and two installers racing. The single job slot mostly prevents this; the route must not create a second path around it. Pinned in Task 7.
3. **The release has no `.exe` asset.** `updates.latest_release` falls back to the release *page* URL, so a naive download fetches HTML and fails the digest check late, after 286 MB of nothing. Refuse up front. Pinned in Task 3.
4. **The disk fills after the space check passes.** The check is not a reservation. A partial file must be deleted, not left to be executed or to fill the disk. Pinned in Task 4.
5. **`check_updates` is off.** No button, and the route refuses — see Global Constraints. Pinned in Task 7.

---

### Task 1: `ServiceInfo.owner` — who the logon task runs as

The CLI must refuse to update an install it does not own (spec §6). `service_windows.describe` already parses every `schtasks /Query /V` field into a dict and reads only `Status`; the owner is `Run As User` in that same dict.

**Files:**
- Modify: `fridgesheet/host/__init__.py` (the `ServiceInfo` dataclass, ~line 135)
- Modify: `fridgesheet/host/service_windows.py:51-62` (`describe`)
- Modify: `fridgesheet/host/service_linux.py` (`describe` — pass `owner=""`)
- Test: `tests/test_host_service_windows.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ServiceInfo.owner: str` — the account the logon task runs as, `""` when unknown or not Windows.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_host_service_windows.py
import subprocess
from fridgesheet.host import service_windows

QUERY_V = """\
Folder: \\
HostName:                             GRAPHY
TaskName:                             \\Fridge Sheet - web
Status:                               Running
Logon Mode:                           Interactive/Background
Task To Run:                          C:\\Users\\lakotarunner\\AppData\\Local\\Programs\\Fridge Sheet\\FridgeSheet.exe web --no-browser
Run As User:                          lakotarunner
"""


def _run_returning(stdout: str, code: int = 0):
    def run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, code, stdout=stdout, stderr="")
    return run


def test_describe_reports_the_account_the_task_runs_as():
    """Seen on graphy 2026-09-22: the task runs as `lakotarunner` while SSH arrives as
    `tony`. A self-update by the wrong user builds a second install and changes nothing
    anyone can see, so the owner has to be readable."""
    info = service_windows.describe(run=_run_returning(QUERY_V))
    assert info.owner == "lakotarunner"
    assert info.installed and info.active


def test_owner_is_empty_rather_than_wrong_when_the_field_is_absent():
    info = service_windows.describe(run=_run_returning("Status:  Running\n"))
    assert info.owner == ""


def test_an_absent_task_has_no_owner():
    info = service_windows.describe(run=_run_returning("", code=1))
    assert info.installed is False and info.owner == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_host_service_windows.py -q`
Expected: FAIL — `TypeError: ServiceInfo.__init__() got an unexpected keyword argument 'owner'`, or `AttributeError: 'ServiceInfo' object has no attribute 'owner'`.

- [ ] **Step 3: Write minimal implementation**

```python
# fridgesheet/host/__init__.py
@dataclass(frozen=True)
class ServiceInfo:
    managed_by: str                 # "systemd" | "task-scheduler"
    installed: bool
    active: bool
    detail: str
    #: The account the unit or task runs as, "" when unknown. A per-user logon task only
    #: fires for its owner, and a per-user install lives in that owner's profile, so an
    #: update run by anyone else builds a second copy and leaves the running one alone.
    owner: str = ""
```

```python
# fridgesheet/host/service_windows.py -- end of describe()
    status = fields.get("Status", "")
    return ServiceInfo("task-scheduler", True, status.lower() == "running",
                       f"logon task {status or 'installed'}", owner=fields.get("Run As User", ""))
```

`service_linux.describe` keeps its current call — `owner` defaults to `""`, which is correct there: this plan does not read it on Linux.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_host_service_windows.py tests/test_host_service_linux.py -q`
Expected: PASS, and the Linux service tests still pass.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/host/__init__.py fridgesheet/host/service_windows.py tests/test_host_service_windows.py
git commit -m "host: ServiceInfo carries the account its task runs as"
```

---

### Task 2: The asset digest on `Update`

`updates.latest_release` already picks the `.exe` asset. It throws away the `digest` GitHub publishes beside it — which is what §4 verifies against.

**Files:**
- Modify: `fridgesheet/web/updates.py` (`Update`, `latest_release`, `check`)
- Test: `tests/test_web_updates.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Update.digest: str` (`"sha256:<hex>"` or `""`), `Update.size: int`; `latest_release(fetch) -> tuple[str, str, str, int]` returning `(version, url, digest, size)` — **note the arity change from 2 to 4**, and `check()` updated accordingly. The size is the asset's bytes, and it exists so Task 4's free-space check has something to check against; without it that check is dead code.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_web_updates.py
import json
from fridgesheet.web import updates

DIGEST = "sha256:b99a964520507b9582819a75fcc4f34d4e9da6d23d40f939f4d2e73d080b7def"


def _release(assets):
    return lambda url: json.dumps({"tag_name": "v0.5.0", "html_url": "https://example/rel",
                                   "assets": assets}).encode()


def test_the_installers_digest_and_size_come_back_with_its_url():
    fetch = _release([{"name": "FridgeSheet-Setup-0.5.0.exe", "size": 286033630,
                       "browser_download_url": "https://example/s.exe", "digest": DIGEST}])
    version, url, digest, size = updates.latest_release(fetch)
    assert (version, url, digest, size) == ("0.5.0", "https://example/s.exe", DIGEST, 286033630)


def test_a_release_with_no_installer_has_no_digest_and_no_size():
    """The URL falls back to the release page. Downloading that yields HTML, so the caller
    must be able to tell this case apart before it spends 286 MB finding out."""
    version, url, digest, size = updates.latest_release(_release([]))
    assert version == "0.5.0" and url == "https://example/rel" and digest == "" and size == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_updates.py -q -k digest`
Expected: FAIL — `ValueError: too many values to unpack (expected 3)`.

- [ ] **Step 3: Write minimal implementation**

```python
# fridgesheet/web/updates.py
@dataclass(frozen=True)
class Update:
    current: str
    latest: str = ""
    url: str = ""
    checked_at: datetime | None = None
    error: str = ""
    #: "sha256:<hex>" for the installer asset, "" when the release has no installer. What
    #: `host.selfupdate` verifies the download against; an empty digest means there is
    #: nothing to install, not "skip the check".
    digest: str = ""
    #: The asset's size in bytes, 0 when there is no installer. Carried so the download can
    #: refuse for want of disk space before it starts rather than after 286 MB.
    size: int = 0
```

```python
def latest_release(fetch: Callable[[str], bytes] | None = None) -> tuple[str, str, str, int]:
    """(version, url, digest, size) for the newest published release. The URL is the Windows
    installer asset when the release has one -- with GitHub's sha256 and byte count for it --
    else the release page, no digest and no size."""
    data = json.loads((fetch or DEFAULT_FETCH)(LATEST_URL))
    tag = str(data.get("tag_name") or "")
    if not parse_version(tag):
        raise ValueError(f"release tag {tag!r} is not a version")
    asset = next((a for a in data.get("assets") or []
                  if str(a.get("name", "")).lower().endswith(".exe")), None)
    if asset is not None:
        try:
            size = int(asset.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        return tag.lstrip("v"), str(asset.get("browser_download_url") or ""), str(asset.get("digest") or ""), size
    return tag.lstrip("v"), str(data.get("html_url") or RELEASES_PAGE), "", 0
```

In `check()`, change the unpack and pass it through:

```python
        latest, url, digest, size = latest_release(fetch or state.extra.get("update_fetch"))
        result = Update(current, latest, url, now, digest=digest, size=size)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_updates.py -q`
Expected: PASS, including the existing tests — `Update(current, "", "", now, error=...)` still works because `digest` has a default.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/updates.py tests/test_web_updates.py
git commit -m "updates: carry the installer's sha256 beside its URL"
```

---

### Task 3: The update PIN

Spec §3. Pure functions first — no web, no config, no I/O — so the hashing and the lockout are testable on their own.

**Files:**
- Create: `fridgesheet/web/updatepin.py`
- Test: `tests/test_web_updatepin.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `hash_pin(pin: str) -> str` — `"pbkdf2_sha256$<iters>$<salt_b64>$<hash_b64>"`
  - `verify(pin: str, stored: str) -> bool`
  - `class Attempts` with `record_failure(now) -> None`, `locked_until(now) -> datetime | None`, `clear() -> None`
  - `MAX_ATTEMPTS = 5`, `LOCKOUT = timedelta(minutes=15)`, `ITERATIONS = 240_000`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_web_updatepin.py
from datetime import datetime, timedelta

from fridgesheet.web import updatepin

NOW = datetime(2026, 9, 22, 15, 0)


def test_a_stored_pin_is_a_hash_and_never_the_pin():
    stored = updatepin.hash_pin("2468")
    assert "2468" not in stored
    assert stored.startswith("pbkdf2_sha256$")
    assert updatepin.verify("2468", stored)


def test_the_same_pin_hashes_differently_every_time():
    """A shared salt would let two households with the same PIN recognise it in each
    other's config.toml, and makes one precomputed table work everywhere."""
    assert updatepin.hash_pin("2468") != updatepin.hash_pin("2468")


def test_a_wrong_pin_is_refused():
    stored = updatepin.hash_pin("2468")
    assert not updatepin.verify("2469", stored)
    assert not updatepin.verify("", stored)


def test_nothing_verifies_against_an_unset_or_malformed_pin():
    """No PIN set must never mean every PIN works."""
    for stored in ("", "   ", "not-a-hash", "pbkdf2_sha256$abc"):
        assert not updatepin.verify("2468", stored)
        assert not updatepin.verify("", stored)


def test_five_failures_lock_the_route_for_fifteen_minutes():
    a = updatepin.Attempts()
    for _ in range(4):
        a.record_failure(NOW)
    assert a.locked_until(NOW) is None
    a.record_failure(NOW)
    assert a.locked_until(NOW) == NOW + timedelta(minutes=15)


def test_the_lock_expires():
    a = updatepin.Attempts()
    for _ in range(5):
        a.record_failure(NOW)
    assert a.locked_until(NOW + timedelta(minutes=16)) is None


def test_a_correct_pin_clears_the_count():
    a = updatepin.Attempts()
    for _ in range(4):
        a.record_failure(NOW)
    a.clear()
    a.record_failure(NOW)
    assert a.locked_until(NOW) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_updatepin.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fridgesheet.web.updatepin'`.

- [ ] **Step 3: Write minimal implementation**

```python
# fridgesheet/web/updatepin.py
"""The PIN that stands between the house network and an installer running on the family PC.

This app has no authentication and `[web] allow_lan` binds 0.0.0.0, so every device in the
house reaches every route -- the children's phones included. A page that shows grades and a
button that downloads and executes a binary are not the same object, and only the second one
needs a gate.

What this is not: the page has no HTTPS, so the PIN crosses the LAN in the clear, and it can
be read over a parent's shoulder. It raises the bar from "any device on the wifi" to "a
device that has been told the PIN". That was the trade taken knowingly (spec section 3); the
alternative, a loopback-only button, is stronger and stops a parent updating from the phone
in their hand.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta

ALGORITHM = "pbkdf2_sha256"
#: Cost. A PIN is short, so the hash is the only thing making a stolen config.toml expensive.
ITERATIONS = 240_000
SALT_BYTES = 16
MAX_ATTEMPTS = 5
LOCKOUT = timedelta(minutes=15)


def hash_pin(pin: str) -> str:
    """`pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>`. A fresh salt every call."""
    salt = os.urandom(SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, ITERATIONS)
    return f"{ALGORITHM}${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify(pin: str, stored: str) -> bool:
    """Whether `pin` matches `stored`. False for an unset or malformed `stored` -- "no PIN
    configured" must never read as "every PIN is correct"."""
    parts = (stored or "").split("$")
    if len(parts) != 4 or parts[0] != ALGORITHM:
        return False
    try:
        iterations = int(parts[1])
        salt = base64.b64decode(parts[2], validate=True)
        expected = base64.b64decode(parts[3], validate=True)
    except (ValueError, TypeError):
        return False
    if iterations < 1 or not salt or not expected:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", (pin or "").encode("utf-8"), salt, iterations)
    return hmac.compare_digest(dk, expected)


@dataclass
class Attempts:
    """Failed PIN tries, in memory. A restart clears them, which is acceptable: a restart is
    not something an attacker without the PIN can cause."""
    failures: list[datetime] = field(default_factory=list)

    def record_failure(self, now: datetime) -> None:
        self.failures.append(now)

    def clear(self) -> None:
        self.failures.clear()

    def locked_until(self, now: datetime) -> datetime | None:
        recent = [t for t in self.failures if now - t < LOCKOUT]
        self.failures = recent
        if len(recent) < MAX_ATTEMPTS:
            return None
        return max(recent) + LOCKOUT
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_updatepin.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/updatepin.py tests/test_web_updatepin.py
git commit -m "updates: the PIN that gates the update button"
```

---

### Task 4: Download and verify

Spec §4. Platform-independent, so it lives in `selfupdate.py` beside the platform pick and is tested without Windows.

**Files:**
- Create: `fridgesheet/host/selfupdate.py`
- Test: `tests/test_host_selfupdate.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class UpdateError(RuntimeError)`
  - `download_verified(url, digest, dest, *, opener=None, log, free_bytes=None, size=0) -> Path`
  - `CHUNK = 1 << 20`, `SPACE_FACTOR = 2`

**Note for the implementer:** `size` is the asset's byte count, from `latest_release` (Task 2). It is not optional in practice — the free-space check is `if size and free < size * SPACE_FACTOR`, so a caller that omits it silently disables that check while every test still passes. Task 7's call site passes it.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_host_selfupdate.py
import hashlib
import io
import pytest

from fridgesheet.host import selfupdate

BODY = b"pretend installer" * 1000
GOOD = "sha256:" + hashlib.sha256(BODY).hexdigest()


def _opener(body: bytes):
    def open_url(url):
        return io.BytesIO(body)
    return open_url


def _log(_line):
    pass


def test_a_verified_download_lands_at_dest(tmp_path):
    dest = tmp_path / "Setup.exe"
    out = selfupdate.download_verified("https://x/s.exe", GOOD, dest,
                                       opener=_opener(BODY), log=_log, free_bytes=10**9)
    assert out == dest and dest.read_bytes() == BODY


def test_a_wrong_digest_refuses_and_leaves_nothing_behind(tmp_path):
    """The whole point. Nothing may execute that GitHub did not describe."""
    dest = tmp_path / "Setup.exe"
    with pytest.raises(selfupdate.UpdateError, match="does not match"):
        selfupdate.download_verified("https://x/s.exe", "sha256:" + "00" * 32, dest,
                                     opener=_opener(BODY), log=_log, free_bytes=10**9)
    assert not dest.exists()
    assert list(tmp_path.iterdir()) == []


def test_an_empty_digest_refuses_before_downloading(tmp_path):
    """A release with no .exe asset. The URL is the release page; fetching it would give
    HTML and fail the hash after 286 MB of nothing."""
    calls = []

    def opener(url):
        calls.append(url)
        return io.BytesIO(BODY)

    with pytest.raises(selfupdate.UpdateError, match="no installer"):
        selfupdate.download_verified("https://x/releases", "", tmp_path / "s.exe",
                                     opener=opener, log=_log, free_bytes=10**9)
    assert calls == []


def test_too_little_free_space_refuses_before_downloading(tmp_path):
    calls = []

    def opener(url):
        calls.append(url)
        return io.BytesIO(BODY)

    with pytest.raises(selfupdate.UpdateError, match="free space"):
        selfupdate.download_verified("https://x/s.exe", GOOD, tmp_path / "s.exe",
                                     opener=opener, log=_log, free_bytes=1000, size=10**9)
    assert calls == []


def test_a_download_that_dies_partway_leaves_nothing_behind(tmp_path):
    """Review Focus 4: the space check is not a reservation. A partial file must never be
    left where something could execute it."""
    class Dying(io.BytesIO):
        def read(self, n=-1):
            raise OSError("connection reset")

    dest = tmp_path / "Setup.exe"
    with pytest.raises(selfupdate.UpdateError):
        selfupdate.download_verified("https://x/s.exe", GOOD, dest,
                                     opener=lambda u: Dying(), log=_log, free_bytes=10**9)
    assert not dest.exists()
    assert list(tmp_path.iterdir()) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_host_selfupdate.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fridgesheet.host.selfupdate'`.

- [ ] **Step 3: Write minimal implementation**

```python
# fridgesheet/host/selfupdate.py
"""Fetch a release's installer, prove it is the one GitHub described, and hand off to it.

`web/updates.py` notices that a new release exists; this does something about it. The split
is deliberate: noticing is a read of a public API and is safe on a timer, and doing is code
execution on a family PC and is not.
"""
from __future__ import annotations

import hashlib
import shutil
import urllib.request
from pathlib import Path
from typing import Callable

from . import IS_WINDOWS

CHUNK = 1 << 20              # 1 MiB; the asset is ~286 MB and never held in memory
#: Free space wanted before starting: the installer on disk plus the install it performs.
SPACE_FACTOR = 2
TIMEOUT = 60


class UpdateError(RuntimeError):
    """Something about this update is wrong, in one sentence a parent can act on."""


def _default_opener(url: str):
    return urllib.request.urlopen(url, timeout=TIMEOUT)     # noqa: S310  a fixed https URL


def download_verified(url: str, digest: str, dest: Path, *, opener: Callable | None = None,
                      log: Callable[[str], None], free_bytes: int | None = None,
                      size: int = 0) -> Path:
    """Stream `url` to `dest`, hashing as it goes, and keep it only if it matches `digest`.

    `digest` is GitHub's `"sha256:<hex>"` for the asset, served from api.github.com -- a
    different host than the one serving the file. An empty `digest` means the release had no
    installer at all, which is refused here rather than after a 286 MB download of the
    release page's HTML.
    """
    if not digest.startswith("sha256:") or len(digest) != len("sha256:") + 64:
        raise UpdateError("That release has no installer to download.")
    want = digest.split(":", 1)[1].lower()
    free = shutil.disk_usage(dest.parent).free if free_bytes is None else free_bytes
    if size and free < size * SPACE_FACTOR:
        raise UpdateError(f"Not enough free space: {size * SPACE_FACTOR // 10**6} MB needed, "
                          f"{free // 10**6} MB free.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    h = hashlib.sha256()
    got = 0
    try:
        with (opener or _default_opener)(url) as r, part.open("wb") as f:
            while True:
                block = r.read(CHUNK)
                if not block:
                    break
                f.write(block)
                h.update(block)
                got += len(block)
                if got % (32 * CHUNK) < CHUNK:
                    log(f"downloaded {got // 10**6} MB")
    except UpdateError:
        part.unlink(missing_ok=True)
        raise
    except Exception as e:                          # noqa: BLE001  network, disk, anything
        part.unlink(missing_ok=True)
        raise UpdateError(f"The download did not finish: {type(e).__name__}: {str(e)[:120]}") from None
    if h.hexdigest().lower() != want:
        part.unlink(missing_ok=True)
        raise UpdateError("The downloaded installer does not match the checksum GitHub "
                          "published for it. Nothing was installed.")
    part.replace(dest)
    log(f"verified {got // 10**6} MB")
    return dest
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_host_selfupdate.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/host/selfupdate.py tests/test_host_selfupdate.py
git commit -m "selfupdate: download an installer and prove it is the published one"
```

---

### Task 5: The breadcrumb

Spec §6. The app cannot watch its own replacement, so the outcome crosses the gap in a file.

**Files:**
- Modify: `fridgesheet/host/selfupdate.py`
- Test: `tests/test_host_selfupdate.py`

**Interfaces:**
- Consumes: `UpdateError` (Task 4).
- Produces:
  - `@dataclass(frozen=True) Pending(from_version: str, to_version: str, started_at: str, installer: str, log: str)`
  - `write_pending(home: Path, pending: Pending) -> Path`
  - `read_pending(home: Path) -> Pending | None`
  - `resolve_pending(home: Path, running_version: str) -> tuple[str, Pending] | None` returning `("ok"|"failed", pending)`
  - `PENDING_NAME = "update-pending.json"`, `LAST_NAME = "update-last.json"`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_host_selfupdate.py  (append)
from fridgesheet.host.selfupdate import Pending


def _pending():
    return Pending(from_version="0.4.1", to_version="0.5.0",
                   started_at="2026-09-22T15:00:00-04:00",
                   installer=r"C:\u\updates\Setup.exe", log=r"C:\u\updates\install.log")


def test_a_breadcrumb_round_trips(tmp_path):
    selfupdate.write_pending(tmp_path, _pending())
    assert selfupdate.read_pending(tmp_path) == _pending()


def test_the_new_version_running_means_it_worked(tmp_path):
    selfupdate.write_pending(tmp_path, _pending())
    verdict, pending = selfupdate.resolve_pending(tmp_path, "0.5.0")
    assert verdict == "ok" and pending.to_version == "0.5.0"
    assert selfupdate.read_pending(tmp_path) is None          # archived, not left to fire again
    assert (tmp_path / selfupdate.LAST_NAME).exists()


def test_the_old_version_still_running_means_it_did_not_take(tmp_path):
    selfupdate.write_pending(tmp_path, _pending())
    verdict, pending = selfupdate.resolve_pending(tmp_path, "0.4.1")
    assert verdict == "failed" and pending.log.endswith("install.log")
    assert selfupdate.read_pending(tmp_path) is not None       # kept, so Diagnostics can show it


def test_no_breadcrumb_is_a_normal_start(tmp_path):
    assert selfupdate.read_pending(tmp_path) is None
    assert selfupdate.resolve_pending(tmp_path, "0.4.1") is None


def test_a_malformed_breadcrumb_is_treated_as_absent_and_never_fatal(tmp_path):
    (tmp_path / selfupdate.PENDING_NAME).write_text("{not json", encoding="utf-8")
    assert selfupdate.read_pending(tmp_path) is None
    assert selfupdate.resolve_pending(tmp_path, "0.4.1") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_host_selfupdate.py -q -k pending or breadcrumb`
Expected: FAIL — `AttributeError: module 'fridgesheet.host.selfupdate' has no attribute 'Pending'`.

- [ ] **Step 3: Write minimal implementation**

```python
# fridgesheet/host/selfupdate.py  (append; add `import json` and the dataclass imports at top)
PENDING_NAME = "update-pending.json"
LAST_NAME = "update-last.json"


@dataclass(frozen=True)
class Pending:
    """What was started, so whatever starts next can say whether it worked."""
    from_version: str
    to_version: str
    started_at: str          # ISO 8601, local
    installer: str
    log: str


def write_pending(home: Path, pending: Pending) -> Path:
    home.mkdir(parents=True, exist_ok=True)
    path = home / PENDING_NAME
    path.write_text(json.dumps(asdict(pending), indent=2), encoding="utf-8")
    return path


def read_pending(home: Path) -> Pending | None:
    """The breadcrumb, or None. A malformed file is absent: a bad JSON file must never stop
    the app starting, which is the one thing that would turn a failed update into a dead one."""
    try:
        data = json.loads((home / PENDING_NAME).read_text(encoding="utf-8"))
        return Pending(**{f: str(data[f]) for f in ("from_version", "to_version", "started_at",
                                                    "installer", "log")})
    except (OSError, ValueError, KeyError, TypeError):
        return None


def resolve_pending(home: Path, running_version: str) -> tuple[str, Pending] | None:
    """Did the update this breadcrumb describes take? ("ok"|"failed", pending), or None when
    there was no update in flight."""
    pending = read_pending(home)
    if pending is None:
        return None
    if running_version == pending.to_version:
        (home / PENDING_NAME).replace(home / LAST_NAME)
        return "ok", pending
    return "failed", pending
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_host_selfupdate.py -q`
Expected: PASS (10 tests).

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/host/selfupdate.py tests/test_host_selfupdate.py
git commit -m "selfupdate: a breadcrumb, so the next start can report the last one"
```

---

### Task 6: The platform handoff — detached on Windows, a refusal on Linux

Spec §5. **The whole design rests on this**: `installer.iss:117` runs `taskkill /IM FridgeSheet.exe /T /F`, and `/T` takes the process tree, so a child process would kill itself.

**Files:**
- Create: `fridgesheet/host/selfupdate_windows.py`
- Create: `fridgesheet/host/selfupdate_linux.py`
- Modify: `fridgesheet/host/selfupdate.py` (the platform pick)
- Test: `tests/test_host_selfupdate_windows.py`, `tests/test_host_selfupdate_linux.py`

**Interfaces:**
- Consumes: `UpdateError`, `Pending` (Tasks 4-5).
- Produces: `selfupdate.spawn_installer(installer: Path, log_path: Path, *, popen=None) -> None`, dispatching to the platform module. `INSTALLER_FLAGS: tuple[str, ...]`. On Windows, `DETACHED_PROCESS = 0x00000008`, `CREATE_NEW_PROCESS_GROUP = 0x00000200`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_host_selfupdate_windows.py
from pathlib import Path

import pytest

from fridgesheet.host import selfupdate_windows as sw


def test_the_installer_escapes_the_apps_process_tree():
    """installer.iss:117 runs `taskkill /IM FridgeSheet.exe /T /F` before it copies a file.
    /T takes the tree, so an installer launched as our child kills itself mid-upgrade. This
    assertion is the entire reason the handoff is shaped the way it is."""
    seen = {}

    def popen(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return None

    sw.spawn_installer(Path(r"C:\u\Setup.exe"), Path(r"C:\u\install.log"), popen=popen)
    flags = seen["kw"]["creationflags"]
    assert flags & sw.DETACHED_PROCESS
    assert flags & sw.CREATE_NEW_PROCESS_GROUP
    assert seen["kw"].get("close_fds") is True


def test_the_installer_runs_silently_and_writes_a_log():
    seen = {}
    sw.spawn_installer(Path(r"C:\u\Setup.exe"), Path(r"C:\u\install.log"),
                       popen=lambda cmd, **kw: seen.update(cmd=cmd))
    assert seen["cmd"][0] == r"C:\u\Setup.exe"
    assert "/VERYSILENT" in seen["cmd"]
    assert "/SUPPRESSMSGBOXES" in seen["cmd"]
    assert "/NORESTART" in seen["cmd"]
    assert r"/LOG=C:\u\install.log" in seen["cmd"]
```

```python
# tests/test_host_selfupdate_linux.py
import pytest

from fridgesheet.host import selfupdate, selfupdate_linux


def test_linux_refuses_and_names_the_checkout_path():
    """Not absent -- absent means AttributeError somewhere less helpful."""
    with pytest.raises(selfupdate.UpdateError, match="git pull"):
        selfupdate_linux.spawn_installer(None, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_host_selfupdate_windows.py tests/test_host_selfupdate_linux.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fridgesheet.host.selfupdate_windows'`.

- [ ] **Step 3: Write minimal implementation**

```python
# fridgesheet/host/selfupdate_windows.py
"""Hand off to the installer and wait to be killed by it.

`packaging/windows/installer.iss`'s PrepareToInstall runs, before [Files] copies anything:

    Exec('taskkill.exe', '/IM FridgeSheet.exe /T /F', ...)

The /T takes the process *tree*. An installer launched as an ordinary child of this process
is inside that tree, so it would kill itself before copying a file. DETACHED_PROCESS and
CREATE_NEW_PROCESS_GROUP are what put it outside.

Nothing here needs changing in the installer: [Run]'s `service install` carries no
`skipifsilent`, and `service_windows.install` ends in `schtasks /Run`, so a silent install
re-registers the logon task and restarts the server by itself.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
INSTALLER_FLAGS = ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART")


def spawn_installer(installer: Path, log_path: Path, *, popen=subprocess.Popen) -> None:
    popen([str(installer), *INSTALLER_FLAGS, f"/LOG={log_path}"],
          creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
          close_fds=True, stdin=None, stdout=None, stderr=None)
```

```python
# fridgesheet/host/selfupdate_linux.py
"""There is no Linux installer to run. A Linux install is a git checkout."""
from __future__ import annotations

from .selfupdate import UpdateError


def spawn_installer(installer, log_path, *, popen=None) -> None:
    raise UpdateError("Fridge Sheet updates itself only on Windows. This is a source "
                      "checkout: update it with `git pull && pip install -e .` and restart "
                      "the service.")
```

```python
# fridgesheet/host/selfupdate.py  (append)
def spawn_installer(installer: Path, log_path: Path, *, popen=None) -> None:
    """Start the installer outside this process's tree, then expect to be killed by it."""
    if IS_WINDOWS:
        from . import selfupdate_windows as impl
    else:
        from . import selfupdate_linux as impl
    kwargs = {"popen": popen} if popen is not None else {}
    impl.spawn_installer(installer, log_path, **kwargs)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_host_selfupdate_windows.py tests/test_host_selfupdate_linux.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/host/selfupdate_windows.py fridgesheet/host/selfupdate_linux.py fridgesheet/host/selfupdate.py tests/test_host_selfupdate_windows.py tests/test_host_selfupdate_linux.py
git commit -m "selfupdate: spawn the installer outside the tree it is about to kill"
```

---

### Task 7: The job kind and the gated route

Spec §3 and §5. **`POST /jobs/{kind}` accepts any kind in `jobs.KINDS`** (`routes/jobs.py:31`), so adding `"update"` there without a guard would make the whole PIN pointless.

**Files:**
- Modify: `fridgesheet/web/jobs.py` (`KINDS`, `LABELS`, `GATED`, `OPEN_KINDS`, `Worker._run`)
- Modify: `fridgesheet/web/routes/jobs.py:31` (accept only `OPEN_KINDS`)
- Modify: `fridgesheet/web/actions.py` (`self_update`)
- Modify: `fridgesheet/web/routes/settings.py` (`POST /settings/update`)
- Test: `tests/test_web_selfupdate_route.py`

**Interfaces:**
- Consumes: `updatepin.verify`/`Attempts` (Task 3), `selfupdate.*` (Tasks 4-6), `Update.digest` (Task 2), `ServiceInfo.owner` (Task 1).
- Produces: `jobs.GATED = ("update",)`, `jobs.OPEN_KINDS`, `actions.self_update(*, home, log, settings, state) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_web_selfupdate_route.py
from fridgesheet.web import jobs, updatepin
from tests.web_fixtures import app_for, seed


def test_the_generic_job_route_will_not_start_an_update(tmp_path):
    """The PIN is worthless if POST /jobs/update works without it. `update` is in KINDS so
    the worker can run it, and out of OPEN_KINDS so the open route cannot start it."""
    assert "update" in jobs.KINDS
    assert "update" not in jobs.OPEN_KINDS
    seed(tmp_path)
    r = app_for(tmp_path).post("/jobs/update")
    assert r.status_code == 404


def test_no_pin_configured_means_the_route_refuses(tmp_path):
    seed(tmp_path)
    r = app_for(tmp_path).post("/settings/update", data={"pin": "2468"})
    assert r.status_code == 403
    assert "PIN" in r.text


def test_a_wrong_pin_is_refused_and_counted(tmp_path, monkeypatch):
    seed(tmp_path, update_pin_hash=updatepin.hash_pin("2468"))
    c = app_for(tmp_path)
    for _ in range(5):
        assert c.post("/settings/update", data={"pin": "0000"}).status_code == 403
    r = c.post("/settings/update", data={"pin": "2468"})          # correct, but locked now
    assert r.status_code == 429 and "15 minutes" in r.text


def test_the_route_refuses_when_the_parent_turned_update_checks_off(tmp_path):
    """Review Focus 5. `check_updates = false` is the parent switching off this app's one
    outbound call; a button must not quietly put it back."""
    seed(tmp_path, update_pin_hash=updatepin.hash_pin("2468"), check_updates=False)
    r = app_for(tmp_path).post("/settings/update", data={"pin": "2468"})
    assert r.status_code == 409


def test_an_update_job_will_not_be_displaced_by_another_job(tmp_path):
    """Review Focus 1: `Worker.submit` abandons the running job to take the slot, but the
    abandoned thread keeps going -- so a Refresh started mid-update would still get an
    installer fired at it. An update in flight holds the slot."""
    seed(tmp_path, update_pin_hash=updatepin.hash_pin("2468"))
    c = app_for(tmp_path)
    c.post("/settings/update", data={"pin": "2468"})
    r = c.post("/jobs/refresh")
    assert r.status_code == 409


def test_a_second_update_cannot_start_while_one_is_running(tmp_path):
    """Review Focus 2: two 286 MB downloads and two installers racing each other."""
    seed(tmp_path, update_pin_hash=updatepin.hash_pin("2468"))
    c = app_for(tmp_path)
    assert c.post("/settings/update", data={"pin": "2468"}).status_code == 200
    assert c.post("/settings/update", data={"pin": "2468"}).status_code == 409
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_selfupdate_route.py -q`
Expected: FAIL — `AttributeError: module 'fridgesheet.web.jobs' has no attribute 'OPEN_KINDS'`.

- [ ] **Step 3: Write minimal implementation**

```python
# fridgesheet/web/jobs.py
KINDS = ("refresh", "preview", "print", "doctor", "login", "update")
LABELS = {"refresh": "Refreshing", "preview": "Building today's sheet", "print": "Printing",
          "doctor": "Running diagnostics", "login": "Testing the login",
          "update": "Updating Fridge Sheet"}
#: Kinds `POST /jobs/{kind}` may start on its own authority. `update` downloads and executes
#: an installer, so it is started only by the PIN-gated route in routes/settings.py. Derived
#: rather than listed, so a kind added to KINDS is never accidentally made public here.
GATED = ("update",)
OPEN_KINDS = tuple(k for k in KINDS if k not in GATED)
```

In `Worker.submit`, refuse to displace an update (Review Focus 1) — add before the displacement branch:

```python
        if self.current is not None and not self.current.done and self.current.kind == "update":
            return None                    # an installer is already on its way; nothing preempts it
```

In `Worker._run`, add the branch:

```python
            elif job.kind == "update":
                ok = self.actions.self_update(home=home, log=log, settings=settings, state=self.state)
                outcome, message = ("OK" if ok else "FAIL"), (job.lines[-1] if job.lines else "")
```

```python
# fridgesheet/web/routes/jobs.py:31
    if kind not in jobmod.OPEN_KINDS:
        raise HTTPException(404, f"no job kind {kind!r}")
```

```python
# fridgesheet/web/actions.py  (append)
def self_update(*, home: Path, log: Callable[[str], None], settings, state) -> bool:
    """Download the newest installer, prove it, and hand off. Returns False having explained
    itself; raising would only reach the job's generic handler."""
    from ..host import selfupdate
    from . import updates as updatemod
    try:
        current = updatemod.current_version()
        latest, url, digest, size = updatemod.latest_release(state.extra.get("update_fetch"))
        if not updatemod.newer(latest, current):
            log(f"Already on {current}; nothing to do.")
            return False
        log(f"Downloading Fridge Sheet {latest} ({size // 10**6} MB)...")
        folder = home / "updates"
        # `size` is not decoration: without it `download_verified`'s free-space check is
        # dead code, because it has nothing to compare the free space against.
        installer = selfupdate.download_verified(url, digest, folder / f"FridgeSheet-Setup-{latest}.exe",
                                                 log=log, size=size)
        log_path = folder / f"install-{latest}.log"
        selfupdate.write_pending(home, selfupdate.Pending(
            from_version=current, to_version=latest, started_at=state.now().isoformat(),
            installer=str(installer), log=str(log_path)))
        log("Starting the installer. Fridge Sheet will close and come back on its own.")
        selfupdate.spawn_installer(installer, log_path)
        return True
    except selfupdate.UpdateError as e:
        log(str(e))
        return False
```

```python
# fridgesheet/web/routes/settings.py  (append)
@router.post("/settings/update")
def start_update(request: Request, pin: str = Form(""), conn: sqlite3.Connection = Db, state=State):
    """The only way to start an update from the web. See `jobs.GATED`."""
    if not state.settings.web_check_updates:
        raise HTTPException(409, "Update checks are turned off in Settings.")
    stored = state.settings.web_update_pin_hash
    if not stored:
        raise HTTPException(403, "Set an update PIN in Settings before updating from here.")
    attempts = state.extra.setdefault("update_attempts", updatepin.Attempts())
    until = attempts.locked_until(state.now())
    if until is not None:
        raise HTTPException(429, "Too many wrong PINs. Try again in 15 minutes.")
    if not updatepin.verify(pin, stored):
        attempts.record_failure(state.now())
        raise HTTPException(403, "That PIN is not right.")
    attempts.clear()
    w = _worker(state)
    job = w.submit("update")
    if job is None:
        r = render_partial(request, conn, "_job.html", job=w.current, busy=True, pdf=None)
        r.status_code = 409
        return r
    return render_partial(request, conn, "_job.html", job=job, busy=False, pdf=None)
```

`tests/web_fixtures.seed` gains `update_pin_hash=""` and `check_updates=True` keyword arguments that it writes into the generated `config.toml` under `[web]`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_selfupdate_route.py tests/test_web_jobs.py -q`
Expected: PASS, and the existing job tests still pass.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/jobs.py fridgesheet/web/routes/jobs.py fridgesheet/web/routes/settings.py fridgesheet/web/actions.py tests/test_web_selfupdate_route.py tests/web_fixtures.py
git commit -m "web: an update job, startable only through the PIN"
```

---

### Task 8: The setting, and setting the PIN

Spec §3: write-only, like the OneLogin password that already never reads back.

**Files:**
- Modify: `fridgesheet/config.py` (`Settings.web_update_pin_hash`, the `[web]` read at ~line 314)
- Modify: `fridgesheet/web/actions.py` (`FormValues`, `load_form`, `save`)
- Modify: `fridgesheet/web/templates/settings.html`
- Test: `tests/test_web_settings_page.py`

**Interfaces:**
- Consumes: `updatepin.hash_pin` (Task 3).
- Produces: `Settings.web_update_pin_hash: str`, read from `[web] update_pin_hash`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_web_settings_page.py  (append)
def test_setting_an_update_pin_stores_a_hash_and_never_the_pin(tmp_path):
    seed(tmp_path)
    c = app_for(tmp_path)
    c.post("/settings", data=_form(update_pin="2468"))
    text = (tmp_path / "config.toml").read_text(encoding="utf-8")
    assert "2468" not in text
    assert "pbkdf2_sha256$" in text


def test_the_pin_never_reads_back_into_the_form(tmp_path):
    """Same rule as the OneLogin password: settable from a phone, never readable."""
    seed(tmp_path, update_pin_hash=updatepin.hash_pin("2468"))
    body = app_for(tmp_path).get("/settings").text
    assert "pbkdf2_sha256$" not in body
    assert 'name="update_pin"' in body and "2468" not in body


def test_a_blank_pin_field_keeps_the_stored_one(tmp_path):
    stored = updatepin.hash_pin("2468")
    seed(tmp_path, update_pin_hash=stored)
    c = app_for(tmp_path)
    c.post("/settings", data=_form(update_pin=""))
    assert stored in (tmp_path / "config.toml").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_settings_page.py -q -k update_pin`
Expected: FAIL — the form has no `update_pin` field; `config.toml` has no `pbkdf2_sha256$`.

- [ ] **Step 3: Write minimal implementation**

```python
# fridgesheet/config.py -- beside web_check_updates
    #: [web] update_pin_hash: the PIN that gates the Settings page's update button
    #: (`web/updatepin.py`). A hash, never the PIN; blank means no button is offered.
    web_update_pin_hash: str = ""
```

```python
# fridgesheet/config.py -- beside the check_updates read
    s.web_update_pin_hash = str(web.get("update_pin_hash", s.web_update_pin_hash) or "")
```

In `actions.FormValues` add `update_pin: str = ""`; `load_form` never populates it. In `actions.save`, hash a non-blank value and leave the stored one alone when blank — the same shape the password already uses:

```python
    if form.update_pin.strip():
        _table(doc, "web")["update_pin_hash"] = updatepin.hash_pin(form.update_pin.strip())
```

In `settings.html`, beside the "Check for updates" checkbox:

```html
<label>Update PIN
  <input type="password" name="update_pin" autocomplete="new-password"
         placeholder="leave blank to keep the stored one">
  <small class="muted">Needed to update Fridge Sheet from this page. It is stored as a
  hash, never read back, and it crosses your network in the clear -- this page has no
  HTTPS.</small>
</label>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_settings_page.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/config.py fridgesheet/web/actions.py fridgesheet/web/templates/settings.html tests/test_web_settings_page.py
git commit -m "settings: an update PIN, stored hashed and never read back"
```

---

### Task 9: The button, its guards, and the page that outlives the server

Spec §6: the polling page is client-side, so it survives the server dying.

**Files:**
- Modify: `fridgesheet/web/templates/settings.html`
- Modify: `fridgesheet/web/routes/settings.py` (`_page` passes the guards)
- Create: `fridgesheet/web/templates/_update_button.html`
- Test: `tests/test_web_settings_page.py`

**Interfaces:**
- Consumes: `describe_service().installed` (Task 1), `updates.cached` (existing), `Settings.web_update_pin_hash` (Task 8).
- Produces: template context `update_ready: bool`, `update_blocked_reason: str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_web_settings_page.py  (append)
def test_no_button_without_a_pin(tmp_path):
    seed(tmp_path)
    body = app_for(tmp_path).get("/settings").text
    assert 'action="/settings/update"' not in body
    assert "Set an update PIN" in body


def test_no_button_when_the_logon_task_is_missing(tmp_path):
    """Issue #39: schtasks /Create fails for standard users and Inno ignores [Run] exit
    codes. A silent update on such a machine leaves a dead app with no wizard and no
    shortcut, so we decline rather than strand them."""
    seed(tmp_path, update_pin_hash=updatepin.hash_pin("2468"))
    body = app_for(tmp_path, service_installed=False).get("/settings").text
    assert 'action="/settings/update"' not in body
    assert "is not set up to start on its own" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_settings_page.py -q -k button`
Expected: FAIL — `"Set an update PIN" not in body`.

- [ ] **Step 3: Write minimal implementation**

In `routes/settings.py:_page`, compute the guards:

```python
    info = service.describe_service()
    reason = ""
    if not state.settings.web_check_updates:
        reason = "Update checks are turned off."
    elif not state.settings.web_update_pin_hash:
        reason = "Set an update PIN below to update from this page."
    elif not info.installed:
        reason = ("Fridge Sheet is not set up to start on its own on this computer, so an "
                  "update could leave it closed. Install it again from the desktop shortcut "
                  "first (issue #39).")
```

`_update_button.html`:

```html
{# The update button, and the reasons it is sometimes absent. A button that downloads and
   executes an installer is not offered when we can already predict it would strand the
   household -- see the spec's section 6. #}
{% if update_blocked_reason %}
  <p class="muted">{{ update_blocked_reason }}</p>
{% elif update and update.available %}
  <form action="/settings/update" method="post" hx-post="/settings/update" hx-target="#update-job">
    <label>Update PIN <input type="password" name="pin" autocomplete="off" required></label>
    <button type="submit">Update to {{ update.latest }}</button>
  </form>
  <div id="update-job"></div>
  <script>
  // The server is about to be killed by the installer it starts, so this poll has to
  // outlive it. It is already loaded in the browser by then, which is the whole trick.
  document.body.addEventListener('htmx:afterRequest', function (e) {
    if (!e.detail.pathInfo || e.detail.pathInfo.requestPath !== '/settings/update') return;
    if (e.detail.xhr.status !== 200) return;
    var deadline = Date.now() + 10 * 60 * 1000;
    (function poll() {
      fetch('/health', {cache: 'no-store'})
        .then(function (r) { return r.json(); })
        .then(function (h) {
          if (h.version === '{{ update.latest }}') { location.reload(); return; }
          setTimeout(poll, 3000);
        })
        .catch(function () {
          if (Date.now() > deadline) {
            document.getElementById('update-job').textContent =
              'This is taking longer than expected. Open Fridge Sheet from your desktop shortcut.';
            return;
          }
          setTimeout(poll, 3000);
        });
    })();
  });
  </script>
{% endif %}
```

`app_for` in `tests/web_fixtures.py` gains `service_installed: bool = True`, injecting a `describe_service` stub through `state.extra`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_settings_page.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/templates/ fridgesheet/web/routes/settings.py tests/test_web_settings_page.py tests/web_fixtures.py
git commit -m "settings: the update button, and the two cases it declines"
```

---

### Task 10: `fridgesheet self-update`

Spec §6's footgun: run as the wrong user, a per-user installer builds a second copy and leaves the running server alone — silently.

**Files:**
- Modify: `fridgesheet/cli.py` (`cmd_self_update`, parser registration near the `service` parser at ~line 496)
- Test: `tests/test_cli_selfupdate.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `fridgesheet self-update [--check] [--force]`, exit 0 on success, 1 on refusal.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_selfupdate.py
import pytest

from fridgesheet import cli
from fridgesheet.host import ServiceInfo


class Args:
    check = False
    force = False


def test_it_refuses_when_another_account_owns_the_install(capsys, monkeypatch):
    """Observed on graphy 2026-09-22: the task runs as `lakotarunner`, SSH arrives as
    `tony`. A per-user installer would build a second copy under the wrong profile and
    report success -- the worst failure, because nothing visible changes."""
    monkeypatch.setattr(cli, "_current_user", lambda: "tony")
    monkeypatch.setattr(cli, "_service_info",
                        lambda: ServiceInfo("task-scheduler", True, True, "running", owner="lakotarunner"))
    assert cli.cmd_self_update(Args()) == 1
    err = capsys.readouterr().err
    assert "lakotarunner" in err and "tony" in err


def test_force_proceeds_anyway(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_current_user", lambda: "tony")
    monkeypatch.setattr(cli, "_service_info",
                        lambda: ServiceInfo("task-scheduler", True, True, "running", owner="lakotarunner"))
    monkeypatch.setattr(cli, "_do_self_update", lambda **kw: calls.append(kw) or 0)
    args = Args()
    args.force = True
    assert cli.cmd_self_update(args) == 0 and calls


def test_the_owner_running_it_is_not_refused(monkeypatch):
    monkeypatch.setattr(cli, "_current_user", lambda: "lakotarunner")
    monkeypatch.setattr(cli, "_service_info",
                        lambda: ServiceInfo("task-scheduler", True, True, "running", owner="lakotarunner"))
    monkeypatch.setattr(cli, "_do_self_update", lambda **kw: 0)
    assert cli.cmd_self_update(Args()) == 0


def test_an_unknown_owner_is_not_treated_as_a_mismatch(monkeypatch):
    """Linux, or a schtasks response without the field. Refusing here would refuse always."""
    monkeypatch.setattr(cli, "_current_user", lambda: "tony")
    monkeypatch.setattr(cli, "_service_info",
                        lambda: ServiceInfo("task-scheduler", True, True, "running", owner=""))
    monkeypatch.setattr(cli, "_do_self_update", lambda **kw: 0)
    assert cli.cmd_self_update(Args()) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli_selfupdate.py -q`
Expected: FAIL — `AttributeError: module 'fridgesheet.cli' has no attribute 'cmd_self_update'`.

- [ ] **Step 3: Write minimal implementation**

```python
# fridgesheet/cli.py
def _current_user() -> str:
    import getpass
    try:
        return getpass.getuser()
    except Exception:       # noqa: BLE001  no password database entry; not worth dying for
        return ""


def _service_info():
    from .host import service
    return service.describe_service()


def _do_self_update(*, home, settings) -> int:
    from .web import actions
    lines: list[str] = []

    def log(line: str) -> None:
        lines.append(line)
        print(line)

    class _State:                       # actions.self_update wants `.extra` and `.now()`
        extra: dict = {}

        @staticmethod
        def now():
            from datetime import datetime
            return datetime.now().astimezone()

    return 0 if actions.self_update(home=home, log=log, settings=settings, state=_State()) else 1


def cmd_self_update(args) -> int:
    """Update this install to the newest release.

    No PIN here, deliberately: a shell on this machine already owns this machine, so asking
    for one would be theatre. What it does check is ownership -- a per-user logon task only
    fires for its owner, and a per-user install lives in that owner's profile, so an update
    run by anyone else builds a second copy under a different profile and leaves the running
    server untouched. Silently.
    """
    from .web import updates as updatemod
    s = load_settings()
    if args.check:
        current = updatemod.current_version()
        latest, _url, _digest, _size = updatemod.latest_release()
        print(f"{current} installed; {latest} is the newest release."
              if updatemod.newer(latest, current) else f"{current} is the newest release.")
        return 0
    info, me = _service_info(), _current_user()
    if not args.force and info.owner and me and info.owner.casefold() != me.casefold():
        print(f"The logon task runs as {info.owner!r} and its install lives in that account's "
              f"profile; you are {me!r}. Updating from here would build a second copy under "
              f"{me!r} and leave the running one alone. Run this as {info.owner!r}, or pass "
              f"--force if you mean to install a separate copy.", file=sys.stderr)
        return 1
    return _do_self_update(home=s.home, settings=s)
```

Registration, beside the `service` parser:

```python
    su = sub.add_parser("self-update", help="install the newest release over this one (Windows)")
    su.add_argument("--check", action="store_true", help="say what is available; install nothing")
    su.add_argument("--force", action="store_true", help="proceed even if another account owns the install")
    su.set_defaults(fn=cmd_self_update)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli_selfupdate.py tests/test_cli.py -q`
Expected: PASS, existing CLI tests unaffected.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/cli.py tests/test_cli_selfupdate.py
git commit -m "cli: self-update, refusing to update an install it does not own"
```

---

### Task 11: Report the last update, and prove the spawn on Windows

Spec §6 and §7: the breadcrumb has to reach a person, and the one claim unit tests cannot reach has to be exercised on a real Windows runner.

**Files:**
- Modify: `fridgesheet/web/routes/diagnostics.py`
- Modify: `fridgesheet/web/templates/diagnostics.html`
- Modify: `packaging/windows/smoke.ps1`
- Test: `tests/test_web_diagnostics_page.py`

**Interfaces:**
- Consumes: `selfupdate.resolve_pending` (Task 5).
- Produces: nothing downstream.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_web_diagnostics_page.py  (append)
from fridgesheet.host import selfupdate


def test_a_failed_update_is_reported_with_its_log(tmp_path):
    seed(tmp_path)
    selfupdate.write_pending(tmp_path, selfupdate.Pending(
        from_version="0.4.1", to_version="9.9.9", started_at="2026-09-22T15:00:00-04:00",
        installer=r"C:\u\Setup.exe", log=r"C:\u\install.log"))
    body = app_for(tmp_path).get("/diagnostics").text
    assert "9.9.9" in body and "install.log" in body


def test_a_clean_start_says_nothing_about_updates(tmp_path):
    seed(tmp_path)
    assert "did not finish" not in app_for(tmp_path).get("/diagnostics").text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_diagnostics_page.py -q -k update`
Expected: FAIL — `"9.9.9" not in body`.

- [ ] **Step 3: Write minimal implementation**

In `routes/diagnostics.py`, resolve once per page render and pass to the template:

```python
    verdict = selfupdate.resolve_pending(state.home, updates.current_version())
```

In `diagnostics.html`:

```html
{% if verdict and verdict[0] == 'failed' %}
<div class="card">
  <h3>The last update did not finish</h3>
  <p>An update from {{ verdict[1].from_version }} to {{ verdict[1].to_version }} was started
     on {{ verdict[1].started_at }} and this is still {{ verdict[1].from_version }}.</p>
  <p class="muted">The installer is still at <code>{{ verdict[1].installer }}</code> -- you can
     run it yourself. What it logged is in <code>{{ verdict[1].log }}</code>.</p>
</div>
{% endif %}
```

In `packaging/windows/smoke.ps1`, add the one claim only a Windows runner can test — that a detached child survives a `taskkill /T` aimed at its parent:

```powershell
# The whole self-update design rests on this: installer.iss's PrepareToInstall runs
# `taskkill /IM FridgeSheet.exe /T /F`, and /T takes the process tree. Prove that a child
# spawned the way host/selfupdate_windows.py spawns one is NOT in that tree.
Write-Host "smoke: detached spawn survives a tree kill"
$parent = Start-Process -FilePath "powershell" -PassThru -WindowStyle Hidden `
  -ArgumentList "-NoProfile","-Command","Start-Process powershell -ArgumentList '-NoProfile','-Command','Start-Sleep 60' -WindowStyle Hidden; Start-Sleep 60"
Start-Sleep -Seconds 3
$before = @(Get-Process powershell -ErrorAction SilentlyContinue).Count
taskkill /PID $parent.Id /T /F | Out-Null
Start-Sleep -Seconds 2
$after = @(Get-Process powershell -ErrorAction SilentlyContinue).Count
if ($after -ge $before - 1) { Write-Host "  ok: a detached grandchild outlived the tree kill" }
else { throw "detached spawn did not survive taskkill /T -- self-update would kill its own installer" }
Get-Process powershell -ErrorAction SilentlyContinue | Where-Object { $_.Id -ne $PID } | Stop-Process -Force
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_diagnostics_page.py -q`
Expected: PASS. The PowerShell block runs only in `release.yml` on `windows-latest`.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/routes/diagnostics.py fridgesheet/web/templates/diagnostics.html packaging/windows/smoke.ps1 tests/test_web_diagnostics_page.py
git commit -m "diagnostics: say when an update did not take, and prove the detached spawn"
```

---

### Task 12: Documentation, including a stale section that is now wrong

`docs/release-checklist.md` §0b says the install is under `tony` and the console user is `gdrunner`. On 2026-09-22 the logon task on graphy runs as `lakotarunner`, with its install under that profile. A checklist that names the wrong account sends a human to the wrong place.

**Files:**
- Modify: `README.md` (the Settings paragraph in the web section, and the CLI reference)
- Modify: `docs/release-checklist.md` (§0b's account note; a new §3b for self-update)
- Test: `tests/test_rebrand.py` and `tests/test_packaging.py` already run over these; no new test.

- [ ] **Step 1: Correct §0b's account claim**

Replace the "Which account hosts it" bullet with what is actually true, and say how to re-check it:

```markdown
- **Which account hosts it.** As of 2026-09-22 the `Fridge Sheet - web` task on graphy runs
  as `lakotarunner`, with its install under `C:\Users\lakotarunner\AppData\Local\Programs\
  Fridge Sheet`. (It has been `tony` and `gdrunner` at different times; check rather than
  assume — `schtasks /Query /TN "Fridge Sheet - web" /FO LIST /V` prints `Run As User`.) A
  per-user logon task only fires for the user that owns it, and a per-user install lives in
  that user's profile, so `fridgesheet self-update` refuses when run by anyone else.
```

- [ ] **Step 2: Add §3b — self-update on a real machine**

```markdown
## 3b. Self-update, over a running app

Section 3 proves the *installer* survives landing on a running app. This proves the app can
start that installer on itself. It needs a release newer than the installed one, so do it on
the release after the one that introduces self-update.

- [ ] Settings → set an **Update PIN**, Save. **Expect:** `config.toml`'s `[web]` has an
  `update_pin_hash` beginning `pbkdf2_sha256$`, and the PIN itself appears nowhere in it.
- [ ] Reload Settings. **Expect:** the PIN box is empty with its placeholder — a PIN is
  settable and never readable, same rule as the password.
- [ ] From a **phone**, enter the wrong PIN five times. **Expect:** refused each time, then
  "Too many wrong PINs" for fifteen minutes even with the right one.
- [ ] From the phone, after the lock expires, enter the right PIN and press **Update**.
  **Expect:** progress in the page, then it waits, then it reloads showing the new version.
- [ ] Open **Settings** and read the version. **Expect:** the new one (see §3's note about
  `[InstallDelete]` — this is the same hazard).
- [ ] Open **Task Scheduler**. **Expect:** `Fridge Sheet - web` still there, still Running.
- [ ] Open **Task Manager**. **Expect:** exactly one `FridgeSheet.exe` once the page is up.
- [ ] **Do it again with a Refresh in flight**, so Chromium is live under `{app}`. This is
  the case `taskkill /T` exists for and the one §3 still has not covered.
```

- [ ] **Step 3: README**

Add to the Settings sentence in the web section: *"…and **Update Fridge Sheet**, which downloads the newest release's installer, checks it against the checksum GitHub published, and runs it — behind a PIN you set on the same page, because every device on your network can reach this app."* Add `fridgesheet self-update [--check] [--force]` to the CLI list with one line on the ownership refusal.

- [ ] **Step 4: Run the suite**

Run: `python -m pytest -q`
Expected: PASS. `test_rebrand.py` scans `README.md` and `docs/release-checklist.md`; both are in its `EXEMPT` set, but the suite must still be green.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/release-checklist.md
git commit -m "docs: self-update, and the account graphy actually runs as"
```

---

## Before opening the PR

- [ ] `python -m pytest -q` — the whole suite. `tests/test_host_credentials.py::test_settings_credentials_falls_back_to_store_username_then_errors` fails on a host whose keyring holds a real credential; it fails on `main` too and is unrelated. Any *other* failure is yours.
- [ ] **REQUIRED SUB-SKILL:** `security-self-review`. This change touches authorization, a stored secret, and code execution, on a child-facing surface.
- [ ] Open the PR against `main` with auto-merge (`gh pr merge <n> --auto --squash`). `main` requires `test (ubuntu-latest)` and `test (windows-latest)`, so auto-merge waits for green CI.
