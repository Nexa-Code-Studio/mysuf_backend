from typing import List, Optional
from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.registries.models import CitizenRegistryMockup, KK, VehicleRegistryMockup

class RegistryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ----------------------------------------------------
    # KK (Kartu Keluarga) CRUD
    # ----------------------------------------------------
    async def get_kk_by_id(self, kk_id: str | UUID) -> KK | None:
        result = await self.db.execute(select(KK).filter(KK.id == kk_id))
        return result.scalars().first()

    async def get_kk_by_code(self, code: str) -> KK | None:
        result = await self.db.execute(select(KK).filter(KK.code == code))
        return result.scalars().first()

    async def get_kks(self, skip: int = 0, limit: int = 100) -> List[KK]:
        result = await self.db.execute(select(KK).offset(skip).limit(limit))
        return list(result.scalars().all())

    async def count_kks(self) -> int:
        result = await self.db.execute(select(func.count()).select_from(KK))
        return result.scalar() or 0

    async def create_kk(self, kk: KK) -> KK:
        self.db.add(kk)
        await self.db.commit()
        await self.db.refresh(kk)
        return kk

    async def update_kk(self, kk: KK) -> KK:
        await self.db.commit()
        await self.db.refresh(kk)
        return kk

    async def delete_kk(self, kk: KK) -> None:
        await self.db.delete(kk)
        await self.db.commit()

    # ----------------------------------------------------
    # CitizenRegistryMockup CRUD
    # ----------------------------------------------------
    async def get_citizen_by_id(self, citizen_id: str | UUID) -> CitizenRegistryMockup | None:
        result = await self.db.execute(
            select(CitizenRegistryMockup).filter(CitizenRegistryMockup.id == citizen_id)
        )
        return result.scalars().first()

    async def get_citizen_by_nik(self, nik: str) -> CitizenRegistryMockup | None:
        result = await self.db.execute(
            select(CitizenRegistryMockup).filter(CitizenRegistryMockup.nik == nik)
        )
        return result.scalars().first()

    async def get_citizen_by_ktp_nfc_id(self, ktp_nfc_id: str) -> CitizenRegistryMockup | None:
        result = await self.db.execute(
            select(CitizenRegistryMockup).filter(CitizenRegistryMockup.ktp_nfc_id == ktp_nfc_id)
        )
        return result.scalars().first()

    async def get_citizens(self, skip: int = 0, limit: int = 100) -> List[CitizenRegistryMockup]:
        result = await self.db.execute(select(CitizenRegistryMockup).offset(skip).limit(limit))
        return list(result.scalars().all())

    async def count_citizens(self) -> int:
        result = await self.db.execute(select(func.count()).select_from(CitizenRegistryMockup))
        return result.scalar() or 0

    async def create_citizen(self, citizen: CitizenRegistryMockup) -> CitizenRegistryMockup:
        self.db.add(citizen)
        await self.db.commit()
        await self.db.refresh(citizen)
        return citizen

    async def update_citizen(self, citizen: CitizenRegistryMockup) -> CitizenRegistryMockup:
        await self.db.commit()
        await self.db.refresh(citizen)
        return citizen

    async def delete_citizen(self, citizen: CitizenRegistryMockup) -> None:
        await self.db.delete(citizen)
        await self.db.commit()

    # ----------------------------------------------------
    # VehicleRegistryMockup CRUD
    # ----------------------------------------------------
    async def get_vehicle_by_id(self, vehicle_id: str | UUID) -> VehicleRegistryMockup | None:
        result = await self.db.execute(
            select(VehicleRegistryMockup).filter(VehicleRegistryMockup.id == vehicle_id)
        )
        return result.scalars().first()

    async def get_vehicle_by_plate(self, plate_number: str) -> VehicleRegistryMockup | None:
        result = await self.db.execute(
            select(VehicleRegistryMockup).filter(VehicleRegistryMockup.plate_number == plate_number)
        )
        return result.scalars().first()

    async def get_vehicle_by_registration(self, registration_number: str) -> VehicleRegistryMockup | None:
        result = await self.db.execute(
            select(VehicleRegistryMockup).filter(VehicleRegistryMockup.registration_number == registration_number)
        )
        return result.scalars().first()

    async def get_vehicles(self, skip: int = 0, limit: int = 100) -> List[VehicleRegistryMockup]:
        result = await self.db.execute(select(VehicleRegistryMockup).offset(skip).limit(limit))
        return list(result.scalars().all())

    async def count_vehicles(self) -> int:
        result = await self.db.execute(select(func.count()).select_from(VehicleRegistryMockup))
        return result.scalar() or 0

    async def create_vehicle(self, vehicle: VehicleRegistryMockup) -> VehicleRegistryMockup:
        self.db.add(vehicle)
        await self.db.commit()
        await self.db.refresh(vehicle)
        return vehicle

    async def update_vehicle(self, vehicle: VehicleRegistryMockup) -> VehicleRegistryMockup:
        await self.db.commit()
        await self.db.refresh(vehicle)
        return vehicle

    async def delete_vehicle(self, vehicle: VehicleRegistryMockup) -> None:
        await self.db.delete(vehicle)
        await self.db.commit()
