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
        # A partial file that hashed wrong must never linger where something could later
        # execute it -- delete before raising, not just on the happy path.
        part.unlink(missing_ok=True)
        raise UpdateError("The downloaded installer does not match the checksum GitHub "
                          "published for it. Nothing was installed.")
    part.replace(dest)
    log(f"verified {got // 10**6} MB")
    return dest
