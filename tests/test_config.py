"""The optional .env under the lakota-grades home must load without anyone having to
export LAKOTA_ENV_FILE. Claude Desktop rewrites its config on exit and can drop the
`env` block, and a systemd unit copied by hand may lose the Environment= line; either
way the server silently ran without its settings."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from lakota_grades import config

MARKER = "LAKOTA_TEST_MARKER"


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """A fake lakota-grades home and a fake cwd, each holding a .env with a different marker."""
    monkeypatch.delenv("LAKOTA_ENV_FILE", raising=False)
    monkeypatch.delenv(MARKER, raising=False)
    home = tmp_path / "home"
    home.mkdir()
    (home / ".env").write_text(f"{MARKER}=home\n")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    (cwd / ".env").write_text(f"{MARKER}=cwd\n")
    monkeypatch.setattr(config, "DEFAULT_HOME", home)
    monkeypatch.chdir(cwd)
    return home, cwd


def test_env_file_defaults_to_home_dotenv_when_unset(isolated):
    home, _ = isolated
    assert config.env_file() == home / ".env"


def test_env_file_honours_explicit_setting(isolated, monkeypatch, tmp_path):
    explicit = tmp_path / "elsewhere.env"
    monkeypatch.setenv("LAKOTA_ENV_FILE", str(explicit))
    assert config.env_file() == explicit


def test_home_dotenv_beats_cwd_dotenv_when_unset(isolated):
    config._load_env_files()
    assert os.environ[MARKER] == "home"


def test_explicit_env_file_beats_home_dotenv(isolated, monkeypatch, tmp_path):
    explicit = tmp_path / "elsewhere.env"
    explicit.write_text(f"{MARKER}=explicit\n")
    monkeypatch.setenv("LAKOTA_ENV_FILE", str(explicit))
    config._load_env_files()
    assert os.environ[MARKER] == "explicit"


def test_missing_default_env_file_is_not_an_error(isolated):
    home, _ = isolated
    (home / ".env").unlink()
    config._load_env_files()  # falls through to cwd/.env, silently
    assert os.environ[MARKER] == "cwd"
