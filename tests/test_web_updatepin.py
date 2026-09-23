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


def test_the_security_constants_are_what_they_claim_to_be():
    """A cost that can be lowered without a test going red is a cost nobody is keeping."""
    assert updatepin.ITERATIONS == 240_000
    assert updatepin.MAX_ATTEMPTS == 5
    assert updatepin.LOCKOUT == timedelta(minutes=15)


def test_the_comparison_is_constant_time():
    """`==` on the derived key passes every behavioural test and leaks timing. The only
    way to pin this is to look at the source."""
    import inspect

    assert "compare_digest" in inspect.getsource(updatepin.verify)


def test_an_absurd_iteration_count_is_refused_not_hung_or_raised():
    """A hostile or corrupt config.toml must not be able to wedge the server with a huge
    count, nor crash it with one too large for pbkdf2_hmac's C long."""
    salt_b64 = "AAAAAAAAAAAAAAAAAAAAAA=="
    hash_b64 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    huge = f"pbkdf2_sha256$99999999999999999999${salt_b64}${hash_b64}"
    large_but_parseable = f"pbkdf2_sha256$10000000001${salt_b64}${hash_b64}"
    assert updatepin.verify("2468", huge) is False
    assert updatepin.verify("2468", large_but_parseable) is False


def test_a_non_string_stored_value_is_refused_not_raised():
    """tomllib turns an unquoted `update_pin_hash = 2468` into an int; that must fail
    closed, not raise AttributeError."""
    assert updatepin.verify("2468", 2468) is False
    assert updatepin.verify("2468", None) is False


def test_an_unpaired_surrogate_pin_is_refused_not_raised_with_the_pin_in_it():
    """A UnicodeEncodeError's .args/repr can carry the plaintext PIN; refuse instead."""
    assert updatepin.verify("\ud800", "pbkdf2_sha256$1$AAAAAAAAAAAAAAAAAAAAAA==$AAAA") is False
