from app.auth_store import _hash_password, _verify_password


def test_password_hash_round_trip_and_wrong_password() -> None:
    encoded = _hash_password("correct horse battery staple")
    assert _verify_password("correct horse battery staple", encoded)
    assert not _verify_password("wrong", encoded)
