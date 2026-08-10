from app.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_hash_and_verify():
    hashed = hash_password("mysecretpassword")

    assert hashed != "mysecretpassword"  # never store the plain password
    assert verify_password("mysecretpassword", hashed)
    assert not verify_password("wrongpassword", hashed)


def test_access_token_round_trip():
    token = create_access_token(subject="jeevan@example.com")

    assert decode_access_token(token) == "jeevan@example.com"


def test_tampered_token_is_rejected():
    token = create_access_token(subject="jeevan@example.com")
    # flip a character in the middle of the token, not the last one — base64's
    # final character can encode unused padding bits, so toggling it sometimes
    # decodes to the exact same bytes and the tamper is a silent no-op, which is
    # what caused this test to fail intermittently across separate sessions
    middle = len(token) // 2
    tampered = token[:middle] + ("a" if token[middle] != "a" else "b") + token[middle + 1 :]

    assert decode_access_token(tampered) is None
