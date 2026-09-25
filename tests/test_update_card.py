"""#145: the Updates card. Off Windows it never offers a button the route would refuse, and
says how to update instead; the "set a PIN" hint sits beside the PIN field; the PIN check
trims like the setter; a PIN is at least four characters and can be removed."""
from __future__ import annotations

from fridgesheet import host
from fridgesheet.web import jobs, updatepin
from tests.test_web_settings_page import FakeCred, _app_with_update, _form
from tests.web_fixtures import app_for, seed


def _post_settings(c, **over):
    # Never the real OS keyring: every POST /settings goes through a fake credential store.
    c.app.state.fridgesheet.extra["credstore"] = FakeCred()
    return c.post("/settings", data=_form(**over))


def test_off_windows_there_is_no_update_button_and_the_page_says_how_to_update(tmp_path, monkeypatch):
    """With checks on, a PIN set and the service installed, Linux got "Update to X" and then a
    409 on the click. The card says what to do on a source checkout instead."""
    monkeypatch.setattr(host, "IS_WINDOWS", False)
    c = _app_with_update(tmp_path, pin=updatepin.hash_pin("2468"))
    body = c.get("/settings").text
    assert 'action="/settings/update"' not in body
    assert "Update to 9.9.9" not in body
    assert "git pull" in body and "pip install -e ." in body
    assert "Set an update PIN" not in body                      # no PIN would help here


def test_off_windows_the_status_line_does_not_offer_the_exe(tmp_path, monkeypatch):
    """The line linked the `.exe` with "Run it over this one" -- Windows instructions on a
    Linux page. There it names the release and the two commands instead, both on the page
    and in what "Check for updates now" swaps in."""
    monkeypatch.setattr(host, "IS_WINDOWS", False)
    c = _app_with_update(tmp_path, pin=updatepin.hash_pin("2468"))
    for body in (c.get("/settings").text, c.post("/settings/update/check").text):
        assert "9.9.9 is available" in body
        assert "download the installer" not in body and "Run it over this one" not in body
        assert "releases" in body and "git pull" in body


def test_on_windows_the_status_line_still_offers_the_installer(tmp_path, monkeypatch):
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    c = _app_with_update(tmp_path, pin=updatepin.hash_pin("2468"))
    body = c.get("/settings").text
    assert "download the installer" in body and "Update to 9.9.9" in body
    assert "git pull" not in body


def test_the_pin_hint_sits_beside_the_pin_field_not_after_the_card(tmp_path, monkeypatch):
    """"Set an update PIN below" rendered under the card that held the field -- pointing up."""
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    body = _app_with_update(tmp_path).get("/settings").text
    hint, field, below = body.index("Set an update PIN below"), body.index('name="update_pin"'), body.index('class="settings-below"')
    assert hint < field < below


def test_the_pin_check_trims_like_the_setter(tmp_path, monkeypatch):
    """The setter stores `pin.strip()`; a phone keyboard's trailing space then failed the check
    and counted towards the lockout."""
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    seed(tmp_path, update_pin_hash=updatepin.hash_pin("2468"))
    c = app_for(tmp_path)
    c.app.state.fridgesheet.jobs = jobs.Worker(c.app.state.fridgesheet)   # never started: nothing runs
    assert c.post("/settings/update", data={"pin": " 2468 "}).status_code == 200


def test_a_pin_shorter_than_four_characters_is_refused_and_nothing_is_written(tmp_path):
    seed(tmp_path)
    c = app_for(tmp_path)
    r = _post_settings(c, update_pin="12")
    assert "must be at least 4" in r.text
    assert not (tmp_path / "config.toml").exists()                        # the whole save was refused
    assert c.app.state.fridgesheet.extra["credstore"].written == []


def test_a_pin_of_four_is_accepted(tmp_path):
    seed(tmp_path)
    c = app_for(tmp_path)
    r = _post_settings(c, update_pin="2468")
    assert "must be at least 4" not in r.text and "Update PIN stored." in r.text
    assert "update_pin_hash" in (tmp_path / "config.toml").read_text(encoding="utf-8")


def test_the_pin_can_be_removed(tmp_path):
    stored = updatepin.hash_pin("2468")
    seed(tmp_path, update_pin_hash=stored)
    c = app_for(tmp_path)
    body = c.get("/settings").text
    assert 'name="clear_update_pin"' in body                                # offered while one is stored
    r = _post_settings(c, clear_update_pin="on")
    assert "Update PIN removed." in r.text
    assert "update_pin_hash" not in (tmp_path / "config.toml").read_text(encoding="utf-8")
    assert 'name="clear_update_pin"' not in r.text                          # nothing left to remove


def test_no_remove_box_when_no_pin_is_stored(tmp_path):
    seed(tmp_path)
    assert 'name="clear_update_pin"' not in app_for(tmp_path).get("/settings").text


def test_typing_a_new_pin_and_removing_it_at_once_is_refused(tmp_path):
    stored = updatepin.hash_pin("2468")
    seed(tmp_path, update_pin_hash=stored)
    c = app_for(tmp_path)
    r = _post_settings(c, update_pin="1357", clear_update_pin="on")
    assert "not both" in r.text
    assert stored in (tmp_path / "config.toml").read_text(encoding="utf-8")
