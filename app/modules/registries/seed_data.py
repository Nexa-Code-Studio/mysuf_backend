import os
import pathlib
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.modules.registries.models import CitizenRegistryMockup, KK, VehicleRegistryMockup, VehicleClass
from app.core.storage import StorageService

# Gunakan gambar orang dari utils/ sebagai placeholder foto KTP saat seeding
# parents[3] dari seed_data.py = subsidia_backend/
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
        {"nik": "3511111411040003", "nama": "EKYA MUHAMMAD HASFI FADLILURRAHMAN", "ktp_nfc_id": "04290CEA936C99", "kk_code": "KK-320101-0001", "pekerjaan": "OJOL", "penghasilan": Decimal("3500000.00")},
        {"nik": "3511111411049999", "nama": "BUDI PRATAMA", "ktp_nfc_id": "04290CEA936C80", "kk_code": "KK-320101-0001", "pekerjaan": "OJOL", "penghasilan": Decimal("3500000.00")},
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
    "vehicles": [
        # Budi Pratama (3511111411049999)
        {
            "plate_number": "B 3511 EKY",
            "registration_number": "REG-3511-EKY",
            "brand": "Toyota",
            "vehicle_type": "Avanza",
            "jenis": VehicleClass.CAR,
            "manufacture_year": 2020,
            "color": "Hitam",
            "engine_capacity_cc": 1496,
            "pkb": Decimal("3000000.00"),
            "njkb": Decimal("180000000.00"),
            "owner_name": "BUDI PRATAMA",
            "owner_nik": "3511111411049999",
            "vehicle_nfc_id": "VEH-NFC-3511-EKY",
        },
        {
            "plate_number": "N 1234 AB",
            "registration_number": "REG-1234-AB",
            "brand": "Honda",
            "vehicle_type": "Scoopy",
            "jenis": VehicleClass.MOTORCYCLE,
            "manufacture_year": 2021,
            "color": "Merah",
            "engine_capacity_cc": 110,
            "pkb": Decimal("350000.00"),
            "njkb": Decimal("18000000.00"),
            "owner_name": "BUDI PRATAMA",
            "owner_nik": "3511111411049999",
            "vehicle_nfc_id": "VEH-NFC-1234-AB",
        },
        {
            "plate_number": "L 9876 CD",
            "registration_number": "REG-9876-CD",
            "brand": "Mitsubishi",
            "vehicle_type": "L300",
            "jenis": VehicleClass.TRUCK,
            "manufacture_year": 2018,
            "color": "Cokelat",
            "engine_capacity_cc": 2500,
            "pkb": Decimal("1500000.00"),
            "njkb": Decimal("90000000.00"),
            "owner_name": "BUDI PRATAMA",
            "owner_nik": "3511111411049999",
            "vehicle_nfc_id": "VEH-NFC-9876-CD",
        },
        # Other Citizens
        {
            "plate_number": "B 1001 SLS",
            "registration_number": "REG-1001-SLS",
            "brand": "Yamaha",
            "vehicle_type": "NMAX",
            "jenis": VehicleClass.MOTORCYCLE,
            "manufacture_year": 2022,
            "color": "Biru",
            "engine_capacity_cc": 155,
            "pkb": Decimal("450000.00"),
            "njkb": Decimal("28000000.00"),
            "owner_name": "Ahmad Sulaiman",
            "owner_nik": "3201010101010001",
            "vehicle_nfc_id": "VEH-NFC-1001-SLS",
        },
        {
            "plate_number": "B 1002 STR",
            "registration_number": "REG-1002-STR",
            "brand": "Daihatsu",
            "vehicle_type": "Sigra",
            "jenis": VehicleClass.CAR,
            "manufacture_year": 2021,
            "color": "Putih",
            "engine_capacity_cc": 1197,
            "pkb": Decimal("2200000.00"),
            "njkb": Decimal("120000000.00"),
            "owner_name": "Siti Rahmawati",
            "owner_nik": "3201010101010002",
            "vehicle_nfc_id": "VEH-NFC-1002-STR",
        },
        {
            "plate_number": "B 1003 BDH",
            "registration_number": "REG-1003-BDH",
            "brand": "Toyota",
            "vehicle_type": "Innova",
            "jenis": VehicleClass.CAR,
            "manufacture_year": 2018,
            "color": "Abu-abu",
            "engine_capacity_cc": 1998,
            "pkb": Decimal("4500000.00"),
            "njkb": Decimal("250000000.00"),
            "owner_name": "Budi Hartono",
            "owner_nik": "3201010101010003",
            "vehicle_nfc_id": "VEH-NFC-1003-BDH",
        },
        {
            "plate_number": "B 1004 DWL",
            "registration_number": "REG-1004-DWL",
            "brand": "Honda",
            "vehicle_type": "Vario",
            "jenis": VehicleClass.MOTORCYCLE,
            "manufacture_year": 2023,
            "color": "Hitam",
            "engine_capacity_cc": 125,
            "pkb": Decimal("400000.00"),
            "njkb": Decimal("22000000.00"),
            "owner_name": "Dewi Lestari",
            "owner_nik": "3201010101010004",
            "vehicle_nfc_id": "VEH-NFC-1004-DWL",
        },
        {
            "plate_number": "B 1005 RZM",
            "registration_number": "REG-1005-RZM",
            "brand": "Suzuki",
            "vehicle_type": "Carry",
            "jenis": VehicleClass.TRUCK,
            "manufacture_year": 2017,
            "color": "Silver",
            "engine_capacity_cc": 1493,
            "pkb": Decimal("1200000.00"),
            "njkb": Decimal("75000000.00"),
            "owner_name": "Rizky Maulana",
            "owner_nik": "3201010101010005",
            "vehicle_nfc_id": "VEH-NFC-1005-RZM",
        },
        {
            "plate_number": "B 1006 NDK",
            "registration_number": "REG-1006-NDK",
            "brand": "Honda",
            "vehicle_type": "Beat",
            "jenis": VehicleClass.MOTORCYCLE,
            "manufacture_year": 2022,
            "color": "Pink",
            "engine_capacity_cc": 110,
            "pkb": Decimal("320000.00"),
            "njkb": Decimal("16500000.00"),
            "owner_name": "Nadia Khairunnisa",
            "owner_nik": "3201010101010006",
            "vehicle_nfc_id": "VEH-NFC-1006-NDK",
        },
        {
            "plate_number": "B 1007 FJN",
            "registration_number": "REG-1007-FJN",
            "brand": "Isuzu",
            "vehicle_type": "Elf",
            "jenis": VehicleClass.TRUCK,
            "manufacture_year": 2019,
            "color": "Putih",
            "engine_capacity_cc": 2771,
            "pkb": Decimal("2800000.00"),
            "njkb": Decimal("160000000.00"),
            "owner_name": "Fajar Nugroho",
            "owner_nik": "3201010101010007",
            "vehicle_nfc_id": "VEH-NFC-1007-FJN",
        },
        {
            "plate_number": "B 1008 PTA",
            "registration_number": "REG-1008-PTA",
            "brand": "Honda",
            "vehicle_type": "Brio",
            "jenis": VehicleClass.CAR,
            "manufacture_year": 2021,
            "color": "Kuning",
            "engine_capacity_cc": 1199,
            "pkb": Decimal("2100000.00"),
            "njkb": Decimal("130000000.00"),
            "owner_name": "Putri Ayuningtyas",
            "owner_nik": "3201010101010008",
            "vehicle_nfc_id": "VEH-NFC-1008-PTA",
        },
        {
            "plate_number": "B 1009 YSF",
            "registration_number": "REG-1009-YSF",
            "brand": "Mitsubishi",
            "vehicle_type": "Pajero Sport",
            "jenis": VehicleClass.CAR,
            "manufacture_year": 2022,
            "color": "Abu-abu",
            "engine_capacity_cc": 2442,
            "pkb": Decimal("8500000.00"),
            "njkb": Decimal("480000000.00"),
            "owner_name": "Yusuf Hidayat",
            "owner_nik": "3201010101010009",
            "vehicle_nfc_id": "VEH-NFC-1009-YSF",
        },
        {
            "plate_number": "B 1010 ITN",
            "registration_number": "REG-1010-ITN",
            "brand": "Wuling",
            "vehicle_type": "Air EV",
            "jenis": VehicleClass.CAR,
            "manufacture_year": 2023,
            "color": "Hijau Muda",
            "engine_capacity_cc": 0,
            "pkb": Decimal("800000.00"),
            "njkb": Decimal("190000000.00"),
            "owner_name": "Intan Permatasari",
            "owner_nik": "3201010101010010",
            "vehicle_nfc_id": "VEH-NFC-1010-ITN",
        },
        # Corporate Fleet: PT Pertamina Retail
        {
            "plate_number": "B 9101 PRR",
            "registration_number": "REG-9101-PRR",
            "brand": "Hino",
            "vehicle_type": "Dutro",
            "jenis": VehicleClass.TRUCK,
            "manufacture_year": 2021,
            "color": "Kuning",
            "engine_capacity_cc": 4009,
            "pkb": Decimal("3500000.00"),
            "njkb": Decimal("320000000.00"),
            "owner_name": "PT Pertamina Retail",
            "owner_nik": None,
            "vehicle_nfc_id": "VEH-NFC-9101-PRR",
        },
        {
            "plate_number": "B 9102 PRR",
            "registration_number": "REG-9102-PRR",
            "brand": "Mitsubishi",
            "vehicle_type": "Fuso",
            "jenis": VehicleClass.TRUCK,
            "manufacture_year": 2020,
            "color": "Merah",
            "engine_capacity_cc": 7545,
            "pkb": Decimal("6200000.00"),
            "njkb": Decimal("580000000.00"),
            "owner_name": "PT Pertamina Retail",
            "owner_nik": None,
            "vehicle_nfc_id": "VEH-NFC-9102-PRR",
        },
        {
            "plate_number": "B 9103 PRR",
            "registration_number": "REG-9103-PRR",
            "brand": "Toyota",
            "vehicle_type": "Dyna",
            "jenis": VehicleClass.TRUCK,
            "manufacture_year": 2019,
            "color": "Putih",
            "engine_capacity_cc": 4009,
            "pkb": Decimal("3200000.00"),
            "njkb": Decimal("290000000.00"),
            "owner_name": "PT Pertamina Retail",
            "owner_nik": None,
            "vehicle_nfc_id": "VEH-NFC-9103-PRR",
        },
        {
            "plate_number": "B 9104 PRR",
            "registration_number": "REG-9104-PRR",
            "brand": "Isuzu",
            "vehicle_type": "Elf",
            "jenis": VehicleClass.TRUCK,
            "manufacture_year": 2022,
            "color": "Biru",
            "engine_capacity_cc": 2771,
            "pkb": Decimal("2800000.00"),
            "njkb": Decimal("260000000.00"),
            "owner_name": "PT Pertamina Retail",
            "owner_nik": None,
            "vehicle_nfc_id": "VEH-NFC-9104-PRR",
        },
        {
            "plate_number": "B 9105 PRR",
            "registration_number": "REG-9105-PRR",
            "brand": "Toyota",
            "vehicle_type": "Hilux",
            "jenis": VehicleClass.CAR,
            "manufacture_year": 2021,
            "color": "Hitam",
            "engine_capacity_cc": 2393,
            "pkb": Decimal("4200000.00"),
            "njkb": Decimal("380000000.00"),
            "owner_name": "PT Pertamina Retail",
            "owner_nik": None,
            "vehicle_nfc_id": "VEH-NFC-9105-PRR",
        },
        {
            "plate_number": "B 9106 PRR",
            "registration_number": "REG-9106-PRR",
            "brand": "Daihatsu",
            "vehicle_type": "Gran Max",
            "jenis": VehicleClass.CAR,
            "manufacture_year": 2022,
            "color": "Silver",
            "engine_capacity_cc": 1495,
            "pkb": Decimal("1800000.00"),
            "njkb": Decimal("130000000.00"),
            "owner_name": "PT Pertamina Retail",
            "owner_nik": None,
            "vehicle_nfc_id": "VEH-NFC-9106-PRR",
        },
        {
            "plate_number": "B 9107 PRR",
            "registration_number": "REG-9107-PRR",
            "brand": "Mitsubishi",
            "vehicle_type": "L300",
            "jenis": VehicleClass.TRUCK,
            "manufacture_year": 2018,
            "color": "Cokelat",
            "engine_capacity_cc": 2477,
            "pkb": Decimal("1500000.00"),
            "njkb": Decimal("110000000.00"),
            "owner_name": "PT Pertamina Retail",
            "owner_nik": None,
            "vehicle_nfc_id": "VEH-NFC-9107-PRR",
        },
        {
            "plate_number": "B 9108 PRR",
            "registration_number": "REG-9108-PRR",
            "brand": "Suzuki",
            "vehicle_type": "Carry",
            "jenis": VehicleClass.CAR,
            "manufacture_year": 2020,
            "color": "Hitam",
            "engine_capacity_cc": 1462,
            "pkb": Decimal("1400000.00"),
            "njkb": Decimal("90000000.00"),
            "owner_name": "PT Pertamina Retail",
            "owner_nik": None,
            "vehicle_nfc_id": "VEH-NFC-9108-PRR",
        },
        # Corporate Fleet: PT Logistik Nusantara
        {
            "plate_number": "L 8011 LN",
            "registration_number": "REG-8011-LN",
            "brand": "Hino",
            "vehicle_type": "Ranger",
            "jenis": VehicleClass.TRUCK,
            "manufacture_year": 2022,
            "color": "Hijau",
            "engine_capacity_cc": 7684,
            "pkb": Decimal("7500000.00"),
            "njkb": Decimal("680000000.00"),
            "owner_name": "PT Logistik Nusantara",
            "owner_nik": None,
            "vehicle_nfc_id": "VEH-NFC-8011-LN",
        },
        {
            "plate_number": "L 8012 LN",
            "registration_number": "REG-8012-LN",
            "brand": "Mitsubishi",
            "vehicle_type": "Coltdiesel",
            "jenis": VehicleClass.TRUCK,
            "manufacture_year": 2021,
            "color": "Kuning",
            "engine_capacity_cc": 3908,
            "pkb": Decimal("3200000.00"),
            "njkb": Decimal("290000000.00"),
            "owner_name": "PT Logistik Nusantara",
            "owner_nik": None,
            "vehicle_nfc_id": "VEH-NFC-8012-LN",
        },
        {
            "plate_number": "L 8013 LN",
            "registration_number": "REG-8013-LN",
            "brand": "Isuzu",
            "vehicle_type": "Giga",
            "jenis": VehicleClass.TRUCK,
            "manufacture_year": 2020,
            "color": "Putih",
            "engine_capacity_cc": 7790,
            "pkb": Decimal("6800000.00"),
            "njkb": Decimal("620000000.00"),
            "owner_name": "PT Logistik Nusantara",
            "owner_nik": None,
            "vehicle_nfc_id": "VEH-NFC-8013-LN",
        },
        {
            "plate_number": "L 8014 LN",
            "registration_number": "REG-8014-LN",
            "brand": "Suzuki",
            "vehicle_type": "Carry Pick Up",
            "jenis": VehicleClass.TRUCK,
            "manufacture_year": 2021,
            "color": "Hitam",
            "engine_capacity_cc": 1462,
            "pkb": Decimal("1400000.00"),
            "njkb": Decimal("95000000.00"),
            "owner_name": "PT Logistik Nusantara",
            "owner_nik": None,
            "vehicle_nfc_id": "VEH-NFC-8014-LN",
        },
        {
            "plate_number": "L 8015 LN",
            "registration_number": "REG-8015-LN",
            "brand": "Toyota",
            "vehicle_type": "Gran Max",
            "jenis": VehicleClass.CAR,
            "manufacture_year": 2023,
            "color": "Silver",
            "engine_capacity_cc": 1495,
            "pkb": Decimal("1900000.00"),
            "njkb": Decimal("140000000.00"),
            "owner_name": "PT Logistik Nusantara",
            "owner_nik": None,
            "vehicle_nfc_id": "VEH-NFC-8015-LN",
        },
        {
            "plate_number": "L 8016 LN",
            "registration_number": "REG-8016-LN",
            "brand": "Mitsubishi",
            "vehicle_type": "Fuso",
            "jenis": VehicleClass.TRUCK,
            "manufacture_year": 2019,
            "color": "Orange",
            "engine_capacity_cc": 7545,
            "pkb": Decimal("5900000.00"),
            "njkb": Decimal("550000000.00"),
            "owner_name": "PT Logistik Nusantara",
            "owner_nik": None,
            "vehicle_nfc_id": "VEH-NFC-8016-LN",
        },
        {
            "plate_number": "L 8017 LN",
            "registration_number": "REG-8017-LN",
            "brand": "Hino",
            "vehicle_type": "Dutro",
            "jenis": VehicleClass.TRUCK,
            "manufacture_year": 2021,
            "color": "Hijau",
            "engine_capacity_cc": 4009,
            "pkb": Decimal("3400000.00"),
            "njkb": Decimal("310000000.00"),
            "owner_name": "PT Logistik Nusantara",
            "owner_nik": None,
            "vehicle_nfc_id": "VEH-NFC-8017-LN",
        },
        {
            "plate_number": "L 8018 LN",
            "registration_number": "REG-8018-LN",
            "brand": "Daihatsu",
            "vehicle_type": "Gran Max Van",
            "jenis": VehicleClass.CAR,
            "manufacture_year": 2020,
            "color": "Putih",
            "engine_capacity_cc": 1298,
            "pkb": Decimal("1700000.00"),
            "njkb": Decimal("120000000.00"),
            "owner_name": "PT Logistik Nusantara",
            "owner_nik": None,
            "vehicle_nfc_id": "VEH-NFC-8018-LN",
        },
        # Corporate Fleet: CV Angkutan Maju Bersama
        {
            "plate_number": "D 7011 AM",
            "registration_number": "REG-7011-AM",
            "brand": "Mitsubishi",
            "vehicle_type": "Fuso",
            "jenis": VehicleClass.TRUCK,
            "manufacture_year": 2021,
            "color": "Merah",
            "engine_capacity_cc": 7545,
            "pkb": Decimal("6300000.00"),
            "njkb": Decimal("590000000.00"),
            "owner_name": "CV Angkutan Maju Bersama",
            "owner_nik": None,
            "vehicle_nfc_id": "VEH-NFC-7011-AM",
        },
        {
            "plate_number": "D 7012 AM",
            "registration_number": "REG-7012-AM",
            "brand": "Hino",
            "vehicle_type": "Dutro",
            "jenis": VehicleClass.TRUCK,
            "manufacture_year": 2020,
            "color": "Hijau",
            "engine_capacity_cc": 4009,
            "pkb": Decimal("3300000.00"),
            "njkb": Decimal("300000000.00"),
            "owner_name": "CV Angkutan Maju Bersama",
            "owner_nik": None,
            "vehicle_nfc_id": "VEH-NFC-7012-AM",
        },
        {
            "plate_number": "D 7013 AM",
            "registration_number": "REG-7013-AM",
            "brand": "Isuzu",
            "vehicle_type": "Elf",
            "jenis": VehicleClass.TRUCK,
            "manufacture_year": 2022,
            "color": "Biru",
            "engine_capacity_cc": 2771,
            "pkb": Decimal("2900000.00"),
            "njkb": Decimal("270000000.00"),
            "owner_name": "CV Angkutan Maju Bersama",
            "owner_nik": None,
            "vehicle_nfc_id": "VEH-NFC-7013-AM",
        },
        {
            "plate_number": "D 7014 AM",
            "registration_number": "REG-7014-AM",
            "brand": "Daihatsu",
            "vehicle_type": "Gran Max",
            "jenis": VehicleClass.CAR,
            "manufacture_year": 2021,
            "color": "Putih",
            "engine_capacity_cc": 1495,
            "pkb": Decimal("1800000.00"),
            "njkb": Decimal("125000000.00"),
            "owner_name": "CV Angkutan Maju Bersama",
            "owner_nik": None,
            "vehicle_nfc_id": "VEH-NFC-7014-AM",
        },
        {
            "plate_number": "D 7015 AM",
            "registration_number": "REG-7015-AM",
            "brand": "Suzuki",
            "vehicle_type": "Carry",
            "jenis": VehicleClass.CAR,
            "manufacture_year": 2019,
            "color": "Hitam",
            "engine_capacity_cc": 1462,
            "pkb": Decimal("1300000.00"),
            "njkb": Decimal("85000000.00"),
            "owner_name": "CV Angkutan Maju Bersama",
            "owner_nik": None,
            "vehicle_nfc_id": "VEH-NFC-7015-AM",
        },
        {
            "plate_number": "D 7016 AM",
            "registration_number": "REG-7016-AM",
            "brand": "Hino",
            "vehicle_type": "Ranger",
            "jenis": VehicleClass.TRUCK,
            "manufacture_year": 2018,
            "color": "Hijau",
            "engine_capacity_cc": 7684,
            "pkb": Decimal("7200000.00"),
            "njkb": Decimal("650000000.00"),
            "owner_name": "CV Angkutan Maju Bersama",
            "owner_nik": None,
            "vehicle_nfc_id": "VEH-NFC-7016-AM",
        },
        {
            "plate_number": "D 7017 AM",
            "registration_number": "REG-7017-AM",
            "brand": "Mitsubishi",
            "vehicle_type": "L300",
            "jenis": VehicleClass.TRUCK,
            "manufacture_year": 2020,
            "color": "Abu-abu",
            "engine_capacity_cc": 2477,
            "pkb": Decimal("1600000.00"),
            "njkb": Decimal("115000000.00"),
            "owner_name": "CV Angkutan Maju Bersama",
            "owner_nik": None,
            "vehicle_nfc_id": "VEH-NFC-7017-AM",
        },
        {
            "plate_number": "D 7018 AM",
            "registration_number": "REG-7018-AM",
            "brand": "Toyota",
            "vehicle_type": "Hilux",
            "jenis": VehicleClass.CAR,
            "manufacture_year": 2022,
            "color": "Silver",
            "engine_capacity_cc": 2393,
            "pkb": Decimal("4400000.00"),
            "njkb": Decimal("395000000.00"),
            "owner_name": "CV Angkutan Maju Bersama",
            "owner_nik": None,
            "vehicle_nfc_id": "VEH-NFC-7018-AM",
        },
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
                jenis=item.get("jenis"),
                vehicle_nfc_id=item.get("vehicle_nfc_id"),
            )
            session.add(vehicle)
            summary["vehicles"] += 1
            await session.flush()
