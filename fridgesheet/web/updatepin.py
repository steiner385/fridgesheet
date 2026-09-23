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
#: Ceiling on an iteration count parsed from `stored`. 240_000 sits comfortably inside it; a
#: hostile or corrupt config.toml must not be able to wedge the server with an absurd count
#: (or overflow the C long pbkdf2_hmac takes it as).
MAX_ITERATIONS = 10_000_000
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
    if not isinstance(stored, str):
        # An unquoted `update_pin_hash = 2468` in config.toml parses to an int, not a str;
        # fail closed instead of raising AttributeError on `.split`.
        return False
    parts = stored.split("$")
    if len(parts) != 4 or parts[0] != ALGORITHM:
        return False
    try:
        iterations = int(parts[1])
        salt = base64.b64decode(parts[2], validate=True)
        expected = base64.b64decode(parts[3], validate=True)
    except (ValueError, TypeError, OverflowError):
        return False
    if not (1 <= iterations <= MAX_ITERATIONS) or not salt or not expected:
        return False
    try:
        # surrogatepass so an unpaired surrogate in `pin` fails closed instead of raising a
        # UnicodeEncodeError whose repr/args carry the plaintext PIN into a traceback.
        pin_bytes = (pin or "").encode("utf-8", errors="surrogatepass")
    except UnicodeEncodeError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", pin_bytes, salt, iterations)
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
