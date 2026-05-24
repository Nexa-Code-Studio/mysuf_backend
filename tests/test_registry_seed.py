from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select

from app.core.database import AsyncSessionLocal
from app.modules.registries.models import CitizenRegistryMockup, KK, VehicleRegistryMockup
from app.modules.registries.seed_data import seed_registry_mockups


TEST_REGISTRY_SEED_DATA = {
    "kk": [
        {"code": "TEST-KK-REGISTRY-0001"},
        {"code": "TEST-KK-REGISTRY-0002"},
    ],
    "citizens": [
        {
            "nik": "9990000000000001",
            "nama": "Warga Test Satu",
            "ktp_nfc_id": "TEST-NFC-0001",
            "kk_code": "TEST-KK-REGISTRY-0001",
        },
        {
            "nik": "9990000000000002",
            "nama": "Warga Test Dua",
            "ktp_nfc_id": "TEST-NFC-0002",
            "kk_code": "TEST-KK-REGISTRY-0002",
        },
    ],
    "vehicles": [
        {
            "plate_number": "B 9001 TST",
            "registration_number": "TEST-STNK-0001",
            "brand": "Honda",
            "vehicle_type": "Scoopy",
            "manufacture_year": 2022,
            "color": "Hijau",
            "engine_capacity_cc": 110,
            "pkb": Decimal("410000.00"),
            "njkb": Decimal("21500000.00"),
            "owner_name": "Warga Test Satu",
            "owner_nik": "9990000000000001",
        },
        {
            "plate_number": "B 9002 TST",
            "registration_number": "TEST-STNK-0002",
            "brand": "Toyota",
            "vehicle_type": "Raize",
            "manufacture_year": 2023,
            "color": "Putih",
            "engine_capacity_cc": 998,
            "pkb": Decimal("2350000.00"),
            "njkb": Decimal("238000000.00"),
            "owner_name": "Warga Test Dua",
            "owner_nik": "9990000000000002",
        },
    ],
}


@pytest.mark.anyio
async def test_seed_registry_mockups_is_idempotent_and_consistent():
    kk_codes = [item["code"] for item in TEST_REGISTRY_SEED_DATA["kk"]]
    citizen_niks = [item["nik"] for item in TEST_REGISTRY_SEED_DATA["citizens"]]
    vehicle_registration_numbers = [item["registration_number"] for item in TEST_REGISTRY_SEED_DATA["vehicles"]]

    try:
        async with AsyncSessionLocal() as session:
            first_summary = await seed_registry_mockups(session, TEST_REGISTRY_SEED_DATA)
            assert first_summary == {"kk": 2, "citizens": 2, "vehicles": 2}

        async with AsyncSessionLocal() as session:
            second_summary = await seed_registry_mockups(session, TEST_REGISTRY_SEED_DATA)
            assert second_summary == {"kk": 0, "citizens": 0, "vehicles": 0}

        async with AsyncSessionLocal() as session:
            kk_count = await session.scalar(
                select(func.count()).select_from(KK).where(KK.code.in_(kk_codes))
            )
            citizen_count = await session.scalar(
                select(func.count()).select_from(CitizenRegistryMockup).where(CitizenRegistryMockup.nik.in_(citizen_niks))
            )
            vehicle_count = await session.scalar(
                select(func.count()).select_from(VehicleRegistryMockup).where(VehicleRegistryMockup.registration_number.in_(vehicle_registration_numbers))
            )

            assert kk_count == 2
            assert citizen_count == 2
            assert vehicle_count == 2

            citizen_owner_niks = set(
                (
                    await session.execute(
                        select(CitizenRegistryMockup.nik).where(CitizenRegistryMockup.nik.in_(citizen_niks))
                    )
                ).scalars().all()
            )
            vehicle_owner_niks = set(
                (
                    await session.execute(
                        select(VehicleRegistryMockup.owner_nik).where(
                            VehicleRegistryMockup.registration_number.in_(vehicle_registration_numbers)
                        )
                    )
                ).scalars().all()
            )

            assert vehicle_owner_niks == citizen_owner_niks
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(VehicleRegistryMockup).where(
                    VehicleRegistryMockup.registration_number.in_(vehicle_registration_numbers)
                )
            )
            await session.execute(
                delete(CitizenRegistryMockup).where(CitizenRegistryMockup.nik.in_(citizen_niks))
            )
            await session.execute(delete(KK).where(KK.code.in_(kk_codes)))
            await session.commit()
