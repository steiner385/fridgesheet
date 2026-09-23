"""Fetch a release's installer, prove it is the one GitHub described, and hand off to it.

`web/updates.py` notices that a new release exists; this does something about it. The split
is deliberate: noticing is a read of a public API and is safe on a timer, and doing is code
execution on a family PC and is not.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

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
    different host than the one serving the file itself, so trusting the download means
    trusting that second, independent source rather than whatever answered the GET. An
    empty or malformed `digest` means the release had no installer at all (its URL falls
    back to the release page), which is refused here, before any network call, rather than
    after streaming 286 MB of HTML that was never going to match a hash.
    """
    if not digest.startswith("sha256:") or len(digest) != len("sha256:") + 64:
        raise UpdateError("That release has no installer to download.")
    want = digest.split(":", 1)[1].lower()
    # The updates/ folder does not exist before a household's first update, and
    # disk_usage() needs a path that exists -- create it before asking the filesystem
    # anything about it, so the common first-run case doesn't crash.
    dest.parent.mkdir(parents=True, exist_ok=True)
    if free_bytes is None:
        try:
            free = shutil.disk_usage(dest.parent).free
        except OSError as e:
            # Callers only ever have to handle UpdateError -- a vanished drive or a
            # permissions problem is exactly the kind of thing this promise covers.
            raise UpdateError(f"Could not check free space: {e}") from None
    else:
        free = free_bytes
    if size and free < size * SPACE_FACTOR:
        raise UpdateError(f"Not enough free space: {size * SPACE_FACTOR // 10**6} MB needed, "
                          f"{free // 10**6} MB free.")
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
        # A partial file that hashed wrong must never linger where something could later
        # execute it -- delete before raising, not just on the happy path.
        part.unlink(missing_ok=True)
        raise UpdateError("The downloaded installer does not match the checksum GitHub "
                          "published for it. Nothing was installed.")
    part.replace(dest)
    log(f"verified {got // 10**6} MB")
    return dest


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
        fields = {}
        for f in ("from_version", "to_version", "started_at", "installer", "log"):
            value = data[f]                      # KeyError -> caught below, treated as absent
            # Require each field to actually be a string. str() succeeds on anything, so a null
            # or nested object would otherwise coerce to "None" or "{'a': 1}", producing a
            # Pending that can never resolve and leaving a permanent "update did not finish"
            # banner on the Diagnostics page that the parent cannot clear. Treat such a corrupt
            # breadcrumb as absent instead.
            if not isinstance(value, str):
                return None
            fields[f] = value
        return Pending(**fields)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def resolve_pending(home: Path, running_version: str) -> tuple[str, Pending] | None:
    """Did the update this breadcrumb describes take? ("ok"|"failed", pending), or None when
    there was no update in flight. On success, the breadcrumb is archived (renames to
    update-last.json); on failure, it is kept so Diagnostics can report it."""
    pending = read_pending(home)
    if pending is None:
        return None
    if running_version == pending.to_version:
        (home / PENDING_NAME).replace(home / LAST_NAME)
        return "ok", pending
    return "failed", pending
