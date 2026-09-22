from datetime import datetime, timedelta

from fridgesheet.web import updatepin

NOW = datetime(2026, 9, 22, 15, 0)


def test_a_stored_pin_is_a_hash_and_never_the_pin():
    stored = updatepin.hash_pin("2468")
    assert "2468" not in stored
    assert stored.startswith("pbkdf2_sha256$")
    assert updatepin.verify("2468", stored)


def test_the_same_pin_hashes_differently_every_time():
    """A shared salt would let two households with the same PIN recognise it in each
    other's config.toml, and makes one precomputed table work everywhere."""
    assert updatepin.hash_pin("2468") != updatepin.hash_pin("2468")


def test_a_wrong_pin_is_refused():
    stored = updatepin.hash_pin("2468")
    assert not updatepin.verify("2469", stored)
    assert not updatepin.verify("", stored)


def test_nothing_verifies_against_an_unset_or_malformed_pin():
    """No PIN set must never mean every PIN works."""
    for stored in ("", "   ", "not-a-hash", "pbkdf2_sha256$abc"):
        assert not updatepin.verify("2468", stored)
        assert not updatepin.verify("", stored)


def test_five_failures_lock_the_route_for_fifteen_minutes():
    a = updatepin.Attempts()
    for _ in range(4):
        a.record_failure(NOW)
    assert a.locked_until(NOW) is None
    a.record_failure(NOW)
    assert a.locked_until(NOW) == NOW + timedelta(minutes=15)


def test_the_lock_expires():
    a = updatepin.Attempts()
    for _ in range(5):
        a.record_failure(NOW)
    assert a.locked_until(NOW + timedelta(minutes=16)) is None


def test_a_correct_pin_clears_the_count():
    a = updatepin.Attempts()
    for _ in range(4):
        a.record_failure(NOW)
    a.clear()
    a.record_failure(NOW)
    assert a.locked_until(NOW) is None
