from app.security import hash_password, verify_password


def test_hash_is_argon2_and_salted():
    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")

    assert first.startswith("$argon2id$")
    assert first != second


def test_verify_accepts_the_right_password():
    assert verify_password("s3cret-password", hash_password("s3cret-password"))


def test_verify_rejects_a_wrong_password():
    assert not verify_password("wrong-password", hash_password("s3cret-password"))


def test_verify_rejects_a_malformed_hash():
    assert not verify_password("anything", "not-a-hash")
