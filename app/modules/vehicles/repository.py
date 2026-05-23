from typing import List
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.registries.models import VehicleRegistryMockup
from app.modules.users.models import BuyerProfile, User
from app.modules.vehicles.models import (
    VehicleOwnership,
    VehicleOwnershipDocument,
    VehicleOwnershipRequest,
    VehicleOwnershipRequestDocument,
)


class VehicleRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_vehicle_ownership_by_id(self, ownership_id: str | UUID) -> VehicleOwnership | None:
        result = await self.db.execute(
            select(VehicleOwnership)
            .options(selectinload(VehicleOwnership.documents))
            .filter(VehicleOwnership.id == ownership_id)
        )
        return result.scalars().first()

    async def get_vehicle_ownerships(self, skip: int = 0, limit: int = 100) -> List[VehicleOwnership]:
        result = await self.db.execute(
            select(VehicleOwnership)
            .options(selectinload(VehicleOwnership.documents))
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_vehicle_ownerships(self) -> int:
        result = await self.db.execute(select(func.count()).select_from(VehicleOwnership))
        return result.scalar() or 0

    async def update_vehicle_ownership(self, ownership: VehicleOwnership) -> VehicleOwnership:
        await self.db.commit()
        await self.db.refresh(ownership)
        return ownership

    async def create_vehicle_ownership(self, ownership: VehicleOwnership) -> VehicleOwnership:
        self.db.add(ownership)
        await self.db.flush()
        return ownership

    async def add_documents(self, documents: list[VehicleOwnershipDocument]) -> None:
        self.db.add_all(documents)

    async def commit(self) -> None:
        await self.db.commit()

    async def rollback(self) -> None:
        await self.db.rollback()

    async def refresh_vehicle_ownership(self, ownership: VehicleOwnership) -> VehicleOwnership:
        await self.db.refresh(ownership)
        return ownership

    async def get_vehicle_registry_by_registration(self, registration_number: str) -> VehicleRegistryMockup | None:
        result = await self.db.execute(
            select(VehicleRegistryMockup).filter(
                VehicleRegistryMockup.registration_number == registration_number
            )
        )
        return result.scalars().first()

    async def get_buyer_profile_by_user_id(self, user_id: str | UUID) -> BuyerProfile | None:
        result = await self.db.execute(
            select(BuyerProfile).filter(BuyerProfile.user_id == user_id)
        )
        return result.scalars().first()

    async def create_vehicle_ownership_request(
        self,
        request: VehicleOwnershipRequest,
    ) -> VehicleOwnershipRequest:
        self.db.add(request)
        await self.db.flush()
        return request

    async def add_request_documents(self, documents: list[VehicleOwnershipRequestDocument]) -> None:
        self.db.add_all(documents)

    async def get_vehicle_ownership_request_by_id(
        self,
        request_id: str | UUID,
    ) -> VehicleOwnershipRequest | None:
        result = await self.db.execute(
            select(VehicleOwnershipRequest)
            .options(selectinload(VehicleOwnershipRequest.documents))
            .filter(VehicleOwnershipRequest.id == request_id)
        )
        return result.scalars().first()
