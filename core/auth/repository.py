import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.auth.api_keys import generate_api_key
from core.auth.password import hash_password, verify_password
from core.models.auth import APIKey, Organization, OrganizationMember, Role, User


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ── Users ────────────────────────────────────────────────────────────────

    async def create_user(self, email: str, password: str, full_name: str = "") -> User:
        user = User(email=email, hashed_password=hash_password(password), full_name=full_name)
        self._s.add(user)
        await self._s.flush()
        return user

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self._s.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def authenticate(self, email: str, password: str) -> User | None:
        user = await self.get_user_by_email(email)
        if not user or not user.is_active:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    # ── Organizations ─────────────────────────────────────────────────────────

    async def create_org(self, name: str, slug: str, owner: User) -> Organization:
        org = Organization(name=name, slug=slug)
        self._s.add(org)
        await self._s.flush()

        member = OrganizationMember(
            organization_id=org.id,
            user_id=owner.id,
            role=Role.OWNER.value,
        )
        self._s.add(member)
        await self._s.flush()
        return org

    async def get_org_by_slug(self, slug: str) -> Organization | None:
        result = await self._s.execute(select(Organization).where(Organization.slug == slug))
        return result.scalar_one_or_none()

    async def get_user_orgs(self, user_id: uuid.UUID) -> list[tuple[Organization, str]]:
        result = await self._s.execute(
            select(OrganizationMember)
            .where(OrganizationMember.user_id == user_id)
            .options(selectinload(OrganizationMember.organization))
        )
        return [(m.organization, m.role) for m in result.scalars().all()]

    async def get_member_role(self, org_id: uuid.UUID, user_id: uuid.UUID) -> str | None:
        result = await self._s.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == user_id,
            )
        )
        m = result.scalar_one_or_none()
        return m.role if m else None

    async def add_member(self, org_id: uuid.UUID, user_id: uuid.UUID, role: str = Role.MEMBER.value) -> OrganizationMember:
        member = OrganizationMember(organization_id=org_id, user_id=user_id, role=role)
        self._s.add(member)
        await self._s.flush()
        return member

    # ── API Keys ──────────────────────────────────────────────────────────────

    async def create_api_key(
        self, org_id: uuid.UUID, name: str, scopes: list[str] | None = None
    ) -> tuple[str, APIKey]:
        raw, prefix, key_hash = generate_api_key()
        api_key = APIKey(
            organization_id=org_id,
            name=name,
            key_prefix=prefix,
            key_hash=key_hash,
            scopes=scopes or ["pipeline:run"],
        )
        self._s.add(api_key)
        await self._s.flush()
        return raw, api_key

    async def list_api_keys(self, org_id: uuid.UUID) -> list[APIKey]:
        result = await self._s.execute(
            select(APIKey).where(APIKey.organization_id == org_id).order_by(APIKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def revoke_api_key(self, key_id: uuid.UUID, org_id: uuid.UUID) -> bool:
        result = await self._s.execute(
            select(APIKey).where(APIKey.id == key_id, APIKey.organization_id == org_id)
        )
        key = result.scalar_one_or_none()
        if not key:
            return False
        key.is_active = False
        return True
