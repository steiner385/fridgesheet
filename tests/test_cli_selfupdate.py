import pytest

from fridgesheet import cli, host
from fridgesheet.host import ServiceInfo


class Args:
    check = False
    force = False


def test_it_refuses_on_a_non_windows_host_before_doing_anything(capsys, monkeypatch):
    """README already advertises `self-update` as Windows-only. This must refuse before
    even `--check`, and before `_service_info`/`_current_user` are consulted -- not be
    discovered last, wherever the flow happens to fail first."""
    monkeypatch.setattr(host, "IS_WINDOWS", False)
    calls = []
    monkeypatch.setattr(cli, "_service_info", lambda: calls.append("service_info"))
    monkeypatch.setattr(cli, "_current_user", lambda: calls.append("current_user"))
    monkeypatch.setattr(cli, "_do_self_update", lambda **kw: calls.append(("do", kw)) or 0)
    assert cli.cmd_self_update(Args()) == 1
    assert calls == []
    err = capsys.readouterr().err
    assert "Windows" in err


def test_it_refuses_on_a_non_windows_host_even_for_check(capsys, monkeypatch):
    """README says `--check` "reports what's available and installs nothing", but the whole
    command is still marked "(Windows only)" -- `--check` must refuse too."""
    monkeypatch.setattr(host, "IS_WINDOWS", False)
    args = Args()
    args.check = True
    assert cli.cmd_self_update(args) == 1
    assert "Windows" in capsys.readouterr().err


def test_it_refuses_when_another_account_owns_the_install(capsys, monkeypatch):
    """Seen on the household's Windows box, 2026-09-22: the logon task runs as one
    account while an SSH session arrives as another. A per-user installer would build a
    second copy under the wrong profile and report success -- the worst failure, because
    nothing visible changes."""
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    monkeypatch.setattr(cli, "_current_user", lambda: "tony")
    monkeypatch.setattr(cli, "_service_info",
                        lambda: ServiceInfo("task-scheduler", True, True, "running", owner="houserunner"))
    assert cli.cmd_self_update(Args()) == 1
    err = capsys.readouterr().err
    assert "houserunner" in err and "tony" in err


def test_force_proceeds_anyway(monkeypatch):
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    calls = []
    monkeypatch.setattr(cli, "_current_user", lambda: "tony")
    monkeypatch.setattr(cli, "_service_info",
                        lambda: ServiceInfo("task-scheduler", True, True, "running", owner="houserunner"))
    monkeypatch.setattr(cli, "_do_self_update", lambda **kw: calls.append(kw) or 0)
    args = Args()
    args.force = True
    assert cli.cmd_self_update(args) == 0 and calls


def test_the_owner_running_it_is_not_refused(monkeypatch):
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    monkeypatch.setattr(cli, "_current_user", lambda: "houserunner")
    monkeypatch.setattr(cli, "_service_info",
                        lambda: ServiceInfo("task-scheduler", True, True, "running", owner="houserunner"))
    monkeypatch.setattr(cli, "_do_self_update", lambda **kw: 0)
    assert cli.cmd_self_update(Args()) == 0


def test_an_unknown_owner_is_not_treated_as_a_mismatch(monkeypatch):
    """Linux, or a schtasks response without the field. Refusing here would refuse always."""
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    monkeypatch.setattr(cli, "_current_user", lambda: "tony")
    monkeypatch.setattr(cli, "_service_info",
                        lambda: ServiceInfo("task-scheduler", True, True, "running", owner=""))
    monkeypatch.setattr(cli, "_do_self_update", lambda **kw: 0)
    assert cli.cmd_self_update(Args()) == 0


def test_an_unverifiable_current_user_is_refused_not_assumed(monkeypatch):
    """getpass.getuser() can fail. Knowing an owner exists and being unable to confirm we
    are it is a reason to stop -- proceeding would build a second install under whatever
    profile this shell happens to have, and report success."""
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    monkeypatch.setattr(cli, "_current_user", lambda: "")
    monkeypatch.setattr(cli, "_service_info",
                        lambda: ServiceInfo("task-scheduler", True, True, "running", owner="houserunner"))
    assert cli.cmd_self_update(Args()) == 1


def test_force_still_overrides_an_unverifiable_current_user(monkeypatch):
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    calls = []
    monkeypatch.setattr(cli, "_current_user", lambda: "")
    monkeypatch.setattr(cli, "_service_info",
                        lambda: ServiceInfo("task-scheduler", True, True, "running", owner="houserunner"))
    monkeypatch.setattr(cli, "_do_self_update", lambda **kw: calls.append(kw) or 0)
    args = Args(); args.force = True
    assert cli.cmd_self_update(args) == 0 and calls
