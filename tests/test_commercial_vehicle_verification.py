import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.modules.registries.models import KK, VehicleRegistryMockup, VehicleClass
from app.modules.subsidies.models import EligibilityStatus, KKSubsidyEligibility
from app.modules.users.models import BuyerProfile, User, UserRole, VerificationStatus
from app.modules.vehicles.models import (
    VehicleOwnership,
    VehicleOwnershipDocument,
    VehicleOwnershipRequest,
    VehicleOwnershipRequestDocument,
    VehicleOwnershipRequestStatus,
    VehicleUsageType,
    VehicleOwnershipStatus,
)
from app.modules.vehicles.service import VehicleService


def _build_token(user_id: str, role: UserRole) -> str:
    return create_access_token(
        subject=user_id,
        session_id=str(uuid4()),
        client_type="PORTAL_WEB" if role != UserRole.BUYER else "BUYER_ANDROID",
        roles=[role.value],
        allowed_apps=["PORTAL_WEB"] if role != UserRole.BUYER else ["BUYER_ANDROID"],
    )


@pytest.mark.anyio
async def test_admin_approves_valid_commercial_motorcycle():
    kk = KK(code=f"KK-VERIFY-{uuid4().hex[:8]}")
    buyer = User(
        name="Buyer Test",
        email=f"buyer-{uuid4().hex[:8]}@example.com",
        password=get_password_hash("secret123"),
        role=[UserRole.BUYER],
        is_active=True,
    )
    admin = User(
        name="Admin Test",
        email=f"admin-{uuid4().hex[:8]}@example.com",
        password=get_password_hash("secret123"),
        role=[UserRole.GOV_ADMIN],
        is_active=True,
    )
    buyer_profile = BuyerProfile(
        nik_snapshot=f"3174{uuid4().hex[:12]}",
        ktp_nfc_id_snapshot=f"NFC-{uuid4().hex[:8]}",
        kk=kk,
        user=buyer,
        verification_status=VerificationStatus.VERIFIED,
    )
    registry_vehicle = VehicleRegistryMockup(
        plate_number="B 9999 MTR",
        registration_number=f"STNK-{uuid4().hex[:8]}",
        brand="Honda",
        vehicle_type="Vario",
        manufacture_year=2024,
        color="Hitam",
        engine_capacity_cc=150,
        pkb="450000.00",
        njkb="23000000.00",
        owner_name="Buyer Test",
        owner_nik=buyer_profile.nik_snapshot,
        jenis=VehicleClass.MOTORCYCLE,
    )

    request_id = None
    ownership_id = None
    storage_dir: Path | None = None
    req_storage_dir: Path | None = None

    try:
        async with AsyncSessionLocal() as session:
            session.add_all([kk, buyer, admin, buyer_profile, registry_vehicle])
            await session.commit()
            await session.refresh(buyer)
            await session.refresh(admin)
            await session.refresh(buyer_profile)
            await session.refresh(registry_vehicle)

        # Create a pending request manually
        async with AsyncSessionLocal() as session:
            request = VehicleOwnershipRequest(
                buyer_profile_id=buyer_profile.id,
                vehicle_id=registry_vehicle.id,
                ownership_status=VehicleOwnershipStatus.PERSONAL,
                usage_type=VehicleUsageType.COMMERCIAL_MOTORCYCLE,
                quota_mode="DEDICATED_VEHICLE_QUOTA",
                plate_number_snapshot=registry_vehicle.plate_number,
                ktp_nfc_id_snapshot=buyer_profile.ktp_nfc_id_snapshot,
                status=VehicleOwnershipRequestStatus.PENDING,
            )
            session.add(request)
            await session.commit()
            await session.refresh(request)
            request_id = request.id

        req_storage_dir = VehicleService.REQUEST_STORAGE_ROOT / str(request_id)
        req_storage_dir.mkdir(parents=True, exist_ok=True)
        # Create a mockup request document
        async with AsyncSessionLocal() as session:
            doc = VehicleOwnershipRequestDocument(
                vehicle_ownership_request_id=request_id,
                document_type="STNK_PHOTO",
                storage_key=f"{request_id}/stnk-photo.jpg",
                original_filename="stnk.jpg",
                mime_type="image/jpeg",
                file_size_bytes=100,
            )
            session.add(doc)
            await session.commit()

        # Write fake file
        (req_storage_dir / "stnk-photo.jpg").write_bytes(b"mock-stnk")

        # Let's perform admin approval
        admin_token = _build_token(str(admin.id), UserRole.GOV_ADMIN)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.put(
                f"/api/v1/vehicle-ownerships/admin/requests/{request_id}/verify",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"status": "APPROVED", "review_note": "Approved by testing suite"},
            )

        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "APPROVED"
        ownership_id = body["approved_vehicle_ownership_id"]

        storage_dir = VehicleService.STORAGE_ROOT / ownership_id
        assert storage_dir.exists()

        # Verify request status in database
        async with AsyncSessionLocal() as session:
            db_request = await session.get(VehicleOwnershipRequest, request_id)
            assert db_request.status == VehicleOwnershipRequestStatus.APPROVED
            assert db_request.review_note == "Approved by testing suite"

            # Check KK eligibility was created
            result = await session.execute(
                select(KKSubsidyEligibility).where(KKSubsidyEligibility.kk_id == kk.id)
            )
            eligibility = result.scalars().first()
            assert eligibility is not None

    finally:
        async with AsyncSessionLocal() as session:
            if request_id is not None:
                await session.execute(delete(VehicleOwnershipRequestDocument).where(VehicleOwnershipRequestDocument.vehicle_ownership_request_id == request_id))
                await session.execute(delete(VehicleOwnershipRequest).where(VehicleOwnershipRequest.id == request_id))
            if ownership_id is not None:
                await session.execute(delete(VehicleOwnershipDocument).where(VehicleOwnershipDocument.vehicle_ownership_id == ownership_id))
                await session.execute(delete(VehicleOwnership).where(VehicleOwnership.id == ownership_id))
            await session.execute(delete(KKSubsidyEligibility).where(KKSubsidyEligibility.kk_id == kk.id))
            await session.execute(delete(VehicleRegistryMockup).where(VehicleRegistryMockup.id == registry_vehicle.id))
            await session.execute(delete(BuyerProfile).where(BuyerProfile.id == buyer_profile.id))
            await session.execute(delete(User).where(User.id.in_([buyer.id, admin.id])))
            await session.execute(delete(KK).where(KK.id == kk.id))
            await session.commit()

        if req_storage_dir and req_storage_dir.exists():
            shutil.rmtree(req_storage_dir, ignore_errors=True)
        if storage_dir and storage_dir.exists():
            shutil.rmtree(storage_dir, ignore_errors=True)


@pytest.mark.anyio
async def test_admin_approval_fails_when_vehicle_class_mismatches_usage_type():
    kk = KK(code=f"KK-VERIFY-{uuid4().hex[:8]}")
    buyer = User(
        name="Buyer Test",
        email=f"buyer-{uuid4().hex[:8]}@example.com",
        password=get_password_hash("secret123"),
        role=[UserRole.BUYER],
        is_active=True,
    )
    admin = User(
        name="Admin Test",
        email=f"admin-{uuid4().hex[:8]}@example.com",
        password=get_password_hash("secret123"),
        role=[UserRole.GOV_ADMIN],
        is_active=True,
    )
    buyer_profile = BuyerProfile(
        nik_snapshot=f"3174{uuid4().hex[:12]}",
        ktp_nfc_id_snapshot=f"NFC-{uuid4().hex[:8]}",
        kk=kk,
        user=buyer,
        verification_status=VerificationStatus.VERIFIED,
    )
    # The vehicle is a CAR but we try to approve it for OJOL!
    registry_vehicle = VehicleRegistryMockup(
        plate_number="B 9999 CAR",
        registration_number=f"STNK-{uuid4().hex[:8]}",
        brand="Toyota",
        vehicle_type="Avanza",
        manufacture_year=2024,
        color="Hitam",
        engine_capacity_cc=1500,
        pkb="1500000.00",
        njkb="130000000.00",
        owner_name="Buyer Test",
        owner_nik=buyer_profile.nik_snapshot,
        jenis=VehicleClass.CAR,
    )

    request_id = None

    try:
        async with AsyncSessionLocal() as session:
            session.add_all([kk, buyer, admin, buyer_profile, registry_vehicle])
            await session.commit()
            await session.refresh(buyer)
            await session.refresh(admin)
            await session.refresh(buyer_profile)
            await session.refresh(registry_vehicle)

        # Create a pending request manually
        async with AsyncSessionLocal() as session:
            request = VehicleOwnershipRequest(
                buyer_profile_id=buyer_profile.id,
                vehicle_id=registry_vehicle.id,
                ownership_status=VehicleOwnershipStatus.PERSONAL,
                usage_type=VehicleUsageType.COMMERCIAL_MOTORCYCLE, # COMMERCIAL_MOTORCYCLE requires motorcycle!
                quota_mode="DEDICATED_VEHICLE_QUOTA",
                plate_number_snapshot=registry_vehicle.plate_number,
                ktp_nfc_id_snapshot=buyer_profile.ktp_nfc_id_snapshot,
                status=VehicleOwnershipRequestStatus.PENDING,
            )
            session.add(request)
            await session.commit()
            await session.refresh(request)
            request_id = request.id

        admin_token = _build_token(str(admin.id), UserRole.GOV_ADMIN)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.put(
                f"/api/v1/vehicle-ownerships/admin/requests/{request_id}/verify",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"status": "APPROVED", "review_note": "This should fail"},
            )

        assert res.status_code == 400
        assert "OJOL usage registration requires a motorcycle" in res.json()["detail"]

    finally:
        async with AsyncSessionLocal() as session:
            if request_id is not None:
                await session.execute(delete(VehicleOwnershipRequest).where(VehicleOwnershipRequest.id == request_id))
            await session.execute(delete(VehicleRegistryMockup).where(VehicleRegistryMockup.id == registry_vehicle.id))
            await session.execute(delete(BuyerProfile).where(BuyerProfile.id == buyer_profile.id))
            await session.execute(delete(User).where(User.id.in_([buyer.id, admin.id])))
            await session.execute(delete(KK).where(KK.id == kk.id))
            await session.commit()
