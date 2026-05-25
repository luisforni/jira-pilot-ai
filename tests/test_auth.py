import pytest

from core.auth.api_keys import generate_api_key, hash_api_key
from core.auth.jwt import create_access_token, create_refresh_token, decode_token
from core.auth.password import hash_password, verify_password
from core.auth.rate_limit import PLAN_MONTHLY_LIMITS


# ── Password ─────────────────────────────────────────────────────────────────

def test_password_hash_and_verify():
    hashed = hash_password("supersecret123")
    assert verify_password("supersecret123", hashed)
    assert not verify_password("wrongpassword", hashed)


def test_password_hashes_differ():
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2  # bcrypt includes salt


# ── JWT ───────────────────────────────────────────────────────────────────────

def test_access_token_roundtrip():
    token = create_access_token("user-1", "org-1", "admin")
    payload = decode_token(token)
    assert payload["sub"] == "user-1"
    assert payload["org"] == "org-1"
    assert payload["role"] == "admin"
    assert payload["type"] == "access"


def test_refresh_token_roundtrip():
    token = create_refresh_token("user-1")
    payload = decode_token(token)
    assert payload["sub"] == "user-1"
    assert payload["type"] == "refresh"


def test_invalid_token_raises():
    import jwt
    with pytest.raises(jwt.InvalidTokenError):
        decode_token("not.a.valid.token")


# ── API Keys ──────────────────────────────────────────────────────────────────

def test_generate_api_key_format():
    raw, prefix, key_hash = generate_api_key()
    assert raw.startswith("jp_")
    assert len(raw) > 20
    assert prefix == raw[:11]
    assert len(key_hash) == 64  # SHA-256 hex


def test_hash_api_key_deterministic():
    raw, _, _ = generate_api_key()
    h1 = hash_api_key(raw)
    h2 = hash_api_key(raw)
    assert h1 == h2


def test_different_keys_different_hashes():
    raw1, _, _ = generate_api_key()
    raw2, _, _ = generate_api_key()
    assert hash_api_key(raw1) != hash_api_key(raw2)


# ── Rate limiting plan caps ───────────────────────────────────────────────────

def test_plan_limits():
    assert PLAN_MONTHLY_LIMITS["free"] == 50
    assert PLAN_MONTHLY_LIMITS["pro"] == 500
    assert PLAN_MONTHLY_LIMITS["enterprise"] >= 999_999
    assert PLAN_MONTHLY_LIMITS["pro"] > PLAN_MONTHLY_LIMITS["free"]
