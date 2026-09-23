"""Settings: the form round-trips config.toml, the password stays on this machine, the editors validate."""
from __future__ import annotations

import tomllib

from fastapi.testclient import TestClient

from fridgesheet import config
from fridgesheet.web import app as webapp, updatepin
from tests.web_fixtures import LOCAL_HOST_HEADERS, app_for, seed


class FakeCred:
    def __init__(self):
        self.written = []
    def write(self, user, pw):
        self.written.append((user, pw))
    def read_username(self):
        return self.written[-1][0] if self.written else None


class StubScheduling:
    """The status line's read-only `describe`; Settings no longer installs or removes anything.

    It answers with a next run no machine would report by accident. A fake that says "not
    scheduled" is indistinguishable from the page shelling out to the real `systemctl --user`
    and failing -- which is what happened here, and which is why the assertion passed under
    pytest (no D-Bus session) and would have failed in the owner's own desktop session, where
    fridgesheet-print-sheet.timer is enabled.
    """
    def describe(self, key):
        from fridgesheet.host import ScheduleInfo
        return ScheduleInfo("systemd", True, "Fri 2026-09-18 16:30:00 EDT", None)


def _client(home, host="127.0.0.1"):
    seed(home).close()
    (home / "config.toml").write_text('[account]\nusername = "parent@example.org"\n[print]\nprinter = "Brother"\n[kids]\nnicknames = { Alex = "Al" }\n')
    s = config.Settings(home=home)
    config.settings_from_doc(config.load_config_doc(home / "config.toml"), s)
    application = webapp.create_app(s, worker=False)
    application.state.fridgesheet.extra["credstore"] = FakeCred()
    application.state.fridgesheet.extra["scheduling"] = StubScheduling()
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
    c, _ = _client(tmp_path)
    body = c.get("/settings").text
    assert 'name="scheduled"' not in body and 'name="time"' not in body
    assert 'href="/schedules"' in body
    assert 'name="days_ahead"' in body and 'name="overdue_days"' in body     # still the report's options
    # The read-only status line, moved but not dropped -- and read from the injected scheduler,
    # not from whatever this machine's own systemd happens to say.
    assert "Automatic printing: No runs yet · next run Fri 2026-09-18 16:30:00 EDT (systemd)" in body


def test_saving_settings_never_touches_the_scheduler(tmp_path):
    class Exploding:
        def install(self, *a, **k):
            raise AssertionError("Settings must not install a schedule")
        def remove(self, *a, **k):
            raise AssertionError("Settings must not remove a schedule")
    c, app = _client(tmp_path)
    app.state.fridgesheet.extra["scheduling"] = Exploding()
    r = c.post("/settings", data={**FORM, "password": "pw"})
    assert r.status_code == 200 and "Settings saved" in r.text


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
