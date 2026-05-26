from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.modules.registries.models import KK, VehicleRegistryMockup
from app.modules.subsidies.models import SubsidyOwnerType, SubsidyQuota
from app.modules.users.models import BuyerProfile, User, UserRole, VerificationStatus
from app.modules.vehicles.models import (
    VehicleOwnership,
    VehicleOwnershipDocument,
    VehicleOwnershipDocumentType,
    VehicleOwnerType,
    VehicleOwnershipStatus,
    VehicleQuotaMode,
    VehicleUsageType,
)


def _build_buyer_token(user_id: str) -> str:
    return create_access_token(
        subject=user_id,
        session_id=str(uuid4()),
        client_type="BUYER_ANDROID",
        roles=[UserRole.BUYER.value],
        allowed_apps=["BUYER_ANDROID"],
    )


@pytest.mark.anyio
async def test_buyer_vehicle_list_and_detail_use_buyer_profile_ktp_snapshot_and_registry_details():
    now = datetime.utcnow()
    kk = KK(code=f"KK-READ-{uuid4().hex[:8]}")
    user = User(
        name="Buyer Read",
        email=f"buyer-read-{uuid4().hex[:8]}@example.com",
        password=get_password_hash("secret123"),
        role=[UserRole.BUYER],
        is_active=True,
    )
    buyer_profile = BuyerProfile(
        nik_snapshot=f"3171{uuid4().hex[:12]}",
        ktp_nfc_id_snapshot=f"NFC-{uuid4().hex[:8]}",
        kk=kk,
        user=user,
        verification_status=VerificationStatus.VERIFIED,
        risk_score=Decimal("10.00"),
    )
    my_registry_vehicle = VehicleRegistryMockup(
        plate_number="B 1111 READ",
        registration_number=f"STNK-READ-{uuid4().hex[:8]}",
        brand="Toyota",
        vehicle_type="Avanza",
        manufacture_year=2020,
        color="Hitam",
        engine_capacity_cc=1496,
        pkb="450000.00",
        njkb="175000000.00",
        owner_name="Buyer Read",
        owner_nik=buyer_profile.nik_snapshot,
    )
    other_registry_vehicle = VehicleRegistryMockup(
        plate_number="B 2222 READ",
        registration_number=f"STNK-OTHER-{uuid4().hex[:8]}",
        brand="Honda",
        vehicle_type="Brio",
        manufacture_year=2021,
        color="Putih",
        engine_capacity_cc=1199,
        pkb="400000.00",
        njkb="160000000.00",
        owner_name="Other Buyer",
        owner_nik=f"3201{uuid4().hex[:12]}",
    )
    commercial_registry_vehicle = VehicleRegistryMockup(
        plate_number="B 3333 COMM",
        registration_number=f"STNK-COMM-{uuid4().hex[:8]}",
        brand="Yamaha",
        vehicle_type="NMAX",
        manufacture_year=2022,
        color="Biru",
        engine_capacity_cc=155,
        pkb="500000.00",
        njkb="32000000.00",
        owner_name="Buyer Read",
        owner_nik=buyer_profile.nik_snapshot,
    )

    my_ownership_id = None
    my_doc_id = None
    commercial_ownership_id = None
    other_ownership_id = None
    kk_id = None
    user_id = None
    buyer_profile_id = None
    my_registry_vehicle_id = None
    commercial_registry_vehicle_id = None
    other_registry_vehicle_id = None

    try:
        async with AsyncSessionLocal() as session:
            session.add_all([kk, user, buyer_profile, my_registry_vehicle, other_registry_vehicle, commercial_registry_vehicle])
            await session.commit()
            await session.refresh(user)
            await session.refresh(buyer_profile)
            await session.refresh(my_registry_vehicle)
            await session.refresh(other_registry_vehicle)
            await session.refresh(commercial_registry_vehicle)

            my_ownership = VehicleOwnership(
                owner_type=VehicleOwnerType.BUYER_PROFILE,
                owner_id=buyer_profile.id,
                vehicle_id=my_registry_vehicle.id,
                ownership_status=VehicleOwnershipStatus.PERSONAL,
                usage_type=VehicleUsageType.PERSONAL,
                quota_mode=VehicleQuotaMode.OWNER_PERSONAL_QUOTA,
                plate_number_snapshot=my_registry_vehicle.plate_number,
                ktp_nfc_id_snapshot=buyer_profile.ktp_nfc_id_snapshot,
            )
            other_ownership = VehicleOwnership(
                owner_type=VehicleOwnerType.BUYER_PROFILE,
                owner_id=uuid4(),
                vehicle_id=other_registry_vehicle.id,
                ownership_status=VehicleOwnershipStatus.PERSONAL,
                usage_type=VehicleUsageType.COMMERCIAL_MOTORCYCLE,
                quota_mode=VehicleQuotaMode.DEDICATED_VEHICLE_QUOTA,
                plate_number_snapshot=other_registry_vehicle.plate_number,
                ktp_nfc_id_snapshot="NFC-OTHER-0001",
            )
            commercial_ownership = VehicleOwnership(
                owner_type=VehicleOwnerType.BUYER_PROFILE,
                owner_id=buyer_profile.id,
                vehicle_id=commercial_registry_vehicle.id,
                ownership_status=VehicleOwnershipStatus.PERSONAL,
                usage_type=VehicleUsageType.COMMERCIAL_MOTORCYCLE,
                quota_mode=VehicleQuotaMode.DEDICATED_VEHICLE_QUOTA,
                plate_number_snapshot=commercial_registry_vehicle.plate_number,
                ktp_nfc_id_snapshot=buyer_profile.ktp_nfc_id_snapshot,
            )
            session.add_all([my_ownership, other_ownership, commercial_ownership])
            await session.flush()

            my_doc = VehicleOwnershipDocument(
                vehicle_ownership_id=my_ownership.id,
                document_type=VehicleOwnershipDocumentType.STNK_PHOTO,
                storage_key=f"{my_ownership.id}/stnk-photo.jpg",
                original_filename="stnk-photo.jpg",
                mime_type="image/jpeg",
                file_size_bytes=123,
                checksum_sha256="checksum",
            )
            session.add(my_doc)
            session.add(
                SubsidyQuota(
                    owner_type=SubsidyOwnerType.VEHICLE,
                    owner_id=commercial_registry_vehicle.id,
                    month=now.month,
                    year=now.year,
                    quota_liters="250.00",
                    used_liters="70.00",
                    is_active=True,
                )
            )
            await session.commit()

            my_ownership_id = my_ownership.id
            my_doc_id = my_doc.id
            commercial_ownership_id = commercial_ownership.id
            other_ownership_id = other_ownership.id
            kk_id = kk.id
            user_id = user.id
            buyer_profile_id = buyer_profile.id
            my_registry_vehicle_id = my_registry_vehicle.id
            commercial_registry_vehicle_id = commercial_registry_vehicle.id
            other_registry_vehicle_id = other_registry_vehicle.id

        token = _build_buyer_token(str(user_id))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            list_res = await ac.get(
                "/api/v1/vehicle-ownerships/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert list_res.status_code == 200
            list_body = list_res.json()
            assert len(list_body["items"]) == 2
            personal_item = next(item for item in list_body["items"] if item["ownership_id"] == str(my_ownership_id))
            commercial_item = next(item for item in list_body["items"] if item["ownership_id"] == str(commercial_ownership_id))
            assert personal_item["plate_number"] == "B 1111 READ"
            assert personal_item["type_label"] == "Toyota - Avanza"
            assert personal_item["category"] == "nonCommercial"
            assert personal_item["quota_liters"] is None
            assert commercial_item["plate_number"] == "B 3333 COMM"
            assert commercial_item["category"] == "commercial"
            assert commercial_item["quota_liters"] == 225.0
            assert commercial_item["used_liters"] == 70.0
            assert commercial_item["remaining_liters"] == 155.0

            detail_res = await ac.get(
                f"/api/v1/vehicle-ownerships/{my_ownership_id}/detail",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert detail_res.status_code == 200
            detail_body = detail_res.json()
            assert detail_body["ownership_id"] == str(my_ownership_id)
            assert detail_body["registration_number"] == my_registry_vehicle.registration_number
            assert detail_body["brand"] == "Toyota"
            assert detail_body["vehicle_type"] == "Avanza"
            assert detail_body["documents"][0]["document_type"] == "STNK_PHOTO"
            assert detail_body["quota_liters"] is None

            commercial_detail_res = await ac.get(
                f"/api/v1/vehicle-ownerships/{commercial_ownership_id}/detail",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert commercial_detail_res.status_code == 200
            commercial_detail_body = commercial_detail_res.json()
            assert commercial_detail_body["usage_type"] == "COMMERCIAL_MOTORCYCLE"
            assert commercial_detail_body["quota_liters"] == 225.0
            assert commercial_detail_body["used_liters"] == 70.0
            assert commercial_detail_body["remaining_liters"] == 155.0

            forbidden_detail_res = await ac.get(
                f"/api/v1/vehicle-ownerships/{other_ownership_id}/detail",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert forbidden_detail_res.status_code == 404
    finally:
        async with AsyncSessionLocal() as session:
            if my_doc_id is not None:
                await session.execute(delete(VehicleOwnershipDocument).where(VehicleOwnershipDocument.id == my_doc_id))
            if my_ownership_id is not None:
                await session.execute(delete(VehicleOwnership).where(VehicleOwnership.id == my_ownership_id))
            if commercial_ownership_id is not None:
                await session.execute(delete(VehicleOwnership).where(VehicleOwnership.id == commercial_ownership_id))
            if other_ownership_id is not None:
                await session.execute(delete(VehicleOwnership).where(VehicleOwnership.id == other_ownership_id))
            if my_registry_vehicle_id is not None:
                await session.execute(delete(VehicleRegistryMockup).where(VehicleRegistryMockup.id == my_registry_vehicle_id))
            if commercial_registry_vehicle_id is not None:
                await session.execute(delete(SubsidyQuota).where(SubsidyQuota.owner_id == commercial_registry_vehicle_id))
                await session.execute(delete(VehicleRegistryMockup).where(VehicleRegistryMockup.id == commercial_registry_vehicle_id))
            if other_registry_vehicle_id is not None:
                await session.execute(delete(VehicleRegistryMockup).where(VehicleRegistryMockup.id == other_registry_vehicle_id))
            if buyer_profile_id is not None:
                await session.execute(delete(BuyerProfile).where(BuyerProfile.id == buyer_profile_id))
            if user_id is not None:
                await session.execute(delete(User).where(User.id == user_id))
            if kk_id is not None:
                await session.execute(delete(KK).where(KK.id == kk_id))
            await session.commit()
