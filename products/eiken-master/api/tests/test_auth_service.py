# products/eiken-master/api/tests/test_auth_service.py
from app.services.auth import hash_pin, verify_pin, create_token, decode_token


def test_hash_and_verify_correct_pin():
    hashed = hash_pin("1234")
    assert verify_pin("1234", hashed)


def test_verify_wrong_pin_fails():
    hashed = hash_pin("1234")
    assert not verify_pin("0000", hashed)


def test_create_and_decode_token():
    user_id = "test-user-uuid"
    token = create_token(user_id)
    payload = decode_token(token)
    assert payload["sub"] == user_id


def test_decode_invalid_token_raises():
    from jose import JWTError
    import pytest

    with pytest.raises(JWTError):
        decode_token("not.a.valid.token")
