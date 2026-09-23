import hashlib
import io
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
