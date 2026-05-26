from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.modules.registries.models import CitizenRegistryMockup, KK, VehicleRegistryMockup, VehicleClass


DEFAULT_REGISTRY_SEED_DATA = {
    "kk": [
        {"code": "KK-320101-0001"},
        {"code": "KK-320101-0002"},
        {"code": "KK-320101-0003"},
        {"code": "KK-320101-0004"},
        {"code": "KK-320101-0005"},
    ],
    "citizens": [
        {"nik": "3511111411040003", "nama": "EKYA MUHAMMAD HASFI FADLILURRAHMAN", "ktp_nfc_id": "04290CEA936C80", "kk_code": "KK-320101-0001"},
        {"nik": "3201010101010001", "nama": "Ahmad Sulaiman", "ktp_nfc_id": "NFC-320101-0001", "kk_code": "KK-320101-0001"},
        {"nik": "3201010101010002", "nama": "Siti Rahmawati", "ktp_nfc_id": "NFC-320101-0002", "kk_code": "KK-320101-0001"},
        {"nik": "3201010101010003", "nama": "Budi Hartono", "ktp_nfc_id": "NFC-320101-0003", "kk_code": "KK-320101-0002"},
        {"nik": "3201010101010004", "nama": "Dewi Lestari", "ktp_nfc_id": "NFC-320101-0004", "kk_code": "KK-320101-0002"},
        {"nik": "3201010101010005", "nama": "Rizky Maulana", "ktp_nfc_id": "NFC-320101-0005", "kk_code": "KK-320101-0003"},
        {"nik": "3201010101010006", "nama": "Nadia Khairunnisa", "ktp_nfc_id": "NFC-320101-0006", "kk_code": "KK-320101-0003"},
        {"nik": "3201010101010007", "nama": "Fajar Nugroho", "ktp_nfc_id": "NFC-320101-0007", "kk_code": "KK-320101-0004"},
        {"nik": "3201010101010008", "nama": "Putri Ayuningtyas", "ktp_nfc_id": "NFC-320101-0008", "kk_code": "KK-320101-0004"},
        {"nik": "3201010101010009", "nama": "Yusuf Hidayat", "ktp_nfc_id": "NFC-320101-0009", "kk_code": "KK-320101-0005"},
        {"nik": "3201010101010010", "nama": "Intan Permatasari", "ktp_nfc_id": "NFC-320101-0010", "kk_code": "KK-320101-0005"},
    ],
    "vehicles": [
        {"plate_number": "B 1234 KKA", "registration_number": "STNK-320101-0001", "brand": "Honda", "vehicle_type": "Beat", "manufacture_year": 2020, "color": "Hitam", "engine_capacity_cc": 110, "pkb": Decimal("350000.00"), "njkb": Decimal("14500000.00"), "owner_name": "Ahmad Sulaiman", "owner_nik": "3201010101010001", "jenis": VehicleClass.MOTORCYCLE},
        {"plate_number": "B 1235 KKA", "registration_number": "STNK-320101-0002", "brand": "Yamaha", "vehicle_type": "NMAX", "manufacture_year": 2021, "color": "Merah", "engine_capacity_cc": 155, "pkb": Decimal("550000.00"), "njkb": Decimal("28500000.00"), "owner_name": "Siti Rahmawati", "owner_nik": "3201010101010002", "jenis": VehicleClass.MOTORCYCLE},
        {"plate_number": "B 2234 KKB", "registration_number": "STNK-320101-0003", "brand": "Toyota", "vehicle_type": "Avanza", "manufacture_year": 2019, "color": "Putih", "engine_capacity_cc": 1329, "pkb": Decimal("1850000.00"), "njkb": Decimal("135000000.00"), "owner_name": "Budi Hartono", "owner_nik": "3201010101010003", "jenis": VehicleClass.CAR},
        {"plate_number": "B 2235 KKB", "registration_number": "STNK-320101-0004", "brand": "Daihatsu", "vehicle_type": "Xenia", "manufacture_year": 2018, "color": "Silver", "engine_capacity_cc": 1298, "pkb": Decimal("1750000.00"), "njkb": Decimal("125000000.00"), "owner_name": "Dewi Lestari", "owner_nik": "3201010101010004", "jenis": VehicleClass.CAR},
        {"plate_number": "B 3234 KKC", "registration_number": "STNK-320101-0005", "brand": "Suzuki", "vehicle_type": "Ertiga", "manufacture_year": 2022, "color": "Abu-Abu", "engine_capacity_cc": 1462, "pkb": Decimal("2100000.00"), "njkb": Decimal("178000000.00"), "owner_name": "Rizky Maulana", "owner_nik": "3201010101010005", "jenis": VehicleClass.CAR},
        {"plate_number": "B 3235 KKC", "registration_number": "STNK-320101-0006", "brand": "Mitsubishi", "vehicle_type": "Xpander", "manufacture_year": 2021, "color": "Hitam", "engine_capacity_cc": 1499, "pkb": Decimal("2250000.00"), "njkb": Decimal("225000000.00"), "owner_name": "Nadia Khairunnisa", "owner_nik": "3201010101010006", "jenis": VehicleClass.CAR},
        {"plate_number": "B 4234 KKD", "registration_number": "STNK-320101-0007", "brand": "Honda", "vehicle_type": "Vario 160", "manufacture_year": 2023, "color": "Biru", "engine_capacity_cc": 160, "pkb": Decimal("475000.00"), "njkb": Decimal("26500000.00"), "owner_name": "Fajar Nugroho", "owner_nik": "3201010101010007", "jenis": VehicleClass.MOTORCYCLE},
        {"plate_number": "B 4235 KKD", "registration_number": "STNK-320101-0008", "brand": "Yamaha", "vehicle_type": "Fazzio", "manufacture_year": 2023, "color": "Cream", "engine_capacity_cc": 125, "pkb": Decimal("410000.00"), "njkb": Decimal("22500000.00"), "owner_name": "Putri Ayuningtyas", "owner_nik": "3201010101010008", "jenis": VehicleClass.MOTORCYCLE},
        {"plate_number": "B 5234 KKE", "registration_number": "STNK-320101-0009", "brand": "Toyota", "vehicle_type": "Calya", "manufacture_year": 2020, "color": "Putih", "engine_capacity_cc": 1197, "pkb": Decimal("1650000.00"), "njkb": Decimal("148000000.00"), "owner_name": "Yusuf Hidayat", "owner_nik": "3201010101010009", "jenis": VehicleClass.CAR},
        {"plate_number": "B 5235 KKE", "registration_number": "STNK-320101-0010", "brand": "Honda", "vehicle_type": "Brio", "manufacture_year": 2022, "color": "Kuning", "engine_capacity_cc": 1199, "pkb": Decimal("1950000.00"), "njkb": Decimal("182000000.00"), "owner_name": "Intan Permatasari", "owner_nik": "3201010101010010", "jenis": VehicleClass.CAR},
        {"plate_number": "B 6234 KKF", "registration_number": "STNK-320101-0011", "brand": "Suzuki", "vehicle_type": "Carry", "manufacture_year": 2017, "color": "Hitam", "engine_capacity_cc": 1493, "pkb": Decimal("1450000.00"), "njkb": Decimal("98000000.00"), "owner_name": "Ahmad Sulaiman", "owner_nik": "3201010101010001", "jenis": VehicleClass.TRUCK},
        {"plate_number": "B 6235 KKF", "registration_number": "STNK-320101-0012", "brand": "Mitsubishi", "vehicle_type": "Pajero Sport", "manufacture_year": 2021, "color": "Putih", "engine_capacity_cc": 2442, "pkb": Decimal("5250000.00"), "njkb": Decimal("498000000.00"), "owner_name": "Budi Hartono", "owner_nik": "3201010101010003", "jenis": VehicleClass.CAR},
        {"plate_number": "B 3511 EKY", "registration_number": "STNK-351111-0001", "brand": "Toyota", "vehicle_type": "Innova", "manufacture_year": 2022, "color": "Hitam", "engine_capacity_cc": 1998, "pkb": Decimal("3800000.00"), "njkb": Decimal("320000000.00"), "owner_name": "EKYA MUHAMMAD HASFI FADLILURRAHMAN", "owner_nik": "3511111411040003", "jenis": VehicleClass.CAR},
    ],
}


async def seed_registry_mockups(
    session: AsyncSession,
    seed_data: dict[str, Sequence[dict]] | None = None,
) -> dict[str, int]:
    dataset = seed_data or DEFAULT_REGISTRY_SEED_DATA
    summary = {"kk": 0, "citizens": 0, "vehicles": 0}

    kk_by_code = await _seed_kk(session, dataset.get("kk", ()), summary)
    await _seed_citizens(session, dataset.get("citizens", ()), kk_by_code, summary)
    await _seed_vehicles(session, dataset.get("vehicles", ()), summary)

    await session.commit()
    return summary


async def _seed_kk(
    session: AsyncSession,
    kk_items: Sequence[dict],
    summary: dict[str, int],
) -> dict[str, KK]:
    kk_by_code: dict[str, KK] = {}
    for item in kk_items:
        result = await session.execute(select(KK).filter(KK.code == item["code"]))
        kk = result.scalars().first()
        if kk is None:
            kk = KK(code=item["code"])
            session.add(kk)
            summary["kk"] += 1
            await session.flush()
        kk_by_code[item["code"]] = kk
    return kk_by_code


async def _seed_citizens(
    session: AsyncSession,
    citizen_items: Sequence[dict],
    kk_by_code: dict[str, KK],
    summary: dict[str, int],
) -> None:
    for item in citizen_items:
        kk = kk_by_code.get(item["kk_code"])
        if kk is None:
            raise ValueError(f"KK code {item['kk_code']} was not seeded before citizen {item['nik']}")

        result = await session.execute(
            select(CitizenRegistryMockup).filter(CitizenRegistryMockup.nik == item["nik"])
        )
        citizen = result.scalars().first()
        if citizen is None:
            citizen = CitizenRegistryMockup(nik=item["nik"])
            session.add(citizen)
            summary["citizens"] += 1

        citizen.nama = item["nama"]
        citizen.ktp_nfc_id = item["ktp_nfc_id"]
        citizen.kk_id = kk.id


async def _seed_vehicles(
    session: AsyncSession,
    vehicle_items: Sequence[dict],
    summary: dict[str, int],
) -> None:
    for item in vehicle_items:
        result = await session.execute(
            select(VehicleRegistryMockup).filter(
                and_(
                    VehicleRegistryMockup.plate_number == item["plate_number"],
                    VehicleRegistryMockup.registration_number == item["registration_number"],
                )
            )
        )
        vehicle = result.scalars().first()
        if vehicle is None:
            vehicle = VehicleRegistryMockup(
                plate_number=item["plate_number"],
                registration_number=item["registration_number"],
            )
            session.add(vehicle)
            summary["vehicles"] += 1

        vehicle.brand = item["brand"]
        vehicle.vehicle_type = item["vehicle_type"]
        vehicle.manufacture_year = item["manufacture_year"]
        vehicle.color = item["color"]
        vehicle.engine_capacity_cc = item["engine_capacity_cc"]
        vehicle.pkb = item["pkb"]
        vehicle.njkb = item["njkb"]
        vehicle.owner_name = item["owner_name"]
        vehicle.owner_nik = item["owner_nik"]
        vehicle.jenis = item.get("jenis")
