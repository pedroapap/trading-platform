from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.config import Settings, get_settings
from app.security import InvalidTokenError, create_access_token, decode_access_token


def _secret() -> str:
    return get_settings().jwt_secret.get_secret_value()


def test_token_round_trip():
    assert decode_access_token(create_access_token("user-123")) == "user-123"


def test_tampered_token_is_rejected():
    header, _, signature = create_access_token("user-123").split(".")
    forged = jwt.utils.base64url_encode(b'{"sub":"intruder","iat":1,"exp":9999999999}').decode()

    with pytest.raises(InvalidTokenError):
        decode_access_token(f"{header}.{forged}.{signature}")


def test_expired_token_is_rejected():
    long_ago = datetime.now(UTC) - timedelta(minutes=get_settings().jwt_expire_minutes + 1)

    with pytest.raises(InvalidTokenError):
        decode_access_token(create_access_token("user-123", now=long_ago))


def test_token_signed_with_another_key_is_rejected():
    now = datetime.now(UTC)
    payload = {"sub": "user-123", "iat": now, "exp": now + timedelta(hours=1)}
    foreign = jwt.encode(payload, "another-key-" + "x" * 32, algorithm="HS256")

    with pytest.raises(InvalidTokenError):
        decode_access_token(foreign)


def test_unsigned_token_is_rejected():
    now = datetime.now(UTC)
    payload = {"sub": "user-123", "iat": now, "exp": now + timedelta(hours=1)}
    unsigned = jwt.encode(payload, None, algorithm="none")

    with pytest.raises(InvalidTokenError):
        decode_access_token(unsigned)


def test_token_without_expiry_is_rejected():
    no_expiry = jwt.encode({"sub": "user-123", "iat": datetime.now(UTC)}, _secret(), "HS256")

    with pytest.raises(InvalidTokenError):
        decode_access_token(no_expiry)


def test_creating_a_token_without_a_secret_fails(monkeypatch):
    monkeypatch.setattr(
        "app.security.get_settings", lambda: Settings(_env_file=None, jwt_secret=None)
    )

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        create_access_token("user-123")
