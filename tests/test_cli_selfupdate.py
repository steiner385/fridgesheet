import pytest

from fridgesheet import cli
from fridgesheet.host import ServiceInfo


class Args:
    check = False
    force = False


def test_it_refuses_when_another_account_owns_the_install(capsys, monkeypatch):
    """Seen on the household's Windows box, 2026-09-22: the logon task runs as one
    account while an SSH session arrives as another. A per-user installer would build a
    second copy under the wrong profile and report success -- the worst failure, because
    nothing visible changes."""
    monkeypatch.setattr(cli, "_current_user", lambda: "tony")
    monkeypatch.setattr(cli, "_service_info",
                        lambda: ServiceInfo("task-scheduler", True, True, "running", owner="houserunner"))
    assert cli.cmd_self_update(Args()) == 1
    err = capsys.readouterr().err
    assert "houserunner" in err and "tony" in err


def test_force_proceeds_anyway(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_current_user", lambda: "tony")
    monkeypatch.setattr(cli, "_service_info",
                        lambda: ServiceInfo("task-scheduler", True, True, "running", owner="houserunner"))
    monkeypatch.setattr(cli, "_do_self_update", lambda **kw: calls.append(kw) or 0)
    args = Args()
    args.force = True
    assert cli.cmd_self_update(args) == 0 and calls


def test_the_owner_running_it_is_not_refused(monkeypatch):
    monkeypatch.setattr(cli, "_current_user", lambda: "houserunner")
    monkeypatch.setattr(cli, "_service_info",
                        lambda: ServiceInfo("task-scheduler", True, True, "running", owner="houserunner"))
    monkeypatch.setattr(cli, "_do_self_update", lambda **kw: 0)
    assert cli.cmd_self_update(Args()) == 0


def test_an_unknown_owner_is_not_treated_as_a_mismatch(monkeypatch):
    """Linux, or a schtasks response without the field. Refusing here would refuse always."""
    monkeypatch.setattr(cli, "_current_user", lambda: "tony")
    monkeypatch.setattr(cli, "_service_info",
                        lambda: ServiceInfo("task-scheduler", True, True, "running", owner=""))
    monkeypatch.setattr(cli, "_do_self_update", lambda **kw: 0)
    assert cli.cmd_self_update(Args()) == 0


def test_an_unverifiable_current_user_is_refused_not_assumed(monkeypatch):
    """getpass.getuser() can fail. Knowing an owner exists and being unable to confirm we
    are it is a reason to stop -- proceeding would build a second install under whatever
    profile this shell happens to have, and report success."""
    monkeypatch.setattr(cli, "_current_user", lambda: "")
    monkeypatch.setattr(cli, "_service_info",
                        lambda: ServiceInfo("task-scheduler", True, True, "running", owner="houserunner"))
    assert cli.cmd_self_update(Args()) == 1


def test_force_still_overrides_an_unverifiable_current_user(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_current_user", lambda: "")
    monkeypatch.setattr(cli, "_service_info",
                        lambda: ServiceInfo("task-scheduler", True, True, "running", owner="houserunner"))
    monkeypatch.setattr(cli, "_do_self_update", lambda **kw: calls.append(kw) or 0)
    args = Args(); args.force = True
    assert cli.cmd_self_update(args) == 0 and calls
