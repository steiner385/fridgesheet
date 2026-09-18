"""Configuration. Secrets are never stored here.

Credentials are read, in order of preference:
  1. From the environment (FRIDGESHEET_ONELOGIN_USERNAME / _PASSWORD), populated by a 1Password
     Environments mounted .env file, `op run --env-file=.env -- fridgesheet ...`, or a
     plain .env you manage yourself.
  2. From the OS credential store, via `host.credentials`: the GNOME keyring / freedesktop
     Secret Service through `secret-tool` on Linux, Windows Credential Manager through the
     `keyring` library on Windows. On Linux this is the default local store: encrypted at
     rest under the login password, unlocked by PAM at desktop login, and readable by an
     unattended systemd --user timer because the user manager already exports
     DBUS_SESSION_BUS_ADDRESS. If nobody has logged into the desktop session the keyring is
     locked and this source fails loudly rather than hanging on a prompt that no one can
     answer.
  3. From `op read` secret references (op://Vault/Item/field) if FRIDGESHEET_OP_USERNAME_REF /
     FRIDGESHEET_OP_PASSWORD_REF are set. Requires the 1Password CLI with desktop-app integration,
     so it needs someone present to approve the prompt -- fine interactively, not for a timer.
     Note: op:// references reject punctuation such as '(' in an item title, and percent-
     encoding does not help -- address such items by UUID (op://Vault/<uuid>/password).

Nothing in this module writes a secret to disk or logs it.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path

import tomllib
import tomli_w
from dotenv import load_dotenv

from . import host, migrate

log = logging.getLogger("fridgesheet.config")

# A parent's own units or .env may still say LAKOTA_*; honour them before anything below
# reads the environment (DEFAULT_HOME is computed at import). The new name wins if both
# are set. See migrate.py.
migrate.alias_legacy_env()

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]


class ConfigError(RuntimeError):
    pass


_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def _validate_report_time(key: str, value) -> None:
    """A [reports.<key>].time must be HH:MM, 24-hour. Raises ConfigError otherwise."""
    ok = False
    if _TIME_RE.match(str(value)):
        h, m = (int(x) for x in str(value).split(":"))
        ok = 0 <= h <= 23 and 0 <= m <= 59
    if not ok:
        raise ConfigError(f"[reports.{key}] time must be HH:MM (24-hour), got {value!r}")


def _default_home() -> Path:
    """~/.fridgesheet on Linux, %LOCALAPPDATA%\\fridgesheet on Windows; FRIDGESHEET_HOME wins."""
    if os.environ.get("FRIDGESHEET_HOME"):
        return Path(os.environ["FRIDGESHEET_HOME"])
    if host.IS_WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "fridgesheet"
    return Path.home() / ".fridgesheet"


DEFAULT_HOME = _default_home()


def env_file() -> Path:
    """The .env to load: FRIDGESHEET_ENV_FILE if set, else <home>/.env."""
    return Path(os.environ.get("FRIDGESHEET_ENV_FILE") or DEFAULT_HOME / ".env")


def config_file() -> Path:
    return DEFAULT_HOME / "config.toml"


def _load_env_files() -> None:
    for c in (env_file(), Path.cwd() / ".env"):
        if c.is_file():
            load_dotenv(c, override=False)
    migrate.alias_legacy_env()          # the .env may be an old one, written as LAKOTA_*


def _migrate_home_once() -> None:
    """The old app's data directory becomes this one's, once (migrate.py, spec section 3).

    Only when the home in use is the OS default. An override (`FRIDGESHEET_HOME`) or a
    test's redirected `DEFAULT_HOME` names a directory the old app never used, and the
    old default directory on that machine -- a developer's real data -- must be left alone.
    """
    if DEFAULT_HOME != _default_home():
        return
    old = migrate.legacy_home(is_windows=host.IS_WINDOWS)
    migrate.migrate_home(DEFAULT_HOME, old, link_old=not host.IS_WINDOWS)


def load_config_doc(path: Path) -> dict:
    """The raw config.toml as a dict. Missing file -> {}. Unparseable -> ConfigError naming the file."""
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"cannot parse {path}: {e}") from e


def save_config_doc(path: Path, doc: dict) -> None:
    """Write config.toml atomically. Never receives a password: callers keep it out of `doc`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".config-", suffix=".toml")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(tomli_w.dumps(doc).encode("utf-8"))
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def parse_nicknames(text: str) -> dict[str, str]:
    """'Alexander=Alex,Samantha=Sam' -> {'Alexander': 'Alex', 'Samantha': 'Sam'}."""
    out: dict[str, str] = {}
    for pair in (text or "").split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            if k.strip() and v.strip():
                out[k.strip()] = v.strip()
    return out


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
class ReportConfig:
    enabled: bool = False
    time: str | None = None          # None -> not set in config.toml; report_config() resolves it
    days: list[str] = field(default_factory=lambda: list(WEEKDAYS))
    printer: str = ""                # blank -> [print].printer -> the system default
    prints: bool = True              # False -> build and archive, never send it to a printer
    options: dict = field(default_factory=dict)      # report-specific, e.g. days_ahead, overdue_days


@dataclass
class Settings:
    home: Path = field(default_factory=lambda: DEFAULT_HOME)
    canvas_base: str = "https://lakota.instructure.com"
    hac_base: str = "https://hac.lakotainline.com/HomeAccess"
    onelogin_host: str = "lakota.onelogin.com"
    timezone: str = "America/New_York"
    headless: bool = True
    user_agent: str = ""
    cache_ttl_minutes: int = 180
    sheets_archive: str = ""
    username: str = ""                 # OneLogin username from config.toml; the password is in the OS store
    printer: str = ""                  # blank = the system default printer
    nicknames: dict[str, str] = field(default_factory=dict)
    reports: dict[str, ReportConfig] = field(default_factory=dict)
    web_host: str = "127.0.0.1"        # [web] host; bind address when allow_lan is off
    web_port: int = 8433
    web_allow_lan: bool = False        # [web] allow_lan; True binds 0.0.0.0 (spec section 8)
    web_host_explicit: bool = False    # FRIDGESHEET_WEB_HOST was set: that address wins over allow_lan
    #: [web] extra_hosts: additional `Host` header *names* to answer to under a wildcard bind.
    #: Addresses need no entry here -- every IP literal is already admitted (see
    #: `web.app._host_allowed`). This is for names, which cannot be admitted wholesale because
    #: a name is exactly what a DNS-rebinding attacker controls: Tailscale MagicDNS
    #: ("graphy.tailnet-1234.ts.net"), an mDNS ".local", or a hosts-file alias.
    web_extra_hosts: list[str] = field(default_factory=list)
    #: [web] check_updates: ask GitHub once a day whether a newer release exists (web/updates.py).
    #: The one call the app makes to anything but OneLogin, Canvas and HAC; a checkbox on Settings.
    web_check_updates: bool = True
    onelogin_user_selector: str = "input#username, input[name='username'], input[type='email']"
    onelogin_pass_selector: str = "input#password, input[name='password'], input[type='password']"
    onelogin_submit_selector: str = "button[type='submit'], input[type='submit']"
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

    def report_config(self, key: str, default_time: str = "14:00") -> ReportConfig:
        rc = self.reports.get(key) or ReportConfig()
        return replace(rc, time=default_time) if rc.time is None else rc

    @property
    def bind_host(self) -> str:
        """The address to bind. An explicit FRIDGESHEET_WEB_HOST wins over `allow_lan`, so
        `FRIDGESHEET_WEB_HOST=127.0.0.1` pins the server to loopback whatever config.toml says."""
        if self.web_host_explicit:
            return self.web_host
        return "0.0.0.0" if self.web_allow_lan else self.web_host

    def credentials(self) -> tuple[str, str]:
        """Return (username, password). Resolved lazily and never logged.
        Order: environment; config.toml username (or the store's) + the OS store; 1Password refs."""
        if self._username and self._password:
            return self._username, self._password
        from .host import credentials as store
        user = os.environ.get("FRIDGESHEET_ONELOGIN_USERNAME")
        pw = os.environ.get("FRIDGESHEET_ONELOGIN_PASSWORD")
        if not (user and pw):
            user = user or self.username or store.read_username()
            pw = pw or (store.read_password(user) if user else None)
        if not (user and pw):
            user, pw = self._legacy_credentials(user, pw, store)
        if not (user and pw):
            uref = os.environ.get("FRIDGESHEET_OP_USERNAME_REF")
            pref = os.environ.get("FRIDGESHEET_OP_PASSWORD_REF")
            if uref and pref:
                user, pw = user or _op_read(uref), pw or _op_read(pref)
        if not (user and pw):
            # The first sentence is the one a parent needs: this message is surfaced verbatim
            # on the Settings and Dashboard pages when a refresh fails, and until now it opened
            # by telling them to run a command they do not have -- `fridgesheet` is not on
            # PATH for anyone who installed the Windows app, where the executable is
            # FridgeSheet.exe. The CLI and environment routes still matter, and still follow,
            # for whoever is running this from a terminal.
            raise RuntimeError(
                "No credentials available. Enter your OneLogin username and password on the "
                "Settings page and save, then use Test login. "
                "(From a terminal instead: `fridgesheet set-credentials` to store them in the "
                "OS credential store, or FRIDGESHEET_ONELOGIN_USERNAME/PASSWORD in the environment, "
                "or FRIDGESHEET_OP_USERNAME_REF/FRIDGESHEET_OP_PASSWORD_REF for the 1Password CLI.)"
            )
        self._username, self._password = user, pw
        return user, pw

    @staticmethod
    def _legacy_credentials(user: str | None, pw: str | None, store) -> tuple[str | None, str | None]:
        """The entry the app stored under its old name, copied forward the first time it is
        needed so the next start finds it under the new one. The old entry is left as it is."""
        user = user or migrate.read_legacy_username(is_windows=host.IS_WINDOWS)
        if user and not pw:
            pw = migrate.read_legacy_password(user, is_windows=host.IS_WINDOWS)
            if pw:
                try:
                    store.write(user, pw)
                    log.info("copied the OneLogin credential entry to the new service name")
                except Exception as e:  # noqa: BLE001  the copy is a courtesy; the login still works
                    log.warning("could not copy the credential entry to the new name: %s", e)
        return user, pw


def settings_from_doc(doc: dict, s: Settings) -> None:
    """Apply config.toml. Unknown sections and keys are ignored so a newer file works with an older app."""
    raw_acct, raw_prn, raw_kids = doc.get("account"), doc.get("print"), doc.get("kids")
    acct = raw_acct if isinstance(raw_acct, dict) else {}
    prn = raw_prn if isinstance(raw_prn, dict) else {}
    kids = raw_kids if isinstance(raw_kids, dict) else {}
    s.username = str(acct.get("username", s.username))
    s.printer = str(prn.get("printer", s.printer))
    s.sheets_archive = str(prn.get("archive", s.sheets_archive))
    nick = kids.get("nicknames") or {}
    s.nicknames = {str(k): str(v) for k, v in nick.items()} if isinstance(nick, dict) else {}
    raw_web = doc.get("web")
    web = raw_web if isinstance(raw_web, dict) else {}
    s.web_host = str(web.get("host", s.web_host))
    s.web_allow_lan = bool(web.get("allow_lan", s.web_allow_lan))
    s.web_check_updates = bool(web.get("check_updates", s.web_check_updates))
    raw_extra = web.get("extra_hosts")
    if isinstance(raw_extra, list):
        # Lowercased on the way in: `urlsplit` lowercases an incoming Host, so a name typed
        # here with capitals would otherwise never match the request it was written for.
        s.web_extra_hosts = [str(h).strip().lower() for h in raw_extra if str(h).strip()]
    try:
        s.web_port = int(web.get("port", s.web_port))
    except (TypeError, ValueError):
        pass
    raw_reports = doc.get("reports")
    for key, sect in (raw_reports if isinstance(raw_reports, dict) else {}).items():
        if not isinstance(sect, dict):
            continue
        known = {"enabled", "time", "days", "printer", "print"}
        time_val = sect.get("time")
        if time_val is not None:
            _validate_report_time(key, time_val)
            time_val = str(time_val)
        # A value of the wrong *shape* keeps the default here, the way `[web].port` and
        # `[kids].nicknames` above already do; only a `time` that is not a time is worth a
        # `ConfigError`, because a schedule installed at the wrong hour is worse than none.
        # `days` used to be read straight off the document, so `days = 5` raised a bare
        # `TypeError: 'int' object is not iterable` and `days = "Mon"` quietly became
        # ["M", "o", "n"] -- and a `TypeError` out of here is a traceback in `schedule remove
        # --all`, which the uninstaller runs hidden with its exit code discarded, orphaning
        # every scheduled task. Same reasoning for a `reports` key that is not a table at all.
        raw_days = sect.get("days", WEEKDAYS)
        days = [str(d) for d in raw_days] if isinstance(raw_days, (list, tuple)) else list(WEEKDAYS)
        s.reports[key] = ReportConfig(
            enabled=bool(sect.get("enabled", False)),
            time=time_val,
            days=days,
            printer=str(sect.get("printer", "") or ""),
            prints=bool(sect.get("print", True)),
            options={k: v for k, v in sect.items() if k not in known},
        )


def load_settings() -> Settings:
    _load_env_files()
    s = Settings()
    doc = load_config_doc(config_file())      # already names the file on a parse error
    try:
        settings_from_doc(doc, s)
    except ConfigError as e:
        raise ConfigError(f"{config_file()}: {e}") from e
    s.canvas_base = os.environ.get("FRIDGESHEET_CANVAS_BASE", s.canvas_base).rstrip("/")
    s.hac_base = os.environ.get("FRIDGESHEET_HAC_BASE", s.hac_base).rstrip("/")
    s.onelogin_host = os.environ.get("FRIDGESHEET_ONELOGIN_HOST", s.onelogin_host)
    s.headless = os.environ.get("FRIDGESHEET_HEADLESS", "1") not in ("0", "false", "no")
    s.user_agent = os.environ.get("FRIDGESHEET_USER_AGENT", s.user_agent)
    s.cache_ttl_minutes = int(os.environ.get("FRIDGESHEET_CACHE_TTL_MINUTES", s.cache_ttl_minutes))
    s.sheets_archive = os.environ.get("FRIDGESHEET_SHEETS_ARCHIVE", s.sheets_archive).strip()
    s.printer = os.environ.get("FRIDGESHEET_PRINTER", s.printer).strip()
    env_host = os.environ.get("FRIDGESHEET_WEB_HOST")
    if env_host:
        s.web_host, s.web_host_explicit = env_host, True
        if env_host == "0.0.0.0":
            s.web_allow_lan = True
    try:
        s.web_port = int(os.environ.get("FRIDGESHEET_WEB_PORT", s.web_port))
    except ValueError:
        pass
    s.nicknames = {**s.nicknames, **parse_nicknames(os.environ.get("FRIDGESHEET_NICKNAMES", ""))}
    s.hac_app_url = os.environ.get("FRIDGESHEET_HAC_ONELOGIN_APP_URL", s.hac_app_url)
    s.hac_app_pattern = os.environ.get("FRIDGESHEET_HAC_APP_PATTERN", s.hac_app_pattern)
    for k in ("onelogin_user_selector", "onelogin_pass_selector", "onelogin_submit_selector"):
        v = os.environ.get("FRIDGESHEET_" + k.upper())
        if v:
            setattr(s, k, v)
    _migrate_home_once()
    for d in (s.home, s.profile_dir, s.cache_dir):
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
        d.chmod(0o700)
    return s
