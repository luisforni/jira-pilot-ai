import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.deps import get_current_org_member
from core.auth.rate_limit import get_usage
from core.auth.repository import AuthRepository
from core.database import get_db
from core.models.auth import PLAN_MONTHLY_LIMITS, Organization, Role, User

router = APIRouter(prefix="/orgs", tags=["organizations"])


class OrgResponse(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    usage_this_month: int
    monthly_limit: int


class CreateAPIKeyRequest(BaseModel):
    name: str
    scopes: list[str] = ["pipeline:run"]


class APIKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    scopes: list
    is_active: bool
    created_at: str


class CreateAPIKeyResponse(BaseModel):
    raw_key: str
    key: APIKeyResponse
    warning: str = "Store this key securely — it will not be shown again."


class InviteMemberRequest(BaseModel):
    email: str
    role: str = "member"


def _require_admin(role: str) -> None:
    if role not in (Role.OWNER.value, Role.ADMIN.value):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")


@router.get("/{slug}", response_model=OrgResponse)
async def get_org(
    slug: str,
    auth=Depends(get_current_org_member),
    db: AsyncSession = Depends(get_db),
) -> OrgResponse:
    _, org, _ = auth
    if org.slug != slug:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    usage = await get_usage(str(org.id))
    return OrgResponse(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        plan=org.plan,
        usage_this_month=usage,
        monthly_limit=PLAN_MONTHLY_LIMITS.get(org.plan, 50),
    )


@router.get("/{slug}/api-keys", response_model=list[APIKeyResponse])
async def list_api_keys(
    slug: str,
    auth=Depends(get_current_org_member),
    db: AsyncSession = Depends(get_db),
) -> list[APIKeyResponse]:
    _, org, role = auth
    _require_admin(role)

    repo = AuthRepository(db)
    keys = await repo.list_api_keys(org.id)
    return [
        APIKeyResponse(
            id=str(k.id),
            name=k.name,
            key_prefix=k.key_prefix,
            scopes=k.scopes,
            is_active=k.is_active,
            created_at=k.created_at.isoformat(),
        )
        for k in keys
    ]


@router.post("/{slug}/api-keys", response_model=CreateAPIKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    slug: str,
    body: CreateAPIKeyRequest,
    auth=Depends(get_current_org_member),
    db: AsyncSession = Depends(get_db),
) -> CreateAPIKeyResponse:
    _, org, role = auth
    _require_admin(role)

    repo = AuthRepository(db)
    raw, key = await repo.create_api_key(org.id, body.name, body.scopes)
    await db.commit()

    return CreateAPIKeyResponse(
        raw_key=raw,
        key=APIKeyResponse(
            id=str(key.id),
            name=key.name,
            key_prefix=key.key_prefix,
            scopes=key.scopes,
            is_active=key.is_active,
            created_at=key.created_at.isoformat(),
        ),
    )


@router.delete("/{slug}/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    slug: str,
    key_id: uuid.UUID,
    auth=Depends(get_current_org_member),
    db: AsyncSession = Depends(get_db),
) -> None:
    _, org, role = auth
    _require_admin(role)

    repo = AuthRepository(db)
    revoked = await repo.revoke_api_key(key_id, org.id)
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    await db.commit()


@router.post("/{slug}/members", status_code=status.HTTP_201_CREATED)
async def invite_member(
    slug: str,
    body: InviteMemberRequest,
    auth=Depends(get_current_org_member),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _, org, role = auth
    _require_admin(role)

    repo = AuthRepository(db)
    user = await repo.get_user_by_email(body.email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found — they must register first")

    existing_role = await repo.get_member_role(org.id, user.id)
    if existing_role:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already a member")

    await repo.add_member(org.id, user.id, body.role)
    await db.commit()
    return {"message": f"{body.email} added as {body.role}"}
