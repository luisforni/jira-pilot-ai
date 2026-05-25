from datetime import datetime, timedelta, timezone

import jwt

from core.config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: str, org_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "org": org_id,
        "role": role,
        "type": "access",
        "exp": _now() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": _now(),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": _now() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        "iat": _now(),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Raises jwt.InvalidTokenError on failure."""
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
