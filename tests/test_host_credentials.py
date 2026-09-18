# tests/test_host_credentials.py
"""The OS password store. Linux = secret-tool (unchanged from the original config.py);
Windows = the keyring library's Credential Manager backend. Neither is touched here:
`run` and the keyring module are faked."""
from __future__ import annotations

import subprocess
import types

import pytest

from fridgesheet import config
from fridgesheet.host import credentials, credentials_linux, credentials_windows


class _R:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def test_linux_reads_with_secret_tool_lookup():
    seen = []

    def run(cmd, **kw):
        seen.append((cmd, kw))
        return _R(0, "hunter2\n")

    assert credentials_linux.read_password("ignored", run=run) == "hunter2"
    cmd, kw = seen[0]
    assert cmd == ["secret-tool", "lookup", "service", credentials.SERVICE, "key", "password"]
    assert kw.get("timeout") == 20


def test_linux_read_returns_none_when_secret_tool_is_missing_or_fails():
    def missing(cmd, **kw):
        raise FileNotFoundError
    assert credentials_linux.read_password("x", run=missing) is None
    assert credentials_linux.read_username(run=lambda c, **k: _R(1)) is None

    def slow(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 20)
    assert credentials_linux.read_password("x", run=slow) is None


def test_linux_write_passes_the_secret_on_stdin_not_argv():
    seen = []

    def run(cmd, **kw):
        seen.append((cmd, kw))
        return _R(0)

    credentials_linux.write("p@x.com", "hunter2", run=run)
    assert [c[0][:2] for c in seen] == [["secret-tool", "store"], ["secret-tool", "store"]]
    for cmd, kw in seen:
        assert "hunter2" not in " ".join(cmd) and kw["input"] in ("p@x.com", "hunter2")
    assert seen[0][0][-2:] == ["key", "username"] and seen[1][0][-2:] == ["key", "password"]


def test_linux_write_failure_raises_without_the_secret():
    with pytest.raises(RuntimeError) as e:
        credentials_linux.write("u", "hunter2", run=lambda c, **k: _R(1, "", "locked"))
    assert "locked" in str(e.value) and "hunter2" not in str(e.value)


@pytest.fixture
def fake_keyring(monkeypatch):
    store = {}
    mod = types.SimpleNamespace(
        get_password=lambda svc, user: store.get((svc, user)),
        set_password=lambda svc, user, pw: store.__setitem__((svc, user), pw),
    )
    monkeypatch.setattr(credentials_windows, "_keyring", lambda: mod)
    return store


def test_windows_round_trip_through_keyring(fake_keyring):
    credentials_windows.write("p@x.com", "hunter2")
    assert fake_keyring == {(credentials.SERVICE, "p@x.com"): "hunter2"}
    assert credentials_windows.read_password("p@x.com") == "hunter2"
    assert credentials_windows.read_password("nobody") is None
    assert credentials_windows.read_username() is None     # the username lives in config.toml


def test_windows_keyring_errors_degrade_like_linux(monkeypatch):
    class Boom:
        def get_password(self, svc, user):
            raise RuntimeError("No recommended backend was available")
        def set_password(self, svc, user, pw):
            raise RuntimeError("backend locked")
    monkeypatch.setattr(credentials_windows, "_keyring", lambda: Boom())
    assert credentials_windows.read_password("p@x.com") is None
    with pytest.raises(RuntimeError) as e:
        credentials_windows.write("p@x.com", "hunter2")
    assert "backend locked" in str(e.value) and "hunter2" not in str(e.value)


def test_settings_credentials_prefers_env_then_store(monkeypatch):
    monkeypatch.delenv("FRIDGESHEET_ONELOGIN_USERNAME", raising=False)
    monkeypatch.delenv("FRIDGESHEET_ONELOGIN_PASSWORD", raising=False)
    monkeypatch.delenv("FRIDGESHEET_OP_USERNAME_REF", raising=False)
    monkeypatch.delenv("FRIDGESHEET_OP_PASSWORD_REF", raising=False)
    monkeypatch.setattr(credentials, "read_username", lambda run=None: None)
    monkeypatch.setattr(credentials, "read_password", lambda user, run=None: "stored" if user == "cfg@x.com" else None)
    s = config.Settings(username="cfg@x.com")
    assert s.credentials() == ("cfg@x.com", "stored")
    monkeypatch.setenv("FRIDGESHEET_ONELOGIN_USERNAME", "env@x.com")
    monkeypatch.setenv("FRIDGESHEET_ONELOGIN_PASSWORD", "envpw")
    assert config.Settings(username="cfg@x.com").credentials() == ("env@x.com", "envpw")


def test_settings_credentials_falls_back_to_store_username_then_errors(monkeypatch):
    for k in ("FRIDGESHEET_ONELOGIN_USERNAME", "FRIDGESHEET_ONELOGIN_PASSWORD", "FRIDGESHEET_OP_USERNAME_REF", "FRIDGESHEET_OP_PASSWORD_REF"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(credentials, "read_username", lambda run=None: "ring@x.com")
    monkeypatch.setattr(credentials, "read_password", lambda user, run=None: "ringpw")
    assert config.Settings().credentials() == ("ring@x.com", "ringpw")
    monkeypatch.setattr(credentials, "read_username", lambda run=None: None)
    with pytest.raises(RuntimeError) as e:
        config.Settings().credentials()
    assert "set-credentials" in str(e.value)
