from typing import List, Optional
from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.registries.models import CitizenRegistryMockup, KK

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

