import os
import pathlib
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.modules.registries.models import CitizenRegistryMockup, KK, VehicleRegistryMockup
from app.core.storage import StorageService

# Gunakan gambar orang dari utils/ sebagai placeholder foto KTP saat seeding
# parents[3] dari seed_data.py = mysuf_backend/
_UTILS_DIR = pathlib.Path(__file__).resolve().parents[3] / "utils"
_KTP_PLACEHOLDER_PATH = _UTILS_DIR / "gambar-orang-png-0.webp"
_KTP_PLACEHOLDER_CONTENT_TYPE = "image/webp"

def _load_ktp_placeholder() -> bytes:
    """Muat file placeholder KTP dari disk. Fallback ke bytes kosong jika tidak ditemukan."""
    try:
        return _KTP_PLACEHOLDER_PATH.read_bytes()
    except OSError:
        import logging
        logging.getLogger(__name__).warning(
            f"KTP placeholder file tidak ditemukan di {_KTP_PLACEHOLDER_PATH}. "
            "Seeding akan lanjut tanpa foto KTP."
        )
        return b""



DEFAULT_REGISTRY_SEED_DATA = {
    "kk": [
        {"code": "KK-320101-0001"},
        {"code": "KK-320101-0002"},
        {"code": "KK-320101-0003"},
        {"code": "KK-320101-0004"},
        {"code": "KK-320101-0005"},
    ],
    "citizens": [
        {"nik": "3511111411040003", "nama": "EKYA MUHAMMAD HASFI FADLILURRAHMAN", "ktp_nfc_id": "04290CEA936C80", "kk_code": "KK-320101-0001", "pekerjaan": "OJOL", "penghasilan": Decimal("3500000.00")},
        {"nik": "3201010101010001", "nama": "Ahmad Sulaiman", "ktp_nfc_id": "NFC-320101-0001", "kk_code": "KK-320101-0001", "pekerjaan": "NELAYAN", "penghasilan": Decimal("4000000.00")},
        {"nik": "3201010101010002", "nama": "Siti Rahmawati", "ktp_nfc_id": "NFC-320101-0002", "kk_code": "KK-320101-0001", "pekerjaan": "UMKM", "penghasilan": Decimal("3000000.00")},
        {"nik": "3201010101010003", "nama": "Budi Hartono", "ktp_nfc_id": "NFC-320101-0003", "kk_code": "KK-320101-0002", "pekerjaan": "KARYAWAN", "penghasilan": Decimal("7000000.00")},
        {"nik": "3201010101010004", "nama": "Dewi Lestari", "ktp_nfc_id": "NFC-320101-0004", "kk_code": "KK-320101-0002", "pekerjaan": "PNS", "penghasilan": Decimal("8000000.00")},
        {"nik": "3201010101010005", "nama": "Rizky Maulana", "ktp_nfc_id": "NFC-320101-0005", "kk_code": "KK-320101-0003", "pekerjaan": "OJOL", "penghasilan": Decimal("2500000.00")},
        {"nik": "3201010101010006", "nama": "Nadia Khairunnisa", "ktp_nfc_id": "NFC-320101-0006", "kk_code": "KK-320101-0003", "pekerjaan": "LAINNYA", "penghasilan": Decimal("4500000.00")},
        {"nik": "3201010101010007", "nama": "Fajar Nugroho", "ktp_nfc_id": "NFC-320101-0007", "kk_code": "KK-320101-0004", "pekerjaan": "LAINNYA", "penghasilan": Decimal("6000000.00")},
        {"nik": "3201010101010008", "nama": "Putri Ayuningtyas", "ktp_nfc_id": "NFC-320101-0008", "kk_code": "KK-320101-0004", "pekerjaan": "NELAYAN", "penghasilan": Decimal("2000000.00")},
        {"nik": "3201010101010009", "nama": "Yusuf Hidayat", "ktp_nfc_id": "NFC-320101-0009", "kk_code": "KK-320101-0005", "pekerjaan": "LAINNYA", "penghasilan": Decimal("12000000.00")},
        {"nik": "3201010101010010", "nama": "Intan Permatasari", "ktp_nfc_id": "NFC-320101-0010", "kk_code": "KK-320101-0005", "pekerjaan": "UMKM", "penghasilan": Decimal("2200000.00")},
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
    storage = StorageService()
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
        citizen.pekerjaan = item.get("pekerjaan")
        citizen.penghasilan = item.get("penghasilan")
        
        foto_ktp_key = f"citizen_ktp/{citizen.nik}.webp"
        citizen.foto_ktp = foto_ktp_key

        ktp_bytes = _load_ktp_placeholder()
        if ktp_bytes:
            try:
                storage.save_file(foto_ktp_key, ktp_bytes, _KTP_PLACEHOLDER_CONTENT_TYPE)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to seed MinIO image for citizen {citizen.nik}: {e}")



async def _seed_vehicles(
    session: AsyncSession,
    vehicle_items: Sequence[dict],
    summary: dict[str, int],
) -> None:
    for item in vehicle_items:
        result = await session.execute(
            select(VehicleRegistryMockup).filter(
                VehicleRegistryMockup.registration_number == item["registration_number"]
            )
        )
        vehicle = result.scalars().first()
        if vehicle is None:
            vehicle = VehicleRegistryMockup(
                plate_number=item["plate_number"],
                registration_number=item["registration_number"],
                brand=item["brand"],
                vehicle_type=item["vehicle_type"],
                manufacture_year=item["manufacture_year"],
                color=item["color"],
                engine_capacity_cc=item["engine_capacity_cc"],
                pkb=item["pkb"],
                njkb=item["njkb"],
                owner_name=item["owner_name"],
                owner_nik=item["owner_nik"],
            )
            session.add(vehicle)
            summary["vehicles"] += 1
            await session.flush()
