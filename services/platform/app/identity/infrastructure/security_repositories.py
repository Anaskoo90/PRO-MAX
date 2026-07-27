"""SQLAlchemy-backed TrustedDevice repository (Security submodule)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.domain.security_entities import TrustedDevice
from app.identity.infrastructure import mappers
from app.identity.infrastructure.orm_models import TrustedDeviceOrmModel
from app.platform_core.shared_kernel.types import EntityId, UserId


class SqlAlchemyTrustedDeviceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_fingerprint_hash(self, user_id: UserId, fingerprint_hash: str) -> TrustedDevice | None:
        stmt = select(TrustedDeviceOrmModel).where(
            TrustedDeviceOrmModel.user_id == user_id,
            TrustedDeviceOrmModel.device_fingerprint_hash == fingerprint_hash,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.trusted_device_to_domain(row) if row else None

    async def list_for_user(self, user_id: UserId) -> list[TrustedDevice]:
        stmt = select(TrustedDeviceOrmModel).where(TrustedDeviceOrmModel.user_id == user_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.trusted_device_to_domain(r) for r in rows]

    async def add(self, device: TrustedDevice) -> None:
        self._session.add(mappers.trusted_device_to_orm(device))

    async def delete(self, device_id: EntityId) -> None:
        row = await self._session.get(TrustedDeviceOrmModel, device_id)
        if row is not None:
            await self._session.delete(row)
