import hashlib
from datetime import datetime
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.modules.users.models import User, UserRole, BuyerProfile, VerificationStatus
from app.modules.companies.models import Company
from app.modules.gas_stations.models import GasStation
from app.core.security import get_password_hash
from app.modules.registries.models import CitizenRegistryMockup, VehicleRegistryMockup
from app.modules.vehicles.models import (
    VehicleOwnership,
    VehicleOwnerType,
    VehicleOwnershipStatus,
    VehicleUsageType,
    VehicleQuotaMode,
)
from app.modules.buyer_registrations.models import (
    BuyerRegistrationAttempt,
    BuyerRegistrationStatus,
    BuyerRegistrationDocument,
    BuyerProfileDocument,
    BuyerDocumentType
)
from app.modules.wallets.models import Wallet, OwnerType


BUYERS_TO_SEED = [
    {
        "nik": "3201010101010001",
        "email": "buyer@mysuf.com",
        "name": "Ahmad Sulaiman",
    },
    {
        "nik": "3511111411040003",
        "email": "ekya@mysuf.com",
        "name": "EKYA MUHAMMAD HASFI FADLILURRAHMAN",
    },
    {
        "nik": "3201010101010002",
        "email": "siti@mysuf.com",
        "name": "Siti Rahmawati",
    },
]

async def seed_users(session: AsyncSession) -> dict[str, int]:
    summary = {"created": 0, "existing": 0}

    # 1. Ensure a default Company exists for ADMIN_COMPANY (AC)
    company_name = "PT Pertamina Retail"
    result = await session.execute(
        select(Company).filter(Company.name == company_name)
    )
    company = result.scalars().first()
    if company is None:
        company = Company(name=company_name)
        session.add(company)
        await session.flush()  # to get company.id

    # 2. Ensure a default GasStation exists for ADMIN_GAS_STATION (AGS) and SALES_OFFICER (SO)
    station_name = "SPBU Pertamina 31.12345 (Default Station)"
    result = await session.execute(
        select(GasStation).filter(GasStation.name == station_name)
    )
    gas_station = result.scalars().first()
    if gas_station is None:
        gas_station = GasStation(
            name=station_name,
            longitude=106.8166,
            latitude=-6.2000
        )
        session.add(gas_station)
        await session.flush()  # to get gas_station.id

    # 3. Define users to seed with abbreviations
    # - SA: Super Admin
    # - AC: Admin Company
    # - AGS: Admin Gas Station
    # - SO: Sales Officer
    default_password_hash = get_password_hash("mysuf123")
    
    users_data = [
        {
            "name": "Super Admin",
            "email": "super.admin@mysuf.id",
            "password": default_password_hash,
            "role": [UserRole.SUPER_ADMIN],
            "company_id": None,
            "gas_station_id": None,
            "employee_id": "EMP-SA-001",
            "shift": None
        },
        {
            "name": "SPBU Admin",
            "email": "spbu.admin@mysuf.id",
            "password": default_password_hash,
            "role": [UserRole.SPBU_ADMIN],
            "company_id": None,
            "gas_station_id": gas_station.id,
            "employee_id": "EMP-SPBU-001",
            "shift": "Morning (06:00 - 14:00)"
        },
        {
            "name": "Fleet Admin",
            "email": "fleet.admin@mysuf.id",
            "password": default_password_hash,
            "role": [UserRole.COMPANY_ADMIN],
            "company_id": company.id,
            "gas_station_id": None,
            "employee_id": "EMP-AC-001",
            "shift": None
        },
        {
            "name": "Government Admin",
            "email": "gov.admin@mysuf.id",
            "password": default_password_hash,
            "role": [UserRole.GOV_ADMIN],
            "company_id": None,
            "gas_station_id": None,
            "employee_id": "EMP-GOV-001",
            "shift": None
        },
        {
            "name": "Sales Officer",
            "email": "so@mysuf.id",
            "password": default_password_hash,
            "role": [UserRole.SALES_OFFICER],
            "company_id": None,
            "gas_station_id": gas_station.id,
            "employee_id": "EMP-SO-001",
            "shift": "Afternoon (14:00 - 22:00)"
        }
    ]

    for data in users_data:
        # Check if user already exists by email
        result = await session.execute(
            select(User).filter(User.email == data["email"])
        )
        existing_user = result.scalars().first()

        if existing_user is None:
            user = User(
                name=data["name"],
                email=data["email"],
                password=data["password"],
                role=data["role"],
                company_id=data["company_id"],
                gas_station_id=data["gas_station_id"],
                employee_id=data["employee_id"],
                shift=data.get("shift"),
                is_active=True
            )
            session.add(user)
            summary["created"] += 1
        else:
            # If user already exists, update their shift as well if needed
            existing_user.shift = data.get("shift")
            summary["existing"] += 1

    await session.commit()
    return summary

async def seed_buyer_user(session: AsyncSession) -> dict[str, int]:
    summary = {"created": 0, "existing": 0, "repaired": 0, "skipped": 0}

    for buyer_info in BUYERS_TO_SEED:
        nik = buyer_info["nik"]
        email = buyer_info["email"]
        created_current_buyer = False
        repaired_current_buyer = False
        seeded_at = datetime.utcnow()
        password_hash = get_password_hash("Password123")

        # 1. Verify that citizen target registry exists
        result = await session.execute(
            select(CitizenRegistryMockup).filter(CitizenRegistryMockup.nik == nik)
        )
        citizen = result.scalars().first()
        if citizen is None:
            summary["skipped"] += 1
            continue

        # 2. Create or update the User (BUYER role)
        result = await session.execute(
            select(User).filter(User.email == email)
        )
        user = result.scalars().first()
        if user is None:
            user = User(
                name=citizen.nama,
                email=email,
                password=password_hash,
                role=[UserRole.BUYER],
                is_active=True
            )
            session.add(user)
            await session.flush()
            created_current_buyer = True
        else:
            if user.name != citizen.nama:
                user.name = citizen.nama
                repaired_current_buyer = True
            if user.password != password_hash:
                user.password = password_hash
                repaired_current_buyer = True
            if UserRole.BUYER not in user.role:
                user.role = [*user.role, UserRole.BUYER]
                repaired_current_buyer = True
            if not user.is_active:
                user.is_active = True
                repaired_current_buyer = True

        # 3. Create or update the corresponding BuyerProfile
        result = await session.execute(
            select(BuyerProfile).filter(BuyerProfile.user_id == user.id)
        )
        buyer_profile = result.scalars().first()
        if buyer_profile is None:
            buyer_profile = BuyerProfile(
                nik_snapshot=citizen.nik,
                ktp_nfc_id_snapshot=citizen.ktp_nfc_id,
                kk_id=citizen.kk_id,
                user_id=user.id,
                verification_status=VerificationStatus.VERIFIED,
                is_pin_active=False
            )
            session.add(buyer_profile)
            await session.flush()
            created_current_buyer = True
        else:
            if buyer_profile.nik_snapshot != citizen.nik:
                buyer_profile.nik_snapshot = citizen.nik
                repaired_current_buyer = True
            if buyer_profile.ktp_nfc_id_snapshot != citizen.ktp_nfc_id:
                buyer_profile.ktp_nfc_id_snapshot = citizen.ktp_nfc_id
                repaired_current_buyer = True
            if buyer_profile.kk_id != citizen.kk_id:
                buyer_profile.kk_id = citizen.kk_id
                repaired_current_buyer = True
            if buyer_profile.verification_status != VerificationStatus.VERIFIED:
                buyer_profile.verification_status = VerificationStatus.VERIFIED
                repaired_current_buyer = True

        # 4. Create or update a Completed BuyerRegistrationAttempt record
        result = await session.execute(
            select(BuyerRegistrationAttempt)
            .filter(
                BuyerRegistrationAttempt.created_user_id == user.id,
                BuyerRegistrationAttempt.registry_citizen_id == citizen.id,
            )
            .order_by(BuyerRegistrationAttempt.created_at.desc(), BuyerRegistrationAttempt.id.desc())
        )
        attempt = result.scalars().first()
        if attempt is None:
            attempt = BuyerRegistrationAttempt(
                nik_input=citizen.nik,
                email=email,
                password_hash=password_hash,
                status=BuyerRegistrationStatus.COMPLETED,
                nik_ocr=citizen.nik,
                is_nik_match=True,
                registry_citizen_id=citizen.id,
                registry_name_snapshot=citizen.nama,
                registry_kk_id_snapshot=citizen.kk_id,
                registry_ktp_nfc_id_snapshot=citizen.ktp_nfc_id,
                face_match_score=0.98,
                is_face_match=True,
                ocr_raw_text=f"NIK {citizen.nik}\nNAMA {citizen.nama}",
                created_user_id=user.id,
                created_buyer_profile_id=buyer_profile.id,
                verification_started_at=seeded_at,
                verified_at=seeded_at,
                completed_at=seeded_at,
            )
            session.add(attempt)
            await session.flush()
            created_current_buyer = True
        else:
            attempt.nik_input = citizen.nik
            attempt.email = email
            attempt.password_hash = user.password
            attempt.status = BuyerRegistrationStatus.COMPLETED
            attempt.nik_ocr = citizen.nik
            attempt.is_nik_match = True
            attempt.registry_citizen_id = citizen.id
            attempt.registry_name_snapshot = citizen.nama
            attempt.registry_kk_id_snapshot = citizen.kk_id
            attempt.registry_ktp_nfc_id_snapshot = citizen.ktp_nfc_id
            attempt.face_match_score = 0.98
            attempt.is_face_match = True
            attempt.ocr_raw_text = f"NIK {citizen.nik}\nNAMA {citizen.nama}"
            attempt.created_user_id = user.id
            attempt.created_buyer_profile_id = buyer_profile.id
            attempt.verification_started_at = attempt.verification_started_at or seeded_at
            attempt.verified_at = attempt.verified_at or seeded_at
            attempt.completed_at = attempt.completed_at or seeded_at
            attempt.failure_reason = None
            attempt.failure_detail = None
            repaired_current_buyer = True

        # 5. Copy default_files.png into the appropriate physical storage location like the real API
        project_root = Path(__file__).resolve().parents[3]
        default_png_path = project_root / "utils" / "default_files.png"
        storage_dir = project_root / "storage" / "buyer-registrations" / str(attempt.id)
        
        if default_png_path.exists():
            file_bytes = default_png_path.read_bytes()
        else:
            # Fallback minimal PNG bytes if source image does not exist
            file_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"

        storage_dir.mkdir(parents=True, exist_ok=True)
        
        ktp_filename = "ktp-photo.png"
        selfie_filename = "selfie-photo.png"
        
        ktp_path = storage_dir / ktp_filename
        selfie_path = storage_dir / selfie_filename
        if not ktp_path.exists():
            ktp_path.write_bytes(file_bytes)
            repaired_current_buyer = True
        if not selfie_path.exists():
            selfie_path.write_bytes(file_bytes)
            repaired_current_buyer = True
        
        checksum = hashlib.sha256(file_bytes).hexdigest()
        file_size = len(file_bytes)

        # 6. Create or update BuyerRegistrationDocuments
        result = await session.execute(
            select(BuyerRegistrationDocument).filter(
                BuyerRegistrationDocument.registration_attempt_id == attempt.id
            )
        )
        registration_documents = {
            document.document_type: document for document in result.scalars().all()
        }

        reg_ktp_doc = registration_documents.get(BuyerDocumentType.KTP_PHOTO)
        if reg_ktp_doc is None:
            reg_ktp_doc = BuyerRegistrationDocument(
                registration_attempt_id=attempt.id,
                document_type=BuyerDocumentType.KTP_PHOTO,
                storage_key=f"{attempt.id}/{ktp_filename}",
                original_filename="default_files.png",
                mime_type="image/png",
                file_size_bytes=file_size,
                checksum_sha256=checksum,
            )
            session.add(reg_ktp_doc)
            created_current_buyer = True
        else:
            reg_ktp_doc.storage_key = f"{attempt.id}/{ktp_filename}"
            reg_ktp_doc.original_filename = "default_files.png"
            reg_ktp_doc.mime_type = "image/png"
            reg_ktp_doc.file_size_bytes = file_size
            reg_ktp_doc.checksum_sha256 = checksum

        reg_selfie_doc = registration_documents.get(BuyerDocumentType.SELFIE_PHOTO)
        if reg_selfie_doc is None:
            reg_selfie_doc = BuyerRegistrationDocument(
                registration_attempt_id=attempt.id,
                document_type=BuyerDocumentType.SELFIE_PHOTO,
                storage_key=f"{attempt.id}/{selfie_filename}",
                original_filename="default_files.png",
                mime_type="image/png",
                file_size_bytes=file_size,
                checksum_sha256=checksum,
            )
            session.add(reg_selfie_doc)
            created_current_buyer = True
        else:
            reg_selfie_doc.storage_key = f"{attempt.id}/{selfie_filename}"
            reg_selfie_doc.original_filename = "default_files.png"
            reg_selfie_doc.mime_type = "image/png"
            reg_selfie_doc.file_size_bytes = file_size
            reg_selfie_doc.checksum_sha256 = checksum

        await session.flush()

        # 7. Create or update BuyerProfileDocuments pointing to registration source
        result = await session.execute(
            select(BuyerProfileDocument).filter(
                BuyerProfileDocument.buyer_profile_id == buyer_profile.id
            )
        )
        profile_documents = {
            document.document_type: document for document in result.scalars().all()
        }

        prof_ktp_doc = profile_documents.get(BuyerDocumentType.KTP_PHOTO)
        if prof_ktp_doc is None:
            prof_ktp_doc = BuyerProfileDocument(
                buyer_profile_id=buyer_profile.id,
                document_type=BuyerDocumentType.KTP_PHOTO,
                storage_key=f"{attempt.id}/{ktp_filename}",
                original_filename="default_files.png",
                mime_type="image/png",
                file_size_bytes=file_size,
                checksum_sha256=checksum,
                source_registration_document_id=reg_ktp_doc.id,
            )
            session.add(prof_ktp_doc)
            created_current_buyer = True
        else:
            prof_ktp_doc.storage_key = f"{attempt.id}/{ktp_filename}"
            prof_ktp_doc.original_filename = "default_files.png"
            prof_ktp_doc.mime_type = "image/png"
            prof_ktp_doc.file_size_bytes = file_size
            prof_ktp_doc.checksum_sha256 = checksum
            prof_ktp_doc.source_registration_document_id = reg_ktp_doc.id

        prof_selfie_doc = profile_documents.get(BuyerDocumentType.SELFIE_PHOTO)
        if prof_selfie_doc is None:
            prof_selfie_doc = BuyerProfileDocument(
                buyer_profile_id=buyer_profile.id,
                document_type=BuyerDocumentType.SELFIE_PHOTO,
                storage_key=f"{attempt.id}/{selfie_filename}",
                original_filename="default_files.png",
                mime_type="image/png",
                file_size_bytes=file_size,
                checksum_sha256=checksum,
                source_registration_document_id=reg_selfie_doc.id,
            )
            session.add(prof_selfie_doc)
            created_current_buyer = True
        else:
            prof_selfie_doc.storage_key = f"{attempt.id}/{selfie_filename}"
            prof_selfie_doc.original_filename = "default_files.png"
            prof_selfie_doc.mime_type = "image/png"
            prof_selfie_doc.file_size_bytes = file_size
            prof_selfie_doc.checksum_sha256 = checksum
            prof_selfie_doc.source_registration_document_id = reg_selfie_doc.id

        # 8. Create or update Wallet for the user with an initial balance of Rp 500.000
        result = await session.execute(
            select(Wallet).filter(
                Wallet.owner_type == OwnerType.USER,
                Wallet.owner_id == user.id,
            )
        )
        wallet = result.scalars().first()
        if wallet is None:
            wallet = Wallet(
                owner_type=OwnerType.USER,
                owner_id=user.id,
                balance=500000.00,
                is_active=True
            )
            session.add(wallet)
            created_current_buyer = True
        else:
            if not wallet.is_active:
                wallet.is_active = True
                repaired_current_buyer = True

        # 9. Automatically seed VehicleOwnership for all vehicles owned by this citizen in the mock registry
        result_vehicles = await session.execute(
            select(VehicleRegistryMockup).filter(VehicleRegistryMockup.owner_nik == citizen.nik)
        )
        vehicles = result_vehicles.scalars().all()
        for vehicle in vehicles:
            result = await session.execute(
                select(VehicleOwnership).filter(
                    VehicleOwnership.owner_type == VehicleOwnerType.BUYER_PROFILE,
                    VehicleOwnership.owner_id == buyer_profile.id,
                    VehicleOwnership.vehicle_id == vehicle.id,
                )
            )
            ownership = result.scalars().first()
            if ownership is None:
                ownership = VehicleOwnership(
                    owner_type=VehicleOwnerType.BUYER_PROFILE,
                    owner_id=buyer_profile.id,
                    vehicle_id=vehicle.id,
                    ownership_status=VehicleOwnershipStatus.PERSONAL,
                    usage_type=VehicleUsageType.PERSONAL,
                    quota_mode=VehicleQuotaMode.OWNER_PERSONAL_QUOTA,
                    plate_number_snapshot=vehicle.plate_number,
                    ktp_nfc_id_snapshot=buyer_profile.ktp_nfc_id_snapshot,
                )
                session.add(ownership)
                created_current_buyer = True
            else:
                if ownership.ownership_status != VehicleOwnershipStatus.PERSONAL:
                    ownership.ownership_status = VehicleOwnershipStatus.PERSONAL
                    repaired_current_buyer = True
                if ownership.usage_type != VehicleUsageType.PERSONAL:
                    ownership.usage_type = VehicleUsageType.PERSONAL
                    repaired_current_buyer = True
                if ownership.quota_mode != VehicleQuotaMode.OWNER_PERSONAL_QUOTA:
                    ownership.quota_mode = VehicleQuotaMode.OWNER_PERSONAL_QUOTA
                    repaired_current_buyer = True
                if ownership.plate_number_snapshot != vehicle.plate_number:
                    ownership.plate_number_snapshot = vehicle.plate_number
                    repaired_current_buyer = True
                if ownership.ktp_nfc_id_snapshot != buyer_profile.ktp_nfc_id_snapshot:
                    ownership.ktp_nfc_id_snapshot = buyer_profile.ktp_nfc_id_snapshot
                    repaired_current_buyer = True

        if created_current_buyer:
            summary["created"] += 1
        elif repaired_current_buyer:
            summary["repaired"] += 1
        else:
            summary["existing"] += 1

    await session.commit()
    return summary
