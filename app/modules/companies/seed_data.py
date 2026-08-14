"""
Seeder for Company Admin users.

Creates demo companies and a COMPANY_ADMIN user for each company.
This seeder is idempotent — safe to run multiple times.

Default credentials:
  - password : subsidia123
  - role     : COMPANY_ADMIN

Companies seeded:
  1. PT Pertamina Retail          → fleet.admin@subsidia.id       (existing, reused)
  2. PT Logistik Nusantara        → admin@logistiknusantara.id
  3. CV Angkutan Maju Bersama     → admin@angkutanmaju.id
  4. PT Transportasi Prima        → admin@transprimaind.id
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.modules.companies.models import Company
from app.modules.users.models import User, UserRole
from app.core.security import get_password_hash
from app.modules.registries.models import VehicleRegistryMockup, VehicleClass
from app.modules.vehicles.models import VehicleOwnership, VehicleOwnerType, VehicleOwnershipStatus, VehicleQuotaMode, VehicleUsageType


# ──────────────────────────────────────────────────────────────────────────────
# Seed data definitions
# ──────────────────────────────────────────────────────────────────────────────

COMPANY_ADMIN_DATA = [
    {
        # This company already exists from seed_users; we just ensure it has an admin.
        "company": {
            "name": "PT Pertamina Retail",
            "nib": "1234567890001",
            "email": "info@pertaminaretail.co.id",
            "phone": "02150990000",
            "fleet_size": 25,
            "siup_no": "SIUP/001/2020",
            "npwp_no": "01.234.567.8-001.000",
            "status": "Approved",
        },
        "admin": {
            "name": "Fleet Admin",
            "email": "fleet.admin@sidia.id",
            "employee_id": "EMP-AC-001",
        },
    },
    {
        "company": {
            "name": "PT Logistik Nusantara",
            "nib": "1234567890002",
            "email": "info@logistiknusantara.id",
            "phone": "02198765432",
            "fleet_size": 40,
            "siup_no": "SIUP/002/2021",
            "npwp_no": "02.345.678.9-002.000",
            "status": "Approved",
        },
        "admin": {
            "name": "Admin Logistik Nusantara",
            "email": "admin@logistiknusantara.id",
            "employee_id": "EMP-AC-002",
        },
    },
    {
        "company": {
            "name": "CV Angkutan Maju Bersama",
            "nib": "1234567890003",
            "email": "admin@angkutanmaju.id",
            "phone": "02177889900",
            "fleet_size": 15,
            "siup_no": "SIUP/003/2022",
            "npwp_no": "03.456.789.0-003.000",
            "status": "Approved",
        },
        "admin": {
            "name": "Admin Angkutan Maju",
            "email": "admin@angkutanmaju.id",
            "employee_id": "EMP-AC-003",
        },
    },
    {
        "company": {
            "name": "PT Transportasi Prima",
            "nib": "1234567890004",
            "email": "admin@transprimaind.id",
            "phone": "02144556677",
            "fleet_size": 30,
            "siup_no": "SIUP/004/2023",
            "npwp_no": "04.567.890.1-004.000",
            "status": "Belum Verifikasi",
        },
        "admin": {
            "name": "Admin Transportasi Prima",
            "email": "admin@transprimaind.id",
            "employee_id": "EMP-AC-004",
        },
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# Seeder function
# ──────────────────────────────────────────────────────────────────────────────

async def seed_company_admins(session: AsyncSession) -> dict[str, int]:
    """
    Idempotently seed demo companies and their COMPANY_ADMIN users.

    Returns a summary dict:
        {
            "companies_created": int,
            "companies_existing": int,
            "admins_created": int,
            "admins_existing": int,
        }
    """
    summary = {
        "companies_created": 0,
        "companies_existing": 0,
        "admins_created": 0,
        "admins_existing": 0,
    }

    default_password_hash = get_password_hash("subsidia123")

    for entry in COMPANY_ADMIN_DATA:
        company_data = entry["company"]
        admin_data = entry["admin"]

        # ── 1. Upsert Company ────────────────────────────────────────────────
        result = await session.execute(
            select(Company).filter(Company.name == company_data["name"])
        )
        company = result.scalars().first()

        if company is None:
            company = Company(
                name=company_data["name"],
                nib=company_data.get("nib"),
                email=company_data.get("email"),
                phone=company_data.get("phone"),
                fleet_size=company_data.get("fleet_size"),
                siup_no=company_data.get("siup_no"),
                npwp_no=company_data.get("npwp_no"),
                status=company_data.get("status", "Belum Verifikasi"),
            )
            session.add(company)
            await session.flush()  # populate company.id
            summary["companies_created"] += 1
        else:
            # Patch fields that may be missing/stale
            if company.nib is None and company_data.get("nib"):
                company.nib = company_data["nib"]
            if company.email is None and company_data.get("email"):
                company.email = company_data["email"]
            if company.phone is None and company_data.get("phone"):
                company.phone = company_data["phone"]
            if company.fleet_size is None and company_data.get("fleet_size"):
                company.fleet_size = company_data["fleet_size"]
            if company.status == "Belum Verifikasi" and company_data.get("status") == "Approved":
                company.status = "Approved"
            summary["companies_existing"] += 1

        # ── 2. Upsert COMPANY_ADMIN user ─────────────────────────────────────
        result = await session.execute(
            select(User).filter(User.email == admin_data["email"])
        )
        existing_user = result.scalars().first()

        if existing_user is None:
            user = User(
                name=admin_data["name"],
                email=admin_data["email"],
                password=default_password_hash,
                role=[UserRole.COMPANY_ADMIN],
                company_id=company.id,
                employee_id=admin_data["employee_id"],
                is_active=True,
            )
            session.add(user)
            summary["admins_created"] += 1
        else:
            # Repair: ensure role, company link, and active state are correct
            if UserRole.COMPANY_ADMIN not in existing_user.role:
                existing_user.role = [*existing_user.role, UserRole.COMPANY_ADMIN]
            if existing_user.company_id is None:
                existing_user.company_id = company.id
            if not existing_user.is_active:
                existing_user.is_active = True
            summary["admins_existing"] += 1

        # ── 3. Seed Corporate Vehicles for this Company ──────────────────────
        result_veh = await session.execute(
            select(VehicleRegistryMockup).filter(VehicleRegistryMockup.owner_name == company.name)
        )
        registry_vehicles = result_veh.scalars().all()
        for reg_veh in registry_vehicles:
            result_own = await session.execute(
                select(VehicleOwnership).filter(
                    VehicleOwnership.owner_type == VehicleOwnerType.COMPANY,
                    VehicleOwnership.owner_id == company.id,
                    VehicleOwnership.vehicle_id == reg_veh.id
                )
            )
            ownership = result_own.scalars().first()

            # Determine usage type based on registry vehicle class
            if reg_veh.jenis == VehicleClass.TRUCK:
                usage_type = VehicleUsageType.COMMERCIAL_TRUCK
            elif reg_veh.jenis == VehicleClass.CAR:
                usage_type = VehicleUsageType.COMMERCIAL_CAR
            elif reg_veh.jenis == VehicleClass.MOTORCYCLE:
                usage_type = VehicleUsageType.COMMERCIAL_MOTORCYCLE
            else:
                usage_type = VehicleUsageType.COMMERCIAL_TRUCK

            if ownership is None:
                ownership = VehicleOwnership(
                    owner_type=VehicleOwnerType.COMPANY,
                    owner_id=company.id,
                    vehicle_id=reg_veh.id,
                    ownership_status=VehicleOwnershipStatus.COMPANY,
                    usage_type=usage_type,
                    quota_mode=VehicleQuotaMode.DEDICATED_VEHICLE_QUOTA,
                    plate_number_snapshot=reg_veh.plate_number,
                    ktp_nfc_id_snapshot=f"COMPANY-{str(company.id)[:8]}",
                    vehicle_nfc_id=reg_veh.vehicle_nfc_id,
                )
                session.add(ownership)
            else:
                ownership.plate_number_snapshot = reg_veh.plate_number
                ownership.vehicle_nfc_id = reg_veh.vehicle_nfc_id
                ownership.usage_type = usage_type
                ownership.ktp_nfc_id_snapshot = f"COMPANY-{str(company.id)[:8]}"

    await session.commit()
    return summary
