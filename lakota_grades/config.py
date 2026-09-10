"""Configuration. Secrets are never stored here.

Credentials are read, in order of preference:
  1. From the environment (populated by a 1Password Environments mounted .env file,
     or by `op run --env-file=.env -- lakota-grades ...`).
  2. From `op read` secret references (op://Vault/Item/field) if LAKOTA_OP_USERNAME_REF /
     LAKOTA_OP_PASSWORD_REF are set. Requires the 1Password CLI with desktop-app integration.
     Note: op:// references reject punctuation such as '(' in an item title, and percent-
     encoding does not help -- address such items by UUID (op://Vault/<uuid>/password).

Nothing in this module writes a secret to disk or logs it.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_HOME = Path(os.environ.get("LAKOTA_GRADES_HOME", Path.home() / ".lakota-grades"))


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


@dataclass
class Settings:
    home: Path = DEFAULT_HOME
    canvas_base: str = "https://lakota.instructure.com"
    hac_base: str = "https://hac.lakotainline.com/HomeAccess"
    onelogin_host: str = "lakota.onelogin.com"
    timezone: str = "America/New_York"
    headless: bool = True
    cache_ttl_minutes: int = 180
    # Optional selector overrides if OneLogin changes its login page
    onelogin_user_selector: str = "input#username, input[name='username'], input[type='email']"
    onelogin_pass_selector: str = "input#password, input[name='password'], input[type='password']"
    onelogin_submit_selector: str = "button[type='submit'], input[type='submit']"
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
            uref = os.environ.get("LAKOTA_OP_USERNAME_REF")
            pref = os.environ.get("LAKOTA_OP_PASSWORD_REF")
            if uref and pref:
                user, pw = _op_read(uref), _op_read(pref)
        if not (user and pw):
            raise RuntimeError(
                "No credentials available. Provide LAKOTA_ONELOGIN_USERNAME/PASSWORD via a 1Password "
                "mounted .env, `op run`, or set LAKOTA_OP_USERNAME_REF/LAKOTA_OP_PASSWORD_REF."
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
    s.cache_ttl_minutes = int(os.environ.get("LAKOTA_CACHE_TTL_MINUTES", s.cache_ttl_minutes))
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
