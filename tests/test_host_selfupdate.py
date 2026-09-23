import hashlib
import io
import json

import pytest

from fridgesheet.host import selfupdate

BODY = b"pretend installer" * 1000
GOOD = "sha256:" + hashlib.sha256(BODY).hexdigest()


def _opener(body: bytes):
    def open_url(url):
        return io.BytesIO(body)
    return open_url


def _log(_line):
    pass


def test_a_verified_download_lands_at_dest(tmp_path):
    dest = tmp_path / "Setup.exe"
    out = selfupdate.download_verified("https://x/s.exe", GOOD, dest,
                                       opener=_opener(BODY), log=_log, free_bytes=10**9)
    assert out == dest and dest.read_bytes() == BODY


def test_a_wrong_digest_refuses_and_leaves_nothing_behind(tmp_path):
    """The whole point. Nothing may execute that GitHub did not describe."""
    dest = tmp_path / "Setup.exe"
    with pytest.raises(selfupdate.UpdateError, match="does not match"):
        selfupdate.download_verified("https://x/s.exe", "sha256:" + "00" * 32, dest,
                                     opener=_opener(BODY), log=_log, free_bytes=10**9)
    assert not dest.exists()
    assert list(tmp_path.iterdir()) == []


def test_an_empty_digest_refuses_before_downloading(tmp_path):
    """A release with no .exe asset. The URL is the release page; fetching it would give
    HTML and fail the hash after 286 MB of nothing."""
    calls = []

    def opener(url):
        calls.append(url)
        return io.BytesIO(BODY)

    with pytest.raises(selfupdate.UpdateError, match="no installer"):
        selfupdate.download_verified("https://x/releases", "", tmp_path / "s.exe",
                                     opener=opener, log=_log, free_bytes=10**9)
    assert calls == []


def test_too_little_free_space_refuses_before_downloading(tmp_path):
    calls = []

    def opener(url):
        calls.append(url)
        return io.BytesIO(BODY)

    with pytest.raises(selfupdate.UpdateError, match="free space"):
        selfupdate.download_verified("https://x/s.exe", GOOD, tmp_path / "s.exe",
                                     opener=opener, log=_log, free_bytes=1000, size=10**9)
    assert calls == []


def test_the_default_free_space_check_works_when_the_folder_does_not_exist_yet(tmp_path):
    """The real first-run path: a household's updates/ folder does not exist before the
    first update, and the caller passes `size` but not `free_bytes`. Every other test
    supplies free_bytes, which is exactly why this crashed unnoticed."""
    dest = tmp_path / "does-not-exist-yet" / "Setup.exe"
    out = selfupdate.download_verified("https://x/s.exe", GOOD, dest,
                                       opener=_opener(BODY), log=_log, size=len(BODY))
    assert out == dest and dest.read_bytes() == BODY


def test_a_download_that_dies_partway_leaves_nothing_behind(tmp_path):
    """Review Focus 4: the space check is not a reservation. A partial file must never be
    left where something could execute it."""
    class Dying(io.BytesIO):
        def read(self, n=-1):
            raise OSError("connection reset")

    dest = tmp_path / "Setup.exe"
    with pytest.raises(selfupdate.UpdateError):
        selfupdate.download_verified("https://x/s.exe", GOOD, dest,
                                     opener=lambda u: Dying(), log=_log, free_bytes=10**9)
    assert not dest.exists()
    assert list(tmp_path.iterdir()) == []


def _pending():
    return selfupdate.Pending(from_version="0.4.1", to_version="0.5.0",
                              started_at="2026-09-22T15:00:00-04:00",
                              installer=r"C:\u\updates\Setup.exe", log=r"C:\u\updates\install.log")


def test_a_breadcrumb_round_trips(tmp_path):
    selfupdate.write_pending(tmp_path, _pending())
    assert selfupdate.read_pending(tmp_path) == _pending()


def test_the_new_version_running_means_it_worked(tmp_path):
    selfupdate.write_pending(tmp_path, _pending())
    verdict, pending = selfupdate.resolve_pending(tmp_path, "0.5.0")
    assert verdict == "ok" and pending.to_version == "0.5.0"
    assert selfupdate.read_pending(tmp_path) is None          # archived, not left to fire again
    assert (tmp_path / selfupdate.LAST_NAME).exists()


def test_the_old_version_still_running_means_it_did_not_take(tmp_path):
    selfupdate.write_pending(tmp_path, _pending())
    verdict, pending = selfupdate.resolve_pending(tmp_path, "0.4.1")
    assert verdict == "failed" and pending.log.endswith("install.log")
    assert selfupdate.read_pending(tmp_path) is not None       # kept, so Diagnostics can show it


def test_no_breadcrumb_is_a_normal_start(tmp_path):
    assert selfupdate.read_pending(tmp_path) is None
    assert selfupdate.resolve_pending(tmp_path, "0.4.1") is None


def test_a_malformed_breadcrumb_is_treated_as_absent_and_never_fatal(tmp_path):
    (tmp_path / selfupdate.PENDING_NAME).write_text("{not json", encoding="utf-8")
    assert selfupdate.read_pending(tmp_path) is None
    assert selfupdate.resolve_pending(tmp_path, "0.4.1") is None


def test_a_wrong_typed_field_is_treated_as_absent(tmp_path):
    """`str()` succeeds on anything, so a null or a nested object would otherwise become
    the literal text "None" -- a to_version that can never match the running version, and
    so a "last update did not finish" banner no parent can clear."""
    for bad in (None, {"a": 1}, [1, 2], 5):
        (tmp_path / selfupdate.PENDING_NAME).write_text(json.dumps({
            "from_version": bad, "to_version": "0.5.0",
            "started_at": "2026-09-22T15:00:00-04:00",
            "installer": "C:/u/Setup.exe", "log": "C:/u/install.log"}), encoding="utf-8")
        assert selfupdate.read_pending(tmp_path) is None, bad
        assert selfupdate.resolve_pending(tmp_path, "0.4.1") is None, bad


def test_a_second_update_overwrites_the_previous_archive(tmp_path):
    """Path.replace, not Path.rename: on Windows rename raises if the target exists, so
    the second update a household ever runs would fail to archive."""
    first = selfupdate.Pending("0.3.0", "0.4.1", "2026-09-01T10:00:00-04:00", "a.exe", "a.log")
    selfupdate.write_pending(tmp_path, first)
    assert selfupdate.resolve_pending(tmp_path, "0.4.1")[0] == "ok"
    second = _pending()
    selfupdate.write_pending(tmp_path, second)
    verdict, got = selfupdate.resolve_pending(tmp_path, "0.5.0")
    assert verdict == "ok" and got == second
    assert (tmp_path / selfupdate.LAST_NAME).exists()
