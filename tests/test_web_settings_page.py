"""Settings: the form round-trips config.toml, the password stays on this machine, the editors validate."""
from __future__ import annotations

import json
import tomllib
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from fridgesheet import config, host
from fridgesheet.web import app as webapp, updatepin
from tests.web_fixtures import LOCAL_HOST_HEADERS, app_for, seed


class FakeCred:
    def __init__(self):
        self.written = []
    def write(self, user, pw):
        self.written.append((user, pw))
    def read_username(self):
        return self.written[-1][0] if self.written else None


def _client(home, host="127.0.0.1"):
    seed(home).close()
    (home / "config.toml").write_text('[account]\nusername = "parent@example.org"\n[print]\nprinter = "Brother"\n[kids]\nnicknames = { Alex = "Al" }\n')
    s = config.Settings(home=home)
    config.settings_from_doc(config.load_config_doc(home / "config.toml"), s)
    application = webapp.create_app(s, worker=False)
    application.state.fridgesheet.extra["credstore"] = FakeCred()
    application.state.fridgesheet.extra["printers"] = ["Brother", "Canon"]
    return TestClient(application, client=(host, 12345), headers=LOCAL_HOST_HEADERS), application


FORM = {"username": "parent@example.org", "password": "", "printer": "Canon", "days_ahead": "10",
        "overdue_days": "21", "nicknames": "Alex=Al", "archive": "", "port": "8433"}


def _form(**over):
    """FORM's shape with a password filled in -- `app_for`'s home has no `[account] username`
    yet, so `actions.validate` treats the very first save like any other new account and
    requires one (the same rule `test_web_updates.py::test_saving_settings_round_trips_the_checkbox`
    exercises). Callers only need to override what the test is actually about."""
    return {**FORM, "password": "hunter2", **over}


def _release_fetch(tag="v9.9.9"):
    """The same shape `tests/test_web_updates.py::release` builds -- a fake `update_fetch`
    that answers with a real release body, so `updates.check` reports one genuinely
    available instead of the "no network in tests" `conftest._no_github` gives every other
    test by default."""
    body = {"tag_name": tag, "html_url": f"https://github.com/x/releases/tag/{tag}",
            "assets": [{"name": f"FridgeSheet-Setup-{tag[1:]}.exe",
                        "browser_download_url": f"https://github.com/x/releases/download/{tag}/FridgeSheet-Setup-{tag[1:]}.exe"}]}
    return lambda url: json.dumps(body).encode()


def _app_with_update(tmp_path, *, pin=None, check_updates=None, service_installed=True, tag="v9.9.9"):
    """A client whose update check reports `tag` as available -- through the button's own
    guards, not around them. Every button test needs a genuine update on offer: otherwise
    "no button" is just as true of `update.available` being False by default
    (`conftest._no_github`) as it is of whatever guard the test claims to be exercising, and
    the assertion cannot tell the two apart."""
    kwargs = {}
    if pin is not None:
        kwargs["update_pin_hash"] = pin
    if check_updates is not None:
        kwargs["check_updates"] = check_updates
    seed(tmp_path, **kwargs)
    c = app_for(tmp_path, service_installed=service_installed)
    c.app.state.fridgesheet.extra["update_fetch"] = _release_fetch(tag)
    return c


def test_a_host_header_this_app_does_not_answer_to_is_refused(tmp_path):
    """The same-origin check compares Origin to Host, so an attacker domain resolving to
    127.0.0.1 satisfies it -- both headers say `evil.example` and they match. Spec section 8
    accepts network isolation as the boundary, but the host we answer to is knowable, so
    checking it costs little and closes a hole that the loopback password gate is behind."""
    c, _ = _client(tmp_path)
    r = c.post("/settings", data={**FORM}, headers={"Host": "evil.example", "Origin": "http://evil.example"})
    assert r.status_code == 403


def test_the_addresses_this_app_does_answer_to_are_accepted(tmp_path):
    c, _ = _client(tmp_path)
    for host in ("127.0.0.1:8433", "localhost:8433", "127.0.0.1"):
        r = c.post("/settings", data={**FORM}, headers={"Host": host, "Origin": f"http://{host}"})
        assert r.status_code != 403, host


def test_the_lan_address_is_accepted_only_when_the_toggle_is_on(monkeypatch, tmp_path):
    """The QR code Plan E built points a phone at this machine's LAN address, and the toggle
    that turns the LAN bind on is exactly what makes that `Host` legitimate. The probe is
    injected through `actions._lan_probe`, the same seam `lan_url`'s own tests use, so this
    never reaches a real socket."""
    from fridgesheet.web import actions
    monkeypatch.setattr(actions, "_lan_probe", lambda: "192.168.1.42")
    c, app = _client(tmp_path)
    headers = {"Host": "192.168.1.42:8433", "Origin": "http://192.168.1.42:8433"}
    assert c.post("/settings", data={**FORM}, headers=headers).status_code == 403   # allow_lan is off
    app.state.fridgesheet.settings.web_allow_lan = True
    assert c.post("/settings", data={**FORM}, headers=headers).status_code != 403


def test_a_network_probe_can_no_longer_lock_a_device_out_at_all(monkeypatch, tmp_path):
    """These two conditions used to need a memo to survive; now they need nothing.

    `_allowed_hosts` once called `actions.lan_url()` on every request under a wildcard bind, so
    a transient `OSError` (a Wi-Fi blip, a VPN coming up) dropped the LAN address out of the
    allowlist and the phone the QR code points at started getting 403s mid-session with nothing
    logged. That was patched with a probe-once memo, which in turn could never invalidate.

    Admission no longer consults the network: an IP literal is admitted by rule under a
    wildcard bind. So a probe that always fails changes nothing, and -- the part the memo
    existed for -- the probe is not called on the request path at all. Both halves of the old
    pair of tests, stated as the one property that replaced them. #38."""
    from fridgesheet.web import actions
    calls = []

    def never_works():
        calls.append(1)
        raise OSError("the network is down")
    monkeypatch.setattr(actions, "_lan_probe", never_works)
    monkeypatch.setattr(actions, "_tailnet_probe", never_works)

    c, app = _client(tmp_path)
    app.state.fridgesheet.settings.web_allow_lan = True
    headers = {"Host": "192.168.1.42:8433", "Origin": "http://192.168.1.42:8433"}

    for _ in range(4):
        assert c.get("/", headers=headers).status_code == 200
    assert calls == [], "admission must not touch the network"


def test_every_local_address_is_admitted_not_only_the_one_on_the_default_route(tmp_path):
    """The bug this replaced the probe to fix: a machine on both a house network and a tailnet
    answers on both, but `_lan_probe` returns whichever address the *default route* uses, so
    the other one got a bare 403 from an app that was listening on it the whole time.

    Observed on a real host (graphy, 2026-09-17): `192.168.243.201` answered and
    `100.107.58.120` -- same process, same socket, bound `0.0.0.0` -- did not. #38."""
    c, app = _client(tmp_path)
    app.state.fridgesheet.settings.web_allow_lan = True
    for addr in ("192.168.243.201", "100.107.58.120", "10.0.0.5", "172.16.3.9", "[fd7a:115c:a1e0::1]"):
        r = c.get("/", headers={"Host": f"{addr}:8433"})
        assert r.status_code == 200, f"{addr} is an address this app is served on"


def test_a_name_is_still_refused_under_a_wildcard_bind(tmp_path):
    """The security property the IP-literal rule must not cost. DNS rebinding is an attack on
    *names*: it points a name the attacker owns at an address they do not, so the browser's
    same-origin policy -- which compares names -- hands them our responses. A bare address
    cannot carry that attack, which is why every address may be admitted while every
    unlisted name may not."""
    c, app = _client(tmp_path)
    app.state.fridgesheet.settings.web_allow_lan = True
    for name in ("evil.example", "graphy", "192.168.1.42.evil.example", "0x7f000001", "127.0.0.1.evil.example"):
        assert c.get("/", headers={"Host": f"{name}:8433"}).status_code == 403, name


def test_extra_hosts_admits_a_magicdns_name_and_only_that_name(tmp_path):
    """Names cannot be admitted wholesale, but a parent reaching the app over Tailscale
    MagicDNS is typing one. `[web] extra_hosts` is the closed list for that case."""
    c, app = _client(tmp_path)
    app.state.fridgesheet.settings.web_allow_lan = True
    app.state.fridgesheet.settings.web_extra_hosts = ["graphy.tailnet-1234.ts.net"]
    assert c.get("/", headers={"Host": "graphy.tailnet-1234.ts.net:8433"}).status_code == 200
    # ... and it is still a closed list, not a suffix or a wildcard
    assert c.get("/", headers={"Host": "evil.graphy.tailnet-1234.ts.net:8433"}).status_code == 403
    assert c.get("/", headers={"Host": "graphy.tailnet-1234.ts.net.evil.example:8433"}).status_code == 403


def test_the_ip_literal_rule_does_not_apply_to_a_pinned_bind(tmp_path):
    """The relaxation is scoped to a wildcard bind, where the app really is answering on every
    address. `FRIDGESHEET_WEB_HOST=127.0.0.1` pins it to loopback, and there a request claiming to
    be for the LAN address is simply wrong -- nothing is listening there."""
    c, app = _client(tmp_path)
    app.state.fridgesheet.settings.web_allow_lan = True          # ... and overridden by the pin
    app.state.fridgesheet.settings.web_host = "127.0.0.1"
    app.state.fridgesheet.settings.web_host_explicit = True
    assert c.get("/", headers={"Host": "192.168.1.42:8433"}).status_code == 403
    assert c.get("/", headers={"Host": "127.0.0.1:8433"}).status_code == 200


def test_a_mismatched_port_in_the_host_header_is_refused(tmp_path):
    """Isolates the port check on its own: `127.0.0.1` is this app's own hostname, but 9000 is
    not the port it's configured for (8433, the default `FORM`/`_client` use), so this is not
    this app's own address either. This is the exact shape of check that silently locked out
    `fridgesheet web --port 9000` until server.py folded the flag into `settings` -- app.py's
    port comparison line is what a CLI-flag override has to reach for that to work."""
    c, _ = _client(tmp_path)
    r = c.post("/settings", data={**FORM}, headers={"Host": "127.0.0.1:9000", "Origin": "http://127.0.0.1:9000"})
    assert r.status_code == 403


def test_the_host_check_covers_reads_not_only_writes(tmp_path):
    """A GET is not exempt: once a DNS name resolves to 127.0.0.1, an attacker's page becomes
    same-origin with this app in the browser's eyes, so a GET from it would otherwise come back
    with the whole page -- the OneLogin username, the kids' names and grades, the LAN address.
    `Origin` is irrelevant here (browsers don't send it on a plain GET); only `Host` matters."""
    c, _ = _client(tmp_path)
    assert c.get("/settings", headers={"Host": "evil.example"}).status_code == 403
    assert c.get("/settings", headers={"Host": "127.0.0.1:8433"}).status_code == 200


def test_the_two_refusals_say_two_different_things(tmp_path):
    """Nobody hostile ever reads a 403 body. The person who does is the parent who typed
    `http://dobby:8433/`, came in over an SSH port-forward, or is on a multi-homed or VPN box
    where the LAN probe follows the default route and reports an address this machine is not
    reached at. Before the Host check they got a working page; "Cross-site request refused."
    blames them for an attack they did not make and names no way out. Say what happened and
    where the app does answer.

    The cross-site wording stays where it belongs -- on the actual cross-site case, a write
    whose `Origin` is another site -- so the two refusals can be told apart in `app.log` and in
    a bug report.

    Neither body may echo the `Host` (or `Origin`) it refused: that is attacker-controlled text
    on a page this app itself serves."""
    c, _ = _client(tmp_path)

    refused_host = c.get("/settings", headers={"Host": "dobby.example:8433"})
    assert refused_host.status_code == 403
    assert "http://127.0.0.1:8433/" in refused_host.text
    assert "Cross-site" not in refused_host.text
    assert "dobby" not in refused_host.text

    # The genuine cross-site case: the Host is this app's own, the Origin is somebody else's.
    cross = c.post("/settings", data={**FORM},
                   headers={"Host": "127.0.0.1:8433", "Origin": "http://evil.example"})
    assert cross.status_code == 403
    assert "Cross-site request refused." in cross.text and "evil.example" not in cross.text


def test_the_host_refusal_names_the_port_this_app_is_actually_on(tmp_path):
    """The address in that message is only useful if it is this server's own -- a parent told
    to try 8433 while the app runs on 9000 is no better off than before."""
    c, app = _client(tmp_path)
    app.state.fridgesheet.settings.web_port = 9000
    r = c.get("/settings", headers={"Host": "dobby.example:9000"})
    assert r.status_code == 403 and "http://127.0.0.1:9000/" in r.text


def test_the_host_refusal_advertises_an_address_that_actually_answers(tmp_path):
    """The message is only worth printing if the address in it is live. Under a
    `FRIDGESHEET_WEB_HOST=192.168.1.42` pin -- the configuration docs/windows.md describes in order
    to warn about it -- uvicorn binds that address *instead of* loopback, so a refusal that
    always says `http://127.0.0.1:8433/` hands the parent a dead link at exactly the moment
    they are lost. Advertise `settings.bind_host` when it is a concrete address; loopback is
    the right answer for the default and for a wildcard bind, where it does answer."""
    c, app = _client(tmp_path)
    app.state.fridgesheet.settings.web_host = "192.168.1.42"
    app.state.fridgesheet.settings.web_host_explicit = True
    r = c.get("/settings", headers={"Host": "dobby.example:8433"})
    assert r.status_code == 403
    assert "http://192.168.1.42:8433/" in r.text and "127.0.0.1" not in r.text

    app.state.fridgesheet.settings.web_host = "0.0.0.0"          # a wildcard bind does answer on loopback
    assert "http://127.0.0.1:8433/" in c.get("/settings", headers={"Host": "dobby.example:8433"}).text

    app.state.fridgesheet.settings.web_host = "::"               # ... and an IPv6 literal is bracketed in a URL
    app.state.fridgesheet.settings.web_host_explicit = False
    app.state.fridgesheet.settings.web_allow_lan = False
    app.state.fridgesheet.settings.web_host = "fd00::1"
    app.state.fridgesheet.settings.web_host_explicit = True
    assert "http://[fd00::1]:8433/" in c.get("/settings", headers={"Host": "dobby.example:8433"}).text


def test_an_explicit_web_host_pin_is_matched_case_insensitively(tmp_path):
    """`_allowed_hosts` used to add `settings.bind_host` verbatim while the incoming `Host` is
    lowercased by `urlsplit`, so `FRIDGESHEET_WEB_HOST=MyBox.local` (a real mDNS-style hostname, not
    just a probed IP) would have refused its own address."""
    c, app = _client(tmp_path)
    app.state.fridgesheet.settings.web_host = "MyBox.local"
    app.state.fridgesheet.settings.web_host_explicit = True
    headers = {"Host": "mybox.local:8433", "Origin": "http://mybox.local:8433"}
    assert c.post("/settings", data={**FORM}, headers=headers).status_code != 403


def test_a_host_header_with_userinfo_is_refused(tmp_path):
    """`urlsplit` will parse a hostname out of `evil.example@127.0.0.1` too, handing back
    `127.0.0.1` and silently dropping the userinfo before `@`. Not exploitable -- browsers
    never put userinfo in a `Host` (or `Origin`) header -- but a `Host` is an authority with no
    userinfo component, and the fail-closed reading the rest of this function already follows
    is to refuse it outright rather than trust that it means nothing."""
    c, _ = _client(tmp_path)
    assert c.get("/settings", headers={"Host": "evil.example@127.0.0.1:8433"}).status_code == 403


def test_an_explicit_web_host_pin_is_accepted_and_evil_example_still_is_not(tmp_path):
    """FRIDGESHEET_WEB_HOST wins over `allow_lan` entirely (`config.Settings.bind_host`) -- a
    concrete pin binds exactly that address, whatever `allow_lan` says. That address is
    precisely what this app is served on, which is the same reasoning that admits loopback
    and the probed LAN address, so it belongs in the allowlist too."""
    c, app = _client(tmp_path)
    app.state.fridgesheet.settings.web_host = "192.168.1.50"
    app.state.fridgesheet.settings.web_host_explicit = True
    headers = {"Host": "192.168.1.50:8433", "Origin": "http://192.168.1.50:8433"}
    assert c.post("/settings", data={**FORM}, headers=headers).status_code != 403
    evil = {"Host": "evil.example", "Origin": "http://evil.example"}
    assert c.post("/settings", data={**FORM}, headers=evil).status_code == 403


def test_a_wildcard_web_host_pin_admits_the_lan_address_not_everything(monkeypatch, tmp_path):
    """FRIDGESHEET_WEB_HOST=0.0.0.0 (or `::`) binds every interface -- the operator asked for that
    explicitly, so it is treated the way `allow_lan` is: the probed LAN address is admitted,
    not every Host that shows up, which would put the hole this task closes straight back."""
    from fridgesheet.web import actions
    monkeypatch.setattr(actions, "_lan_probe", lambda: "192.168.1.42")
    c, app = _client(tmp_path)
    app.state.fridgesheet.settings.web_host = "0.0.0.0"
    app.state.fridgesheet.settings.web_host_explicit = True
    headers = {"Host": "192.168.1.42:8433", "Origin": "http://192.168.1.42:8433"}
    assert c.post("/settings", data={**FORM}, headers=headers).status_code != 403
    evil = {"Host": "evil.example", "Origin": "http://evil.example"}
    assert c.post("/settings", data={**FORM}, headers=evil).status_code == 403


def test_settings_page_shows_current_values_and_the_password_field_on_loopback(tmp_path):
    c, app = _client(tmp_path)
    body = c.get("/settings").text
    assert 'value="parent@example.org"' in body and 'name="password"' in body and 'type="password"' in body
    assert '<option value="Brother" selected' in body and 'value="Canon"' in body
    assert "Alex=Al" in body and 'name="port"' in body and 'name="allow_lan"' in body
    assert 'name="default_late_days" value="14"' in body                 # the late-rules editor, seeded
    assert 'name="quarter_date" value="2026-10-15"' in body
    assert "Labor Day" in body                                           # the no-print-days editor, seeded
    assert 'hx-post="/jobs/login"' not in body                            # no worker: no Test login button
    assert "Fridge Sheet" in body and "MIT" in body                       # about


def test_the_password_can_be_set_from_another_device(tmp_path):
    """This used to be refused with a 400 and the field hidden, on the reasoning that a
    password should only be typed on the computer holding it.

    That is unsatisfiable on a headless host: the account running the server has no desktop
    session, so no request from it is ever loopback, and "open Fridge Sheet on the PC itself"
    is an instruction nobody can follow -- the app cannot be set up at all. It also protected
    less than it appeared, because this app has no login (spec section 8): any device the Host
    check admits could already read the kids' grades and the OneLogin username, and setting a
    password gives an attacker nothing they did not have."""
    c, app = _client(tmp_path, host="192.168.1.9")
    body = c.get("/settings").text
    assert 'name="password"' in body and 'type="password"' in body
    assert "crosses your" in body and "no HTTPS" in body, "the trade-off is stated, not hidden"

    r = c.post("/settings", data={**FORM, "password": "hunter2"})
    assert r.status_code == 200 and "Password stored" in r.text
    assert app.state.fridgesheet.extra["credstore"].written == [("parent@example.org", "hunter2")]


def test_the_stored_password_is_never_rendered_back_to_any_device(tmp_path):
    """The property that does *not* relax with the loopback gate gone. Setting is now allowed
    from anywhere; reading never was and still is not, so a device on the network cannot turn
    the Settings page into a way to recover the password someone else stored."""
    c, app = _client(tmp_path)
    assert c.post("/settings", data={**FORM, "password": "hunter2"}).status_code == 200
    for client in (c, _client(tmp_path, host="192.168.1.9")[0]):
        body = client.get("/settings").text
        assert "hunter2" not in body
        assert 'placeholder="leave blank to keep the stored one"' in body


def test_a_blank_password_field_keeps_the_stored_one(tmp_path):
    """The corollary of never rendering it: a parent editing any other field submits an empty
    password box every time, and that must not wipe the credential."""
    c, app = _client(tmp_path)
    c.post("/settings", data={**FORM, "password": "hunter2"})
    c.post("/settings", data={**FORM, "days_ahead": "21"})               # blank password
    assert app.state.fridgesheet.extra["credstore"].written == [("parent@example.org", "hunter2")]


def test_save_round_trips_reloads_settings_and_stores_the_password(tmp_path):
    c, app = _client(tmp_path)
    r = c.post("/settings", data={**FORM, "password": "hunter2", "nicknames": "Alex=Dougie"})
    assert r.status_code == 200 and "Settings saved" in r.text and "Password stored" in r.text
    assert app.state.fridgesheet.extra["credstore"].written == [("parent@example.org", "hunter2")]
    doc = config.load_config_doc(tmp_path / "config.toml")
    assert doc["print"]["printer"] == "Canon" and doc["web"]["port"] == 8433
    assert app.state.fridgesheet.settings.nicknames == {"Alex": "Dougie"}    # reloaded
    assert ">Dougie<" in c.get("/").text                                     # the rail uses the new nickname


def test_invalid_form_shows_errors_and_writes_nothing(tmp_path):
    c, app = _client(tmp_path)
    before = (tmp_path / "config.toml").read_text()
    r = c.post("/settings", data={**FORM, "days_ahead": "0", "port": "80"})
    assert r.status_code == 200 and "between 1 and" in r.text and "1024" in r.text
    assert (tmp_path / "config.toml").read_text() == before


def test_changing_the_port_says_restart(tmp_path):
    c, app = _client(tmp_path)
    r = c.post("/settings", data={**FORM, "port": "9000", "allow_lan": "on"})
    assert "restart" in r.text.lower()
    assert "Allow other devices" in r.text                                   # the LAN URL itself depends on this machine's network (lan_url is unit-tested)


def test_the_lan_toggle_shows_a_qr_code_for_the_phone(monkeypatch, tmp_path):
    """Spec section 8: the toggle shows the LAN URL *and* a QR code. A parent standing in the
    kitchen should not have to type an IP address into a phone.

    The probe is injected. Without that, this test reaches `actions._lan_probe`'s real
    `socket.connect(("10.255.255.255", 1))` and fails on any host with no routable
    non-loopback IPv4 (a CI container, a laptop on aeroplane mode) for a reason that has
    nothing to do with QR codes -- which is why the port test three lines up deliberately
    stops short of asserting on the LAN URL at all. With a known address the assertion can be
    the exact drawing `qr.svg` produces for it, which also pins that the whole element reaches
    the page unescaped: a `| safe` scoped to only part of it would leave `&lt;` somewhere in
    this string and fail."""
    from fridgesheet import qr
    from fridgesheet.web import actions
    monkeypatch.setattr(actions, "_lan_probe", lambda: "192.168.1.42")
    c, _ = _client(tmp_path)
    body = c.post("/settings", data={**FORM, "password": "pw", "allow_lan": "on"}).text
    assert "http://192.168.1.42:8433/" in body            # the address itself, to type if need be
    assert qr.svg("http://192.168.1.42:8433/") in body    # ...and the same address, drawn
    assert "&lt;svg" not in body                          # marked safe, not escaped into visible markup


def test_the_qr_code_never_carries_what_the_form_typed_into_the_page(monkeypatch, tmp_path):
    """The QR is the one thing on this page rendered with `| safe`, and the URL it encodes
    contains `port` -- `Form("8433")`, a raw user string that the *error* path re-renders
    unsaved. What makes that safe is not "the server computed it": it is that segno emits
    module geometry only (`<svg>`/`<path>`) and never echoes the encoded text, since no
    `<title>`/`<desc>` is asked for. If that ever changes -- a segno upgrade, or a caller
    passing `title=` -- this is where it shows up."""
    from fridgesheet.web import actions
    monkeypatch.setattr(actions, "_lan_probe", lambda: "192.168.1.42")
    c, _ = _client(tmp_path)
    body = c.post("/settings", data={**FORM, "port": '80"><script>alert(1)</script>', "allow_lan": "on"}).text
    assert "<svg" in body                                     # the QR is drawn for the unsaved form
    assert "<script>alert(1)</script>" not in body            # ...and carries none of that with it
    assert "alert(1)" in body and "&lt;script&gt;" in body    # the URL text itself: escaped, as ordinary output


def test_no_qr_code_when_the_app_is_loopback_only(tmp_path):
    c, _ = _client(tmp_path)
    body = c.post("/settings", data={**FORM, "password": "pw"}).text
    assert "<svg" not in body


def test_settings_no_longer_edits_the_schedule(tmp_path):
    """Two pages writing `[reports.open-work].enabled` is how a page ends up showing a
    schedule the scheduler does not have. Schedules owns it; Settings links to it."""
    c, app = _client(tmp_path)
    with (tmp_path / "config.toml").open("a") as f:
        f.write('[reports.open-work]\nenabled = true\ntime = "14:00"\ndays = ["Fri"]\n')
    app.state.fridgesheet.clock = lambda: datetime(2026, 9, 25, 9, 0, tzinfo=ZoneInfo("America/New_York"))
    body = c.get("/settings").text
    assert 'name="scheduled"' not in body and 'name="time"' not in body
    assert 'href="/schedules"' in body
    assert 'name="days_ahead"' in body and 'name="overdue_days"' in body     # still the report's options
    # The read-only status line, moved but not dropped -- and read from the plan over
    # config.toml, not from whatever this machine's own systemd happens to say.
    assert "Automatic printing: No runs yet · next run Fri 9/25 2:00 PM" in body


def test_a_schedule_set_on_the_schedules_page_survives_a_settings_save(tmp_path):
    """The regression this task exists to prevent."""
    c, _ = _client(tmp_path)
    (tmp_path / "config.toml").write_text(
        '[account]\nusername = "parent@example.org"\n'
        '[reports.open-work]\nenabled = true\ntime = "15:00"\ndays = ["Mon"]\n')
    c.post("/settings", data={**FORM, "password": "pw"})
    doc = tomllib.loads((tmp_path / "config.toml").read_text())
    assert doc["reports"]["open-work"]["enabled"] is True
    assert doc["reports"]["open-work"]["time"] == "15:00"
    assert doc["reports"]["open-work"]["days"] == ["Mon"]


def test_late_rules_editor_validates_and_saves(tmp_path):
    c, app = _client(tmp_path)
    r = c.post("/settings/late-rules", data={"default_late_days": "x", "default_credit": "?"})
    assert r.status_code == 200 and "whole number" in r.text
    assert "late_days = 14" in (tmp_path / "late-rules.toml").read_text()     # unchanged: still the seed

    r = c.post("/settings/late-rules", data={
        "default_late_days": "10", "default_credit": "?",
        "quarter_date": ["2026-10-15"],
        "rule_kid": ["Alex"], "rule_course": ["Band"], "rule_mode": ["days"],
        "rule_late_days": ["7"], "rule_credit": ["50%"], "rule_source": ["syllabus"],
    })
    assert r.status_code == 200 and "Saved" in r.text
    saved = (tmp_path / "late-rules.toml").read_text()
    assert "late_days = 10" in saved and "Alex" in saved and "Band" in saved


def test_late_rules_editor_supports_a_quarter_end_rule(tmp_path):
    c, app = _client(tmp_path)
    r = c.post("/settings/late-rules", data={
        "default_late_days": "14", "default_credit": "?",
        "quarter_date": ["2026-10-15"],
        "rule_kid": [""], "rule_course": ["Band"], "rule_mode": ["quarter_end"],
        "rule_late_days": [""], "rule_credit": [""], "rule_source": [""],
    })
    assert r.status_code == 200 and "Saved" in r.text
    assert 'until = "quarter_end"' in (tmp_path / "late-rules.toml").read_text()


def test_no_print_days_editor_validates_and_saves(tmp_path):
    c, app = _client(tmp_path)
    r = c.post("/settings/no-print-days", data={"start": ["2026-12-25"], "end": [""], "note": ["Christmas"]})
    assert r.status_code == 200 and "Saved" in r.text
    assert "Christmas" in (tmp_path / "no-print-days.txt").read_text()

    r = c.post("/settings/no-print-days", data={"start": ["2026-12-25"], "end": ["2026-12-20"], "note": [""]})
    assert r.status_code == 200 and "before the start" in r.text
    assert "Christmas" in (tmp_path / "no-print-days.txt").read_text()        # unchanged


def test_setting_an_update_pin_stores_a_hash_and_never_the_pin(tmp_path):
    seed(tmp_path)
    c = app_for(tmp_path)
    c.app.state.fridgesheet.extra["credstore"] = FakeCred()
    c.post("/settings", data=_form(update_pin="2468"))
    text = (tmp_path / "config.toml").read_text(encoding="utf-8")
    assert "2468" not in text
    assert "pbkdf2_sha256$" in text


def test_the_pin_never_reads_back_into_the_form(tmp_path):
    """Same rule as the OneLogin password: settable from a phone, never readable."""
    seed(tmp_path, update_pin_hash=updatepin.hash_pin("2468"))
    body = app_for(tmp_path).get("/settings").text
    assert "pbkdf2_sha256$" not in body
    assert 'name="update_pin"' in body and "2468" not in body


def test_a_blank_pin_field_keeps_the_stored_one(tmp_path):
    stored = updatepin.hash_pin("2468")
    seed(tmp_path, update_pin_hash=stored)
    c = app_for(tmp_path)
    c.app.state.fridgesheet.extra["credstore"] = FakeCred()
    c.post("/settings", data=_form(update_pin=""))
    assert stored in (tmp_path / "config.toml").read_text(encoding="utf-8")


def test_no_button_without_a_pin(tmp_path, monkeypatch):
    monkeypatch.setattr(host, "IS_WINDOWS", True)   # the card's Windows guards, not the Linux line (#145)
    """An update genuinely is available (see `_app_with_update`), so the missing PIN is the
    only thing that can be suppressing the button here."""
    c = _app_with_update(tmp_path)
    body = c.get("/settings").text
    assert 'action="/settings/update"' not in body
    assert "Set an update PIN" in body


def test_no_button_when_the_logon_task_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(host, "IS_WINDOWS", True)   # the card's Windows guards, not the Linux line (#145)
    """Issue #39: schtasks /Create fails for standard users and Inno ignores [Run] exit
    codes. A silent update on such a machine leaves a dead app with no wizard and no
    shortcut, so we decline rather than strand them."""
    c = _app_with_update(tmp_path, pin=updatepin.hash_pin("2468"), service_installed=False)
    body = c.get("/settings").text
    assert 'action="/settings/update"' not in body
    assert "is not set up to start on its own" in body


def test_no_button_when_update_checks_are_off(tmp_path):
    """`[web] check_updates = false` is the parent's one switch for this app's one outbound
    call; the button must not quietly put it back regardless of what else is configured."""
    c = _app_with_update(tmp_path, pin=updatepin.hash_pin("2468"), check_updates=False)
    body = c.get("/settings").text
    assert 'action="/settings/update"' not in body
    assert "Update checks are turned off." in body


def test_the_button_renders_when_nothing_blocks_it(tmp_path, monkeypatch):
    monkeypatch.setattr(host, "IS_WINDOWS", True)   # the card's Windows guards, not the Linux line (#145)
    """The positive case: a PIN is set, the logon task is installed, checks are on, and an
    update is genuinely available -- so the button is exactly what should show, with the
    version it would update to."""
    c = _app_with_update(tmp_path, pin=updatepin.hash_pin("2468"))
    body = c.get("/settings").text
    assert 'action="/settings/update"' in body
    assert "Update to 9.9.9" in body


def test_check_now_brings_the_update_button_with_it(tmp_path, monkeypatch):
    """The button block used to render only on a full page load, so "Check for updates now"
    finding a release left the parent reloading the page to see the form. The check's
    response carries the block out of band instead, into the anchor the page always has."""
    monkeypatch.setattr(host, "IS_WINDOWS", True)   # the card's Windows guards, not the Linux line (#145)
    c = _app_with_update(tmp_path, pin=updatepin.hash_pin("2468"), tag="v0.1.0")
    body = c.get("/settings").text
    assert 'action="/settings/update"' not in body and 'id="update-action"' in body
    c.app.state.fridgesheet.extra["update_fetch"] = _release_fetch("v9.9.9")
    r = c.post("/settings/update/check")
    assert r.status_code == 200 and "Fridge Sheet 9.9.9 is available" in r.text
    assert 'id="update-action" hx-swap-oob="true"' in r.text
    assert 'action="/settings/update"' in r.text and "Update to 9.9.9" in r.text


def test_check_now_does_not_route_around_the_guards(tmp_path, monkeypatch):
    """Same swap, same guards: with no PIN set the out-of-band block comes back empty -- the
    check must not route around `_update_button.html`'s refusals. The reason is not in it:
    it sits in the Updates card beside the PIN field (#145), which a check does not change."""
    monkeypatch.setattr(host, "IS_WINDOWS", True)   # the card's Windows guards, not the Linux line (#145)
    c = _app_with_update(tmp_path, tag="v9.9.9")
    r = c.post("/settings/update/check")
    assert r.status_code == 200 and 'id="update-action" hx-swap-oob="true"' in r.text
    assert 'action="/settings/update"' not in r.text


RULE = '\n[[sources.rule]]\nkid = "Alex"\ncourse = "Band"\nassignments = "hac"\n'


def test_source_defaults_round_trip(tmp_path):
    c, app = _client(tmp_path)
    r = c.post("/settings", data={**FORM, "sources_assignments": "hac", "sources_grades": "canvas"})
    assert r.status_code == 200 and "Settings saved" in r.text
    doc = config.load_config_doc(tmp_path / "config.toml")
    assert (doc["sources"]["assignments"], doc["sources"]["grades"]) == ("hac", "canvas")
    assert app.state.fridgesheet.settings.sources.default.assignments == "hac"     # reloaded
    body = c.get("/settings").text
    assert 'name="sources_assignments"' in body and '<option value="hac" selected>' in body


def test_saving_the_form_keeps_rules(tmp_path):
    """Review focus 4: the main form owns the defaults, never the rules."""
    c, _ = _client(tmp_path)
    with open(tmp_path / "config.toml", "a") as f:
        f.write(RULE)
    assert c.post("/settings", data=FORM).status_code == 200
    doc = config.load_config_doc(tmp_path / "config.toml")
    assert doc["sources"]["rule"] == [{"kid": "Alex", "course": "Band", "assignments": "hac"}]


def test_a_bad_source_value_is_refused_and_nothing_is_written(tmp_path):
    c, _ = _client(tmp_path)
    before = (tmp_path / "config.toml").read_text()
    r = c.post("/settings", data={**FORM, "sources_grades": "powerschool"})
    assert "Canvas or HAC" in r.text
    assert (tmp_path / "config.toml").read_text() == before


def test_rules_are_listed_and_removable(tmp_path):
    c, app = _client(tmp_path)
    with open(tmp_path / "config.toml", "a") as f:
        f.write(RULE)
    app.state.fridgesheet.reload()
    body = c.get("/settings").text
    assert "Band" in body and 'action="/settings/sources/remove"' in body
    r = c.post("/settings/sources/remove", data={"kid": "Alex", "course": "Band"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/settings"
    assert "rule" not in config.load_config_doc(tmp_path / "config.toml")["sources"]
    assert app.state.fridgesheet.settings.sources.rules == ()


def test_bad_no_print_days_lines_reach_the_header_and_the_editor(tmp_path):
    """#147: a hand-edited no-print-days.txt with a reversed range or an impossible date lost
    those lines silently. The header carries them the way it carries a broken late-rules.toml
    (`AppState.rules`), and the editor lists them above the rows it could read."""
    c, _ = _client(tmp_path)
    (tmp_path / "no-print-days.txt").write_text(
        "2026-09-07 Labor Day\n2026-12-21..2026-12-01 Break\n2026-02-30 Nope\n", encoding="utf-8")
    home = c.get("/").text
    assert "no-print-days.txt line 2" in home and "ends before it starts" in home
    assert "no-print-days.txt line 3" in home and "2026-02-30" in home
    editor = c.get("/settings").text.split('id="no-print-days"', 1)[1]
    assert "line 2: 2026-12-21..2026-12-01 ends before it starts" in editor
    assert "line 3: 2026-02-30 is not a real date" in editor
    assert "Labor Day" in editor                                # what it could read is still editable
    # A file that reads clean says nothing at all.
    (tmp_path / "no-print-days.txt").write_text("2026-09-07 Labor Day\n", encoding="utf-8")
    assert "no-print-days.txt line" not in c.get("/").text
    assert "line 2:" not in c.get("/settings").text.split('id="no-print-days"', 1)[1]


def test_the_editor_does_not_claim_weekends_never_print(tmp_path):
    """#147: there is no weekend guard -- Schedules offers Saturday and Sunday, and ticking one
    prints on it. The editor's help line has to say what is true instead."""
    c, _ = _client(tmp_path)
    editor = c.get("/settings").text.split('id="no-print-days"', 1)[1]
    assert "never print" not in editor
    assert "Schedules" in editor.split("<details", 1)[0]


def test_the_editor_refuses_a_row_with_a_note_but_no_start_and_says_when_it_left_an_empty_one_out(tmp_path):
    """#147: a row with no start date was dropped without a word, note and all."""
    c, _ = _client(tmp_path)
    r = c.post("/settings/no-print-days",
               data={"start": ["", "2026-12-25"], "end": ["", ""], "note": ["Christmas Eve", "Christmas"]})
    assert r.status_code == 200 and "Row 1: needs a start date" in r.text and "Saved" not in r.text
    assert 'value="Christmas Eve"' in r.text                    # what was typed comes back, not the file
    assert "Christmas" not in (tmp_path / "no-print-days.txt").read_text()
    r = c.post("/settings/no-print-days",
               data={"start": ["", "2026-12-25"], "end": ["", ""], "note": ["", "Christmas"]})
    assert r.status_code == 200 and "Saved" in r.text and "Row 1 was empty and was left out" in r.text
    assert "Christmas" in (tmp_path / "no-print-days.txt").read_text()


def test_settings_says_when_the_environment_overrides_a_field(monkeypatch, tmp_path):
    """#148: `load_form` shows config.toml, but `FRIDGESHEET_PRINTER` and friends win over it
    (`config.load_settings`), so a parent changed the printer here and nothing happened. Each
    overridden field says which variable is in charge; the box stays editable and says it is
    ignored. `FRIDGESHEET_WEB_PORT` that is not a number is ignored by `load_settings`, so no
    note for it -- a note that lies is the bug this fixes."""
    monkeypatch.setenv("FRIDGESHEET_PRINTER", "Canon")
    monkeypatch.setenv("FRIDGESHEET_WEB_HOST", "0.0.0.0")
    monkeypatch.setenv("FRIDGESHEET_NICKNAMES", "Alex=Lex")
    monkeypatch.setenv("FRIDGESHEET_WEB_PORT", "not-a-port")
    c, _ = _client(tmp_path)
    body = c.get("/settings").text
    assert "Set by FRIDGESHEET_PRINTER=Canon in the environment" in body and "this box is ignored" in body
    assert "Set by FRIDGESHEET_WEB_HOST=0.0.0.0 in the environment" in body
    assert "FRIDGESHEET_NICKNAMES=Alex=Lex" in body
    assert "FRIDGESHEET_WEB_PORT" not in body and "FRIDGESHEET_SHEETS_ARCHIVE" not in body
    assert '<option value="Brother" selected' in body            # config.toml's value, still shown and editable
    monkeypatch.delenv("FRIDGESHEET_PRINTER")
    assert "FRIDGESHEET_PRINTER" not in c.get("/settings").text


def test_the_host_refusal_under_a_wildcard_bind_says_extra_hosts_not_the_tick(tmp_path):
    """#149: with **Allow other devices** already on, a computer name is still refused (a name
    is what a rebinding attacker controls), and the page told the parent to tick the box they
    had just ticked. The way in is `[web] extra_hosts`; say so, with the exact line.

    This is the one place a refused `Host` is shown back, and only when it is plainly a DNS
    name (letters, digits, dots, hyphens; not an address) on the right port under a wildcard
    bind: such a string cannot carry markup or a sentence, and the only person who reads a 403
    body is the one who typed that name."""
    c, app = _client(tmp_path)
    app.state.fridgesheet.settings.web_allow_lan = True
    r = c.get("/", headers={"Host": "dobby:8433"})
    assert r.status_code == 403
    assert 'extra_hosts = ["dobby"]' in r.text and "[web]" in r.text and "config.toml" in r.text
    assert "tick <b>Allow other devices" not in r.text
    assert "http://127.0.0.1:8433/" in r.text
    # A MagicDNS name -- the case the list exists for -- lower-cased, the way the list is matched.
    r = c.get("/", headers={"Host": "Graphy.Tailnet-1234.TS.net:8433"})
    assert 'extra_hosts = ["graphy.tailnet-1234.ts.net"]' in r.text


def test_the_host_refusal_echoes_a_name_only_when_it_is_plainly_a_name(tmp_path):
    c, app = _client(tmp_path)
    app.state.fridgesheet.settings.web_allow_lan = True
    r = c.get("/", headers={"Host": "dob'by:8433"})
    assert r.status_code == 403 and "dob" not in r.text and "extra_hosts" in r.text
    # The wrong port is not a name problem: nothing to add, the port is what to fix.
    r = c.get("/", headers={"Host": "dobby:9000"})
    assert r.status_code == 403 and "dobby" not in r.text and "extra_hosts = [" not in r.text and "8433" in r.text
    # LAN off: the tick is the advice, and the name is not echoed
    # (test_the_two_refusals_say_two_different_things).
    app.state.fridgesheet.settings.web_allow_lan = False
    r = c.get("/", headers={"Host": "dobby:8433"})
    assert "Allow other devices" in r.text and "dobby" not in r.text


def test_save_needs_no_password_when_the_environment_supplies_the_login(monkeypatch, tmp_path):
    """#154: on a headless box the login lives in `.env` (`FRIDGESHEET_ONELOGIN_*`), and the
    keyring is locked. Save used to demand a password anyway, so changing the printer meant
    typing one that then failed to store. The card says where the login comes from, and Save
    writes the rest without touching the store."""
    monkeypatch.setenv("FRIDGESHEET_ONELOGIN_USERNAME", "env@x.com")
    monkeypatch.setenv("FRIDGESHEET_ONELOGIN_PASSWORD", "s3cret")
    c, app = _client(tmp_path)
    card = c.get("/settings").text.split("School login", 1)[1].split("</section>", 1)[0]
    assert "Username and password are supplied by the environment (FRIDGESHEET_ONELOGIN_USERNAME)" in card
    assert "the boxes here are ignored" in card and "s3cret" not in card and "env@x.com" not in card
    r = c.post("/settings", data={**FORM, "username": "", "password": "", "printer": "Canon"})
    assert r.status_code == 200 and "Settings saved" in r.text
    assert "Enter the OneLogin password" not in r.text and "username is required" not in r.text
    assert app.state.fridgesheet.extra["credstore"].written == []
    doc = tomllib.loads((tmp_path / "config.toml").read_text())
    assert doc["print"]["printer"] == "Canon" and doc["account"]["username"] == "parent@example.org"
    monkeypatch.delenv("FRIDGESHEET_ONELOGIN_PASSWORD")
    assert "supplied by the environment" not in c.get("/settings").text


def test_a_password_typed_anyway_against_a_locked_keyring_is_a_message_not_a_500(monkeypatch, tmp_path):
    monkeypatch.setenv("FRIDGESHEET_ONELOGIN_USERNAME", "env@x.com")
    monkeypatch.setenv("FRIDGESHEET_ONELOGIN_PASSWORD", "s3cret")
    c, app = _client(tmp_path)

    class Locked:
        def write(self, username, password):
            raise RuntimeError("secret-tool: Cannot autolaunch D-Bus without X11 $DISPLAY")
    app.state.fridgesheet.extra["credstore"] = Locked()
    r = c.post("/settings", data={**FORM, "password": "typed-anyway"})
    assert r.status_code == 200
    assert "could not be stored" in r.text and "D-Bus" in r.text and "typed-anyway" not in r.text


# --- the time zone (#122) ------------------------------------------------------------------

def test_settings_offers_a_time_zone_and_names_this_computers(tmp_path):
    """A field under "Where you are": the common US zones to pick from, any IANA name typed,
    and what a blank means -- this computer's zone, named, so a parent can see it is right."""
    client, _ = _client(tmp_path)
    html = client.get("/settings").text
    assert 'name="timezone"' in html and "Where you are" in html
    assert "this computer's: America/New_York" in html
    for zone in ("America/Chicago", "America/Denver", "America/Phoenix", "America/Los_Angeles", "Pacific/Honolulu"):
        assert f'<option value="{zone}">' in html


def test_saving_a_time_zone_writes_general_timezone_and_the_app_uses_it_now(tmp_path):
    client, application = _client(tmp_path)
    r = client.post("/settings", data=_form(timezone="America/Chicago"))
    assert r.status_code == 200 and "Settings saved" in r.text
    assert tomllib.loads((tmp_path / "config.toml").read_text())["general"]["timezone"] == "America/Chicago"
    assert str(application.state.fridgesheet.tz) == "America/Chicago"      # in force now, not at the next start
    assert 'name="timezone"' in r.text and 'value="America/Chicago"' in r.text
    # Blank means this computer's zone again: the key goes, rather than staying as "".
    r = client.post("/settings", data=_form(timezone="  "))
    assert r.status_code == 200 and "Settings saved" in r.text
    assert "timezone" not in tomllib.loads((tmp_path / "config.toml").read_text()).get("general", {})
    assert str(application.state.fridgesheet.tz) == "America/New_York"


def test_a_time_zone_that_is_not_a_zone_is_refused_before_anything_is_written(tmp_path):
    client, _ = _client(tmp_path)
    r = client.post("/settings", data=_form(timezone="Eastern"))
    assert r.status_code == 200 and "Time zone must be a name like America/Chicago" in r.text
    assert "general" not in tomllib.loads((tmp_path / "config.toml").read_text())
    assert 'value="Eastern"' in r.text                                     # what was typed comes back to fix


def test_the_settings_page_says_when_the_environment_pins_the_time_zone(tmp_path, monkeypatch):
    monkeypatch.setenv("FRIDGESHEET_TIMEZONE", "America/Denver")
    client, _ = _client(tmp_path)
    html = client.get("/settings").text
    assert "Set by FRIDGESHEET_TIMEZONE=America/Denver in the environment" in html
