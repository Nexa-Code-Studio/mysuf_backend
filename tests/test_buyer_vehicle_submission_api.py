import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.modules.registries.models import KK, VehicleRegistryMockup
from app.modules.subsidies.models import EligibilityStatus, KKSubsidyEligibility
from app.modules.users.models import BuyerProfile, User, UserRole, VerificationStatus
from app.modules.vehicles.models import (
    VehicleOwnership,
    VehicleOwnershipDocument,
    VehicleOwnershipRequest,
    VehicleOwnershipRequestDocument,
)
from app.modules.vehicles.service import VehicleService


def _build_buyer_token(user_id: str) -> str:
    return create_access_token(
        subject=user_id,
        session_id=str(uuid4()),
        client_type="BUYER_ANDROID",
        roles=[UserRole.BUYER.value],
        allowed_apps=["BUYER_ANDROID"],
    )


@pytest.mark.anyio
async def test_buyer_personal_vehicle_submission_creates_vehicle_ownership():
    kk = KK(code=f"KK-SUBMIT-{uuid4().hex[:8]}")
    user = User(
        name="Buyer Submit",
        email=f"buyer-submit-{uuid4().hex[:8]}@example.com",
        password=get_password_hash("secret123"),
        role=[UserRole.BUYER],
        is_active=True,
    )
    buyer_profile = BuyerProfile(
        nik_snapshot=f"3174{uuid4().hex[:12]}",
        ktp_nfc_id_snapshot=f"NFC-{uuid4().hex[:8]}",
        kk=kk,
        user=user,
        verification_status=VerificationStatus.VERIFIED,
    )
    registry_vehicle = VehicleRegistryMockup(
        plate_number="B 7000 TEST",
        registration_number=f"STNK-SUBMIT-{uuid4().hex[:8]}",
        brand="Honda",
        vehicle_type="Beat",
        manufacture_year=2024,
        color="Hitam",
        engine_capacity_cc=110,
        pkb="450000.00",
        njkb="23000000.00",
        owner_name="Buyer Submit",
        owner_nik=buyer_profile.nik_snapshot,
    )
    ownership_id = None
    storage_dir: Path | None = None
    kk_id = None
    user_id = None
    buyer_profile_id = None
    registry_vehicle_id = None

    try:
        async with AsyncSessionLocal() as session:
            session.add_all([kk, user, buyer_profile, registry_vehicle])
            await session.commit()
            await session.refresh(user)
            await session.refresh(buyer_profile)
            await session.refresh(registry_vehicle)
            kk_id = kk.id
            user_id = user.id
            buyer_profile_id = buyer_profile.id
            registry_vehicle_id = registry_vehicle.id

        token = _build_buyer_token(str(user.id))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.post(
                "/api/v1/vehicle-ownerships/submissions",
                headers={"Authorization": f"Bearer {token}"},
                data={
                    "registration_number": registry_vehicle.registration_number,
                    "usage_type": "PERSONAL",
                },
                files={
                    "stnk_photo": ("stnk.jpg", b"fake-stnk-image", "image/jpeg"),
                    "vehicle_photo": ("vehicle.jpg", b"fake-vehicle-image", "image/jpeg"),
                },
            )

        assert res.status_code == 201
        body = res.json()
        assert body["submission_type"] == "created"
        assert body["ownership"] is not None
        assert body["request"] is None
        assert body["ownership"]["usage_type"] == "PERSONAL"
        ownership_id = body["ownership"]["id"]

        storage_dir = VehicleService.STORAGE_ROOT / ownership_id
        assert storage_dir.exists()
        assert (storage_dir / "stnk-photo.jpg").exists()
        assert (storage_dir / "vehicle-photo.jpg").exists()

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(KKSubsidyEligibility).where(KKSubsidyEligibility.kk_id == kk_id)
            )
            eligibility = result.scalars().first()
            assert eligibility is not None
            assert eligibility.eligibility_status == EligibilityStatus.ELIGIBLE
    finally:
        async with AsyncSessionLocal() as session:
            if ownership_id is not None:
                await session.execute(delete(VehicleOwnershipDocument).where(VehicleOwnershipDocument.vehicle_ownership_id == ownership_id))
                await session.execute(delete(VehicleOwnership).where(VehicleOwnership.id == ownership_id))
            if kk_id is not None:
                await session.execute(delete(KKSubsidyEligibility).where(KKSubsidyEligibility.kk_id == kk_id))
            if registry_vehicle_id is not None:
                await session.execute(delete(VehicleRegistryMockup).where(VehicleRegistryMockup.id == registry_vehicle_id))
            if buyer_profile_id is not None:
                await session.execute(delete(BuyerProfile).where(BuyerProfile.id == buyer_profile_id))
            if user_id is not None:
                await session.execute(delete(User).where(User.id == user_id))
            if kk_id is not None:
                await session.execute(delete(KK).where(KK.id == kk_id))
            await session.commit()

        if storage_dir and storage_dir.exists():
            shutil.rmtree(storage_dir, ignore_errors=True)


@pytest.mark.anyio
async def test_buyer_ojol_vehicle_submission_creates_pending_request():
    kk = KK(code=f"KK-REQ-{uuid4().hex[:8]}")
    user = User(
        name="Buyer Request",
        email=f"buyer-request-{uuid4().hex[:8]}@example.com",
        password=get_password_hash("secret123"),
        role=[UserRole.BUYER],
        is_active=True,
    )
    buyer_profile = BuyerProfile(
        nik_snapshot=f"3175{uuid4().hex[:12]}",
        ktp_nfc_id_snapshot=f"NFC-{uuid4().hex[:8]}",
        kk=kk,
        user=user,
        verification_status=VerificationStatus.VERIFIED,
    )
    registry_vehicle = VehicleRegistryMockup(
        plate_number="B 8000 TEST",
        registration_number=f"STNK-REQ-{uuid4().hex[:8]}",
        brand="Yamaha",
        vehicle_type="NMAX",
        manufacture_year=2024,
        color="Merah",
        engine_capacity_cc=155,
        pkb="650000.00",
        njkb="32000000.00",
        owner_name="Buyer Request",
        owner_nik=buyer_profile.nik_snapshot,
    )
    request_id = None
    storage_dir: Path | None = None
    kk_id = None
    user_id = None
    buyer_profile_id = None
    registry_vehicle_id = None

    try:
        async with AsyncSessionLocal() as session:
            session.add_all([kk, user, buyer_profile, registry_vehicle])
            await session.commit()
            await session.refresh(user)
            await session.refresh(buyer_profile)
            await session.refresh(registry_vehicle)
            kk_id = kk.id
            user_id = user.id
            buyer_profile_id = buyer_profile.id
            registry_vehicle_id = registry_vehicle.id

        token = _build_buyer_token(str(user.id))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.post(
                "/api/v1/vehicle-ownerships/submissions",
                headers={"Authorization": f"Bearer {token}"},
                data={
                    "registration_number": registry_vehicle.registration_number,
                    "usage_type": "OJOL",
                },
                files={
                    "stnk_photo": ("stnk.jpg", b"fake-stnk-image", "image/jpeg"),
                    "vehicle_photo": ("vehicle.jpg", b"fake-vehicle-image", "image/jpeg"),
                    "productive_business_proof": ("proof.pdf", b"fake-proof-pdf", "application/pdf"),
                },
            )

        assert res.status_code == 201
        body = res.json()
        assert body["submission_type"] == "pending_review"
        assert body["ownership"] is None
        assert body["request"] is not None
        assert body["request"]["status"] == "PENDING"
        request_id = body["request"]["id"]

        storage_dir = VehicleService.REQUEST_STORAGE_ROOT / request_id
        assert storage_dir.exists()
        assert (storage_dir / "stnk-photo.jpg").exists()
        assert (storage_dir / "vehicle-photo.jpg").exists()
        assert (storage_dir / "productive-business-proof.pdf").exists()
    finally:
        async with AsyncSessionLocal() as session:
            if request_id is not None:
                await session.execute(
                    delete(VehicleOwnershipRequestDocument).where(
                        VehicleOwnershipRequestDocument.vehicle_ownership_request_id == request_id
                    )
                )
                await session.execute(delete(VehicleOwnershipRequest).where(VehicleOwnershipRequest.id == request_id))
            if kk_id is not None:
                await session.execute(delete(KKSubsidyEligibility).where(KKSubsidyEligibility.kk_id == kk_id))
            if registry_vehicle_id is not None:
                await session.execute(delete(VehicleRegistryMockup).where(VehicleRegistryMockup.id == registry_vehicle_id))
            if buyer_profile_id is not None:
                await session.execute(delete(BuyerProfile).where(BuyerProfile.id == buyer_profile_id))
            if user_id is not None:
                await session.execute(delete(User).where(User.id == user_id))
            if kk_id is not None:
                await session.execute(delete(KK).where(KK.id == kk_id))
            await session.commit()

        if storage_dir and storage_dir.exists():
            shutil.rmtree(storage_dir, ignore_errors=True)
