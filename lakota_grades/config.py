"""Configuration. Secrets are never stored here.

Credentials are read, in order of preference:
  1. From the environment (LAKOTA_ONELOGIN_USERNAME / _PASSWORD), populated by a 1Password
     Environments mounted .env file, `op run --env-file=.env -- lakota-grades ...`, or a
     plain .env you manage yourself.
  2. From the GNOME keyring / freedesktop Secret Service, via `secret-tool`. This is the
     default local store: encrypted at rest under the login password, unlocked by PAM at
     desktop login, and readable by an unattended systemd --user timer because the user
     manager already exports DBUS_SESSION_BUS_ADDRESS. If nobody has logged into the
     desktop session the keyring is locked and this source fails loudly rather than
     hanging on a prompt that no one can answer.
  3. From `op read` secret references (op://Vault/Item/field) if LAKOTA_OP_USERNAME_REF /
     LAKOTA_OP_PASSWORD_REF are set. Requires the 1Password CLI with desktop-app integration,
     so it needs someone present to approve the prompt -- fine interactively, not for a timer.
     Note: op:// references reject punctuation such as '(' in an item title, and percent-
     encoding does not help -- address such items by UUID (op://Vault/<uuid>/password).

Nothing in this module writes a secret to disk or logs it.
"""
from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

log = logging.getLogger("lakota.config")

DEFAULT_HOME = Path(os.environ.get("LAKOTA_GRADES_HOME", Path.home() / ".lakota-grades"))

#: Secret Service attributes used for the keyring entries: service=<this>, key=username|password
KEYRING_SERVICE = os.environ.get("LAKOTA_KEYRING_SERVICE", "lakota-grades")
KEYRING_LABEL = "Lakota OneLogin (lakota-grades)"


def _load_env_files() -> None:
    """Load a mounted 1Password .env (or a plain one) if present. Later files do not override earlier ones."""
    candidates = [
        os.environ.get("LAKOTA_ENV_FILE"),
        str(Path.cwd() / ".env"),
        str(DEFAULT_HOME / ".env"),
    ]
    for c in candidates:
        if c and Path(c).is_file():
            load_dotenv(c, override=False)


def _op_read(ref: str) -> str:
    """Resolve an op:// secret reference with the 1Password CLI.

    On failure, surface op's own stderr. CalledProcessError alone reports just an exit code,
    which turned every cause (locked app, bad vault, unusable item title) into the same
    unactionable message. Only stderr is quoted -- the secret is on stdout and is never shown.
    """
    out = subprocess.run(["op", "read", "--no-newline", ref], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"`op read` failed for {ref!r}: {out.stderr.strip() or f'exit {out.returncode}'}")
    if not out.stdout:
        raise RuntimeError(f"`op read` returned an empty value for {ref!r}")
    return out.stdout


def _keyring_read(key: str) -> str | None:
    """Read one field from the GNOME keyring. Returns None when unavailable, so the caller
    can fall through to the next source; never raises on a plain cache miss.

    A locked keyring makes secret-tool block on a GUI unlock prompt, which would hang a
    timer forever -- hence the timeout.
    """
    try:
        p = subprocess.run(
            ["secret-tool", "lookup", "service", KEYRING_SERVICE, "key", key],
            capture_output=True, text=True, timeout=20,
        )
    except FileNotFoundError:
        return None  # libsecret not installed
    except subprocess.TimeoutExpired:
        log.warning("secret-tool timed out reading %r; is the login keyring locked?", key)
        return None
    if p.returncode != 0 or not p.stdout:
        return None
    return p.stdout.rstrip("\n")


def keyring_write(key: str, value: str) -> None:
    """Store one field in the GNOME keyring. `value` is passed on stdin, never argv, so it
    cannot leak through the process table."""
    p = subprocess.run(
        ["secret-tool", "store", "--label", KEYRING_LABEL, "service", KEYRING_SERVICE, "key", key],
        input=value, capture_output=True, text=True, timeout=60,
    )
    if p.returncode != 0:
        raise RuntimeError(f"`secret-tool store` failed for {key!r}: {p.stderr.strip()[:200]}")


@dataclass
class Settings:
    home: Path = DEFAULT_HOME
    canvas_base: str = "https://lakota.instructure.com"
    hac_base: str = "https://hac.lakotainline.com/HomeAccess"
    onelogin_host: str = "lakota.onelogin.com"
    timezone: str = "America/New_York"
    headless: bool = True
    user_agent: str = ""   # blank => derive real Chrome UA from the Chromium binary
    cache_ttl_minutes: int = 180
    # Optional selector overrides if OneLogin changes its login page
    onelogin_user_selector: str = "input#username, input[name='username'], input[type='email']"
    onelogin_pass_selector: str = "input#password, input[name='password'], input[type='password']"
    onelogin_submit_selector: str = "button[type='submit'], input[type='submit']"
    # Lakota removed HAC's native login form; HAC is entered by launching its OneLogin
    # portal tile. Leave hac_app_url blank to discover the tile by name each run (app ids
    # are tenant-specific and change), or pin it once discovery is confirmed.
    onelogin_portal_path: str = "/portal/"
    hac_app_url: str = ""
    hac_app_pattern: str = r"home ?access|\bhac\b"
    _username: str | None = field(default=None, repr=False)
    _password: str | None = field(default=None, repr=False)

    @property
    def profile_dir(self) -> Path:
        return self.home / "browser-profile"

    @property
    def cache_dir(self) -> Path:
        return self.home / "cache"

    def credentials(self) -> tuple[str, str]:
        """Return (username, password). Resolved lazily and never logged."""
        if self._username and self._password:
            return self._username, self._password
        user = os.environ.get("LAKOTA_ONELOGIN_USERNAME")
        pw = os.environ.get("LAKOTA_ONELOGIN_PASSWORD")
        if not (user and pw):
            user = user or _keyring_read("username")
            pw = pw or _keyring_read("password")
        if not (user and pw):
            uref = os.environ.get("LAKOTA_OP_USERNAME_REF")
            pref = os.environ.get("LAKOTA_OP_PASSWORD_REF")
            if uref and pref:
                user, pw = user or _op_read(uref), pw or _op_read(pref)
        if not (user and pw):
            raise RuntimeError(
                "No credentials available. Run `lakota-grades set-credentials` to store them in "
                "the GNOME keyring, or provide LAKOTA_ONELOGIN_USERNAME/PASSWORD in the environment, "
                "or set LAKOTA_OP_USERNAME_REF/LAKOTA_OP_PASSWORD_REF for the 1Password CLI."
            )
        self._username, self._password = user, pw
        return user, pw


def load_settings() -> Settings:
    _load_env_files()
    s = Settings()
    s.canvas_base = os.environ.get("LAKOTA_CANVAS_BASE", s.canvas_base).rstrip("/")
    s.hac_base = os.environ.get("LAKOTA_HAC_BASE", s.hac_base).rstrip("/")
    s.onelogin_host = os.environ.get("LAKOTA_ONELOGIN_HOST", s.onelogin_host)
    s.headless = os.environ.get("LAKOTA_HEADLESS", "1") not in ("0", "false", "no")
    s.user_agent = os.environ.get("LAKOTA_USER_AGENT", s.user_agent)
    s.cache_ttl_minutes = int(os.environ.get("LAKOTA_CACHE_TTL_MINUTES", s.cache_ttl_minutes))
    s.hac_app_url = os.environ.get("LAKOTA_HAC_ONELOGIN_APP_URL", s.hac_app_url)
    s.hac_app_pattern = os.environ.get("LAKOTA_HAC_APP_PATTERN", s.hac_app_pattern)
    for k in ("onelogin_user_selector", "onelogin_pass_selector", "onelogin_submit_selector"):
        v = os.environ.get("LAKOTA_" + k.upper())
        if v:
            setattr(s, k, v)
    # 0700 from creation: this tree holds the browser profile's session cookies and the
    # kids' grades. mkdir's mode is masked by umask, so chmod explicitly as well.
    for d in (s.home, s.profile_dir, s.cache_dir):
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
        d.chmod(0o700)
    return s
