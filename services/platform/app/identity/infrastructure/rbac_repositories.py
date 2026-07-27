"""SQLAlchemy-backed Role, Permission, and UserRoleAssignment repositories."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.domain.rbac import Permission, Role, UserRoleAssignment
from app.identity.infrastructure import mappers
from app.identity.infrastructure.orm_models import (
    PermissionOrmModel,
    RoleOrmModel,
    RolePermissionOrmModel,
    UserRoleOrmModel,
)
from app.platform_core.errors.domain_exceptions import ConcurrencyConflictError
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7


class SqlAlchemyRoleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _load_permission_ids(self, role_id: EntityId) -> set[EntityId]:
        stmt = select(RolePermissionOrmModel.permission_id).where(RolePermissionOrmModel.role_id == role_id)
        result = (await self._session.execute(stmt)).scalars().all()
        return {EntityId(pid) for pid in result}

    async def get_by_id(self, role_id: EntityId) -> Role | None:
        row = await self._session.get(RoleOrmModel, role_id)
        if row is None:
            return None
        return mappers.role_to_domain(row, await self._load_permission_ids(role_id))

    async def get_by_name(self, org_id: OrgId | None, name: str) -> Role | None:
        stmt = select(RoleOrmModel).where(RoleOrmModel.org_id == org_id, RoleOrmModel.name == name)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return mappers.role_to_domain(row, await self._load_permission_ids(EntityId(row.id)))

    async def list_system_roles(self) -> list[Role]:
        stmt = select(RoleOrmModel).where(RoleOrmModel.is_system_role.is_(True))
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.role_to_domain(r, await self._load_permission_ids(EntityId(r.id))) for r in rows]

    async def list_for_org(self, org_id: OrgId) -> list[Role]:
        stmt = select(RoleOrmModel).where(RoleOrmModel.org_id == org_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.role_to_domain(r, await self._load_permission_ids(EntityId(r.id))) for r in rows]

    async def add(self, role: Role) -> None:
        self._session.add(mappers.role_to_orm(role))
        await self._sync_permissions(role)

    async def update(self, role: Role) -> None:
        row = await self._session.get(RoleOrmModel, role.id)
        if row is None:
            raise ValueError(f"Role {role.id} not found for update")
        if row.version != role.version:
            raise ConcurrencyConflictError("Role", role.id)
        mappers.role_to_orm(role, row)
        row.version = role.version + 1
        role.version += 1
        await self._sync_permissions(role)

    async def _sync_permissions(self, role: Role) -> None:
        existing = await self._load_permission_ids(role.id)
        to_add = role.permission_ids - existing
        to_remove = existing - role.permission_ids
        for permission_id in to_add:
            self._session.add(
                RolePermissionOrmModel(id=new_uuid7(), role_id=role.id, permission_id=permission_id)
            )
        if to_remove:
            stmt = delete(RolePermissionOrmModel).where(
                RolePermissionOrmModel.role_id == role.id, RolePermissionOrmModel.permission_id.in_(to_remove)
            )
            await self._session.execute(stmt)

    async def delete(self, role_id: EntityId) -> None:
        row = await self._session.get(RoleOrmModel, role_id)
        if row is not None:
            await self._session.execute(delete(RolePermissionOrmModel).where(RolePermissionOrmModel.role_id == role_id))
            await self._session.delete(row)


class SqlAlchemyPermissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, permission_id: EntityId) -> Permission | None:
        row = await self._session.get(PermissionOrmModel, permission_id)
        return mappers.permission_to_domain(row) if row else None

    async def get_by_key(self, resource: str, action: str) -> Permission | None:
        stmt = select(PermissionOrmModel).where(
            PermissionOrmModel.resource == resource, PermissionOrmModel.action == action
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.permission_to_domain(row) if row else None

    async def list_all(self) -> list[Permission]:
        rows = (await self._session.execute(select(PermissionOrmModel))).scalars().all()
        return [mappers.permission_to_domain(r) for r in rows]

    async def add(self, permission: Permission) -> None:
        self._session.add(mappers.permission_to_orm(permission))


class SqlAlchemyUserRoleAssignmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(self, user_id: UserId, org_id: OrgId) -> list[UserRoleAssignment]:
        stmt = select(UserRoleOrmModel).where(UserRoleOrmModel.user_id == user_id, UserRoleOrmModel.org_id == org_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.user_role_assignment_to_domain(r) for r in rows]

    async def get(self, user_id: UserId, role_id: EntityId) -> UserRoleAssignment | None:
        stmt = select(UserRoleOrmModel).where(UserRoleOrmModel.user_id == user_id, UserRoleOrmModel.role_id == role_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.user_role_assignment_to_domain(row) if row else None

    async def add(self, assignment: UserRoleAssignment) -> None:
        self._session.add(mappers.user_role_assignment_to_orm(assignment))

    async def delete(self, assignment_id: EntityId) -> None:
        row = await self._session.get(UserRoleOrmModel, assignment_id)
        if row is not None:
            await self._session.delete(row)
