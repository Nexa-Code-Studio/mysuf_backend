from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.modules.registries.models import KK, VehicleRegistryMockup
from app.modules.transactions.models import CashierScanEvent
from app.modules.users.models import BuyerProfile, User, UserRole, VerificationStatus
from app.modules.vehicles.models import (
    VehicleOwnership,
    VehicleOwnerType,
    VehicleOwnershipStatus,
    VehicleQuotaMode,
    VehicleUsageType,
)


def _build_sales_officer_token(user_id: str) -> str:
    return create_access_token(
        subject=user_id,
        session_id=str(uuid4()),
        client_type="POS_ANDROID",
        roles=[UserRole.SALES_OFFICER.value],
        allowed_apps=["POS_ANDROID"],
    )


@pytest.mark.anyio
async def test_cashier_can_lookup_buyer_and_vehicles_by_nfc_id():
    kk = KK(code=f"KK-NFC-{uuid4().hex[:8]}")
    buyer_user = User(
        name="Buyer NFC",
        email=f"buyer-nfc-{uuid4().hex[:8]}@example.com",
        password=get_password_hash("secret123"),
        role=[UserRole.BUYER],
        is_active=True,
    )
    buyer_profile = BuyerProfile(
        nik_snapshot=f"3171{uuid4().hex[:12]}",
        ktp_nfc_id_snapshot=f"NFC-{uuid4().hex[:10]}",
        kk=kk,
        user=buyer_user,
        verification_status=VerificationStatus.VERIFIED,
        risk_score=Decimal("12.50"),
    )
    sales_officer = User(
        name="Cashier NFC",
        email=f"cashier-nfc-{uuid4().hex[:8]}@example.com",
        password=get_password_hash("secret123"),
        role=[UserRole.SALES_OFFICER],
        is_active=True,
    )
    vehicle_a = VehicleRegistryMockup(
        plate_number="B 1111 NFC",
        registration_number=f"STNK-NFC-{uuid4().hex[:8]}",
        brand="Toyota",
        vehicle_type="Avanza",
        manufacture_year=2021,
        color="Hitam",
        engine_capacity_cc=1496,
        pkb="450000.00",
        njkb="175000000.00",
        owner_name="Buyer NFC",
        owner_nik=buyer_profile.nik_snapshot,
    )
    vehicle_b = VehicleRegistryMockup(
        plate_number="B 2222 NFC",
        registration_number=f"STNK-NFC-{uuid4().hex[:8]}",
        brand="Honda",
        vehicle_type="Vario",
        manufacture_year=2023,
        color="Merah",
        engine_capacity_cc=160,
        pkb="250000.00",
        njkb="29000000.00",
        owner_name="Buyer NFC",
        owner_nik=buyer_profile.nik_snapshot,
    )
    vehicle_other = VehicleRegistryMockup(
        plate_number="D 9999 OTH",
        registration_number=f"STNK-OTH-{uuid4().hex[:8]}",
        brand="Suzuki",
        vehicle_type="Ertiga",
        manufacture_year=2020,
        color="Putih",
        engine_capacity_cc=1462,
        pkb="400000.00",
        njkb="160000000.00",
        owner_name="Other Buyer",
        owner_nik=f"3201{uuid4().hex[:12]}",
    )

    kk_id = None
    buyer_user_id = None
    buyer_profile_id = None
    sales_officer_id = None
    vehicle_a_id = None
    vehicle_b_id = None
    vehicle_other_id = None
    ownership_a_id = None
    ownership_b_id = None
    ownership_other_id = None

    try:
        async with AsyncSessionLocal() as session:
            session.add_all([kk, buyer_user, buyer_profile, sales_officer, vehicle_a, vehicle_b, vehicle_other])
            await session.commit()
            await session.refresh(kk)
            await session.refresh(buyer_user)
            await session.refresh(buyer_profile)
            await session.refresh(sales_officer)
            await session.refresh(vehicle_a)
            await session.refresh(vehicle_b)
            await session.refresh(vehicle_other)

            ownership_a = VehicleOwnership(
                owner_type=VehicleOwnerType.BUYER_PROFILE,
                owner_id=buyer_profile.id,
                vehicle_id=vehicle_a.id,
                ownership_status=VehicleOwnershipStatus.PERSONAL,
                usage_type=VehicleUsageType.PERSONAL,
                quota_mode=VehicleQuotaMode.OWNER_PERSONAL_QUOTA,
                plate_number_snapshot=vehicle_a.plate_number,
                ktp_nfc_id_snapshot=buyer_profile.ktp_nfc_id_snapshot,
            )
            ownership_b = VehicleOwnership(
                owner_type=VehicleOwnerType.BUYER_PROFILE,
                owner_id=buyer_profile.id,
                vehicle_id=vehicle_b.id,
                ownership_status=VehicleOwnershipStatus.PERSONAL,
                usage_type=VehicleUsageType.OJOL,
                quota_mode=VehicleQuotaMode.DEDICATED_VEHICLE_QUOTA,
                plate_number_snapshot=vehicle_b.plate_number,
                ktp_nfc_id_snapshot=buyer_profile.ktp_nfc_id_snapshot,
            )
            ownership_other = VehicleOwnership(
                owner_type=VehicleOwnerType.BUYER_PROFILE,
                owner_id=uuid4(),
                vehicle_id=vehicle_other.id,
                ownership_status=VehicleOwnershipStatus.PERSONAL,
                usage_type=VehicleUsageType.PERSONAL,
                quota_mode=VehicleQuotaMode.OWNER_PERSONAL_QUOTA,
                plate_number_snapshot=vehicle_other.plate_number,
                ktp_nfc_id_snapshot="NFC-OTHER-0001",
            )
            session.add_all([ownership_a, ownership_b, ownership_other])
            await session.commit()

            kk_id = kk.id
            buyer_user_id = buyer_user.id
            buyer_profile_id = buyer_profile.id
            sales_officer_id = sales_officer.id
            vehicle_a_id = vehicle_a.id
            vehicle_b_id = vehicle_b.id
            vehicle_other_id = vehicle_other.id
            ownership_a_id = ownership_a.id
            ownership_b_id = ownership_b.id
            ownership_other_id = ownership_other.id

        token = _build_sales_officer_token(str(sales_officer_id))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(
                f"/api/v1/vehicle-ownerships/cashier/by-nfc/{buyer_profile.ktp_nfc_id_snapshot}",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["buyer"]["buyer_profile_id"] == str(buyer_profile_id)
        assert body["buyer"]["user_id"] == str(buyer_user_id)
        assert body["buyer"]["name"] == "Buyer NFC"
        assert body["buyer"]["nik_snapshot"] == buyer_profile.nik_snapshot
        assert body["buyer"]["verification_status"] == "VERIFIED"
        assert body["buyer"]["risk_score"] == 12.5

        assert len(body["vehicles"]) == 2
        vehicles_by_id = {item["ownership_id"]: item for item in body["vehicles"]}

        assert str(ownership_a_id) in vehicles_by_id
        assert str(ownership_b_id) in vehicles_by_id
        assert str(ownership_other_id) not in vehicles_by_id

        personal_vehicle = vehicles_by_id[str(ownership_a_id)]
        assert personal_vehicle["plate_number"] == "B 1111 NFC"
        assert personal_vehicle["registration_number"] == vehicle_a.registration_number
        assert personal_vehicle["type_label"] == "Toyota - Avanza"
        assert personal_vehicle["category"] == "nonCommercial"
        assert personal_vehicle["brand"] == "Toyota"
        assert personal_vehicle["vehicle_type"] == "Avanza"

        ojol_vehicle = vehicles_by_id[str(ownership_b_id)]
        assert ojol_vehicle["plate_number"] == "B 2222 NFC"
        assert ojol_vehicle["registration_number"] == vehicle_b.registration_number
        assert ojol_vehicle["type_label"] == "Honda - Vario"
        assert ojol_vehicle["category"] == "commercial"
        assert ojol_vehicle["usage_type"] == "OJOL"
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(CashierScanEvent).where(CashierScanEvent.cashier_user_id == sales_officer_id)
            )
            if ownership_a_id is not None:
                await session.execute(delete(VehicleOwnership).where(VehicleOwnership.id == ownership_a_id))
            if ownership_b_id is not None:
                await session.execute(delete(VehicleOwnership).where(VehicleOwnership.id == ownership_b_id))
            if ownership_other_id is not None:
                await session.execute(delete(VehicleOwnership).where(VehicleOwnership.id == ownership_other_id))
            if vehicle_a_id is not None:
                await session.execute(delete(VehicleRegistryMockup).where(VehicleRegistryMockup.id == vehicle_a_id))
            if vehicle_b_id is not None:
                await session.execute(delete(VehicleRegistryMockup).where(VehicleRegistryMockup.id == vehicle_b_id))
            if vehicle_other_id is not None:
                await session.execute(delete(VehicleRegistryMockup).where(VehicleRegistryMockup.id == vehicle_other_id))
            if buyer_profile_id is not None:
                await session.execute(delete(BuyerProfile).where(BuyerProfile.id == buyer_profile_id))
            if buyer_user_id is not None:
                await session.execute(delete(User).where(User.id == buyer_user_id))
            if sales_officer_id is not None:
                await session.execute(delete(User).where(User.id == sales_officer_id))
            if kk_id is not None:
                await session.execute(delete(KK).where(KK.id == kk_id))
            await session.commit()


@pytest.mark.anyio
async def test_cashier_nfc_lookup_returns_404_when_buyer_profile_missing():
    sales_officer = User(
        name="Cashier Missing NFC",
        email=f"cashier-missing-{uuid4().hex[:8]}@example.com",
        password=get_password_hash("secret123"),
        role=[UserRole.SALES_OFFICER],
        is_active=True,
    )
    sales_officer_id = None

    try:
        async with AsyncSessionLocal() as session:
            session.add(sales_officer)
            await session.commit()
            await session.refresh(sales_officer)
            sales_officer_id = sales_officer.id

        token = _build_sales_officer_token(str(sales_officer_id))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(
                "/api/v1/vehicle-ownerships/cashier/by-nfc/NFC-NOT-FOUND",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 404
        assert response.json()["detail"] == "Buyer profile not found for the provided NFC ID or NIK."
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(CashierScanEvent).where(CashierScanEvent.cashier_user_id == sales_officer_id)
            )
            if sales_officer_id is not None:
                await session.execute(delete(User).where(User.id == sales_officer_id))
            await session.commit()
