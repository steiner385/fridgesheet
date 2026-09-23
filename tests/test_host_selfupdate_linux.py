import pytest

from fridgesheet.host import selfupdate, selfupdate_linux


def test_linux_refuses_and_names_the_checkout_path():
    """Not absent -- absent means AttributeError somewhere less helpful."""
    with pytest.raises(selfupdate.UpdateError, match="git pull"):
        selfupdate_linux.spawn_installer(None, None)
