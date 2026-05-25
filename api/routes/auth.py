from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.deps import get_current_user
from core.auth.jwt import create_access_token, create_refresh_token, decode_token
from core.auth.repository import AuthRepository
from core.auth.rate_limit import get_usage
from core.database import get_db
from core.models.auth import PLAN_MONTHLY_LIMITS

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str = ""
    org_name: str
    org_slug: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    org_slug: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    user_id: str
    email: str
    full_name: str
    organizations: list[dict]


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    repo = AuthRepository(db)

    if await repo.get_user_by_email(body.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    if await repo.get_org_by_slug(body.org_slug):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Organization slug already taken")

    user = await repo.create_user(body.email, body.password, body.full_name)
    org = await repo.create_org(body.org_name, body.org_slug, user)
    await db.commit()

    access = create_access_token(str(user.id), str(org.id), "owner")
    refresh = create_refresh_token(str(user.id))
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    repo = AuthRepository(db)
    user = await repo.authenticate(body.email, body.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    org = await repo.get_org_by_slug(body.org_slug)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    role = await repo.get_member_role(org.id, user.id)
    if not role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this organization")

    access = create_access_token(str(user.id), str(org.id), role)
    refresh = create_refresh_token(str(user.id))
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    import jwt as pyjwt
    try:
        payload = decode_token(body.refresh_token)
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not a refresh token")

    repo = AuthRepository(db)
    orgs = await repo.get_user_orgs(payload["sub"])
    if not orgs:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No organizations")

    org, role = orgs[0]
    access = create_access_token(payload["sub"], str(org.id), role)
    new_refresh = create_refresh_token(payload["sub"])
    return TokenResponse(access_token=access, refresh_token=new_refresh)


@router.get("/me", response_model=MeResponse)
async def me(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> MeResponse:
    repo = AuthRepository(db)
    orgs = await repo.get_user_orgs(user.id)

    org_list = []
    for org, role in orgs:
        usage = await get_usage(str(org.id))
        limit = PLAN_MONTHLY_LIMITS.get(org.plan, 50)
        org_list.append({
            "id": str(org.id),
            "name": org.name,
            "slug": org.slug,
            "plan": org.plan,
            "role": role,
            "usage_this_month": usage,
            "monthly_limit": limit,
        })

    return MeResponse(
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        organizations=org_list,
    )
