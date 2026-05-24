from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.registries.models import CitizenRegistryMockup, KK, VehicleRegistryMockup
from app.modules.registries.repository import RegistryRepository
from app.modules.registries.schemas import (
    CitizenCreate,
    CitizenUpdate,
    KKCreate,
    KKUpdate,
    VehicleCreate,
    VehicleUpdate,
)

class RegistryService:
    def __init__(self, db: AsyncSession):
        self.repo = RegistryRepository(db)

    # ----------------------------------------------------
    # KK (Kartu Keluarga) Service Methods
    # ----------------------------------------------------
    async def get_kks(self, page: int = 1, page_size: int = 20) -> dict:
        skip = (page - 1) * page_size
        limit = page_size

        items = await self.repo.get_kks(skip=skip, limit=limit)
        total = await self.repo.count_kks()
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0

        return {
            "items": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
            },
        }

    async def get_kk(self, kk_id: str) -> KK:
        kk = await self.repo.get_kk_by_id(kk_id)
        if not kk:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="KK not found")
        return kk

    async def create_kk(self, kk_in: KKCreate) -> KK:
        existing = await self.repo.get_kk_by_code(kk_in.code)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"KK code {kk_in.code} already exists",
            )
        db_kk = KK(code=kk_in.code)
        return await self.repo.create_kk(db_kk)

    async def update_kk(self, kk_id: str, kk_in: KKUpdate) -> KK:
        kk = await self.get_kk(kk_id)

        if kk_in.code is not None and kk_in.code != kk.code:
            existing = await self.repo.get_kk_by_code(kk_in.code)
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"KK code {kk_in.code} already exists",
                )
            kk.code = kk_in.code

        return await self.repo.update_kk(kk)

    async def delete_kk(self, kk_id: str) -> None:
        kk = await self.get_kk(kk_id)
        await self.repo.delete_kk(kk)

    # ----------------------------------------------------
    # CitizenRegistryMockup Service Methods
    # ----------------------------------------------------
    async def get_citizens(self, page: int = 1, page_size: int = 20) -> dict:
        skip = (page - 1) * page_size
        limit = page_size

        items = await self.repo.get_citizens(skip=skip, limit=limit)
        total = await self.repo.count_citizens()
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0

        return {
            "items": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
            },
        }

    async def get_citizen(self, citizen_id: str) -> CitizenRegistryMockup:
        citizen = await self.repo.get_citizen_by_id(citizen_id)
        if not citizen:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Citizen registry entry not found")
        return citizen

    async def create_citizen(self, citizen_in: CitizenCreate) -> CitizenRegistryMockup:
        # Validate KK ID exists
        kk = await self.repo.get_kk_by_id(citizen_in.kk_id)
        if not kk:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"KK with ID {citizen_in.kk_id} does not exist",
            )

        # Validate unique NIK
        existing_nik = await self.repo.get_citizen_by_nik(citizen_in.nik)
        if existing_nik:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Citizen with NIK {citizen_in.nik} already exists",
            )

        # Validate unique KTP NFC ID
        existing_nfc = await self.repo.get_citizen_by_ktp_nfc_id(citizen_in.ktp_nfc_id)
        if existing_nfc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Citizen with KTP NFC ID {citizen_in.ktp_nfc_id} already exists",
            )

        db_citizen = CitizenRegistryMockup(
            nik=citizen_in.nik,
            nama=citizen_in.nama,
            ktp_nfc_id=citizen_in.ktp_nfc_id,
            kk_id=citizen_in.kk_id,
        )
        return await self.repo.create_citizen(db_citizen)

    async def update_citizen(self, citizen_id: str, citizen_in: CitizenUpdate) -> CitizenRegistryMockup:
        citizen = await self.get_citizen(citizen_id)

        if citizen_in.kk_id is not None and citizen_in.kk_id != citizen.kk_id:
            kk = await self.repo.get_kk_by_id(citizen_in.kk_id)
            if not kk:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"KK with ID {citizen_in.kk_id} does not exist",
                )
            citizen.kk_id = citizen_in.kk_id

        if citizen_in.nik is not None and citizen_in.nik != citizen.nik:
            existing_nik = await self.repo.get_citizen_by_nik(citizen_in.nik)
            if existing_nik:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Citizen with NIK {citizen_in.nik} already exists",
                )
            citizen.nik = citizen_in.nik

        if citizen_in.ktp_nfc_id is not None and citizen_in.ktp_nfc_id != citizen.ktp_nfc_id:
            existing_nfc = await self.repo.get_citizen_by_ktp_nfc_id(citizen_in.ktp_nfc_id)
            if existing_nfc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Citizen with KTP NFC ID {citizen_in.ktp_nfc_id} already exists",
                )
            citizen.ktp_nfc_id = citizen_in.ktp_nfc_id

        if citizen_in.nama is not None:
            citizen.nama = citizen_in.nama

        return await self.repo.update_citizen(citizen)

    async def delete_citizen(self, citizen_id: str) -> None:
        citizen = await self.get_citizen(citizen_id)
        await self.repo.delete_citizen(citizen)

    # ----------------------------------------------------
    # VehicleRegistryMockup Service Methods
    # ----------------------------------------------------
    async def get_vehicles(self, page: int = 1, page_size: int = 20) -> dict:
        skip = (page - 1) * page_size
        limit = page_size

        items = await self.repo.get_vehicles(skip=skip, limit=limit)
        total = await self.repo.count_vehicles()
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0

        return {
            "items": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
            },
        }

    async def get_vehicle(self, vehicle_id: str) -> VehicleRegistryMockup:
        vehicle = await self.repo.get_vehicle_by_id(vehicle_id)
        if not vehicle:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle registry entry not found")
        return vehicle

    async def create_vehicle(self, vehicle_in: VehicleCreate) -> VehicleRegistryMockup:
        # Validate unique STNK registration number
        existing_reg = await self.repo.get_vehicle_by_registration(vehicle_in.registration_number)
        if existing_reg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Vehicle with registration number {vehicle_in.registration_number} already exists",
            )

        db_vehicle = VehicleRegistryMockup(
            plate_number=vehicle_in.plate_number,
            registration_number=vehicle_in.registration_number,
            brand=vehicle_in.brand,
            vehicle_type=vehicle_in.vehicle_type,
            manufacture_year=vehicle_in.manufacture_year,
            color=vehicle_in.color,
            engine_capacity_cc=vehicle_in.engine_capacity_cc,
            pkb=vehicle_in.pkb,
            njkb=vehicle_in.njkb,
            owner_name=vehicle_in.owner_name,
            owner_nik=vehicle_in.owner_nik,
        )
        return await self.repo.create_vehicle(db_vehicle)

    async def update_vehicle(self, vehicle_id: str, vehicle_in: VehicleUpdate) -> VehicleRegistryMockup:
        vehicle = await self.get_vehicle(vehicle_id)

        if vehicle_in.registration_number is not None and vehicle_in.registration_number != vehicle.registration_number:
            existing_reg = await self.repo.get_vehicle_by_registration(vehicle_in.registration_number)
            if existing_reg:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Vehicle with registration number {vehicle_in.registration_number} already exists",
                )
            vehicle.registration_number = vehicle_in.registration_number

        update_data = vehicle_in.model_dump(exclude_unset=True)
        # Exclude registration_number since we already handled it above
        update_data.pop("registration_number", None)

        for field, value in update_data.items():
            setattr(vehicle, field, value)

        return await self.repo.update_vehicle(vehicle)

    async def delete_vehicle(self, vehicle_id: str) -> None:
        vehicle = await self.get_vehicle(vehicle_id)
        await self.repo.delete_vehicle(vehicle)
