from datetime import datetime, timezone

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.api_keys import hash_api_key
from core.auth.jwt import decode_token
from core.auth.rate_limit import check_and_increment
from core.database import get_db
from core.models.auth import APIKey, Organization, OrganizationMember, User

_bearer = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
_FORBIDDEN = HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
_RATE_LIMITED = HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Monthly pipeline run limit reached")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise _UNAUTHORIZED
    try:
        payload = decode_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise _UNAUTHORIZED

    if payload.get("type") != "access":
        raise _UNAUTHORIZED

    result = await db.execute(select(User).where(User.id == payload["sub"], User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise _UNAUTHORIZED
    return user


async def get_current_org_member(
    user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, Organization, str]:
    """Returns (user, org, role). Extracts org_id from JWT."""
    try:
        payload = decode_token(credentials.credentials)
        org_id = payload.get("org")
        role = payload.get("role", "member")
    except Exception:
        raise _UNAUTHORIZED

    result = await db.execute(
        select(Organization).where(Organization.id == org_id, Organization.is_active == True)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise _FORBIDDEN

    return user, org, role


async def get_org_from_api_key(
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Validates an API key and returns the associated org. Used by webhooks/n8n."""
    key_hash = hash_api_key(x_api_key)
    result = await db.execute(
        select(APIKey).where(APIKey.key_hash == key_hash, APIKey.is_active == True)
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise _UNAUTHORIZED

    # Update last_used_at
    api_key.last_used_at = datetime.now(timezone.utc)

    result = await db.execute(
        select(Organization).where(Organization.id == api_key.organization_id, Organization.is_active == True)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise _UNAUTHORIZED

    return org


async def require_pipeline_quota(
    org: Organization = Depends(get_org_from_api_key),
) -> Organization:
    """Checks rate limit before allowing a pipeline run. Used on /agent/run-ticket."""
    allowed, current, limit = await check_and_increment(str(org.id), org.plan)
    if not allowed:
        raise _RATE_LIMITED
    return org
