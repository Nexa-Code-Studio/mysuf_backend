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
from app.modules.subsidies.models import (
    EligibilityStatus,
    KKSubsidyEligibility,
    SubsidyOwnerType,
    SubsidyPolicy,
    SubsidyQuota,
)
from app.modules.users.models import BuyerProfile, User, UserRole, VerificationStatus
from app.modules.vehicles.models import (
    VehicleOwnership,
    VehicleOwnerType,
    VehicleOwnershipStatus,
    VehicleQuotaMode,
    VehicleUsageType,
)
from app.modules.fuels.models import FuelType, SubsidyType, FuelCategory
from app.modules.transactions.models import FuelTransaction, FuelTransactionStatus, BuyerType, PaymentMethod
from app.modules.gas_stations.models import GasStation

def _build_buyer_token(user_id: str) -> str:
    return create_access_token(
        subject=user_id,
        session_id=str(uuid4()),
        client_type="BUYER_ANDROID",
        roles=[UserRole.BUYER.value],
        allowed_apps=["BUYER_ANDROID"],
    )


@pytest.mark.anyio
async def test_get_buyer_quota_detail_api():
    now = datetime.utcnow()
    kk = KK(code=f"KK-QUOTA-{uuid4().hex[:8]}")
    user = User(
        name="John Doe",
        email=f"john-quota-{uuid4().hex[:8]}@example.com",
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
        risk_score=Decimal("20.00"),  # trust factor = 80% (0.8)
    )


    gas_station = GasStation(
        name="Pertalite Station",
        latitude=-6.200000,
        longitude=106.800000,
    )

    subsidized_fuel = FuelType(
        name="Pertalite",
        octane="90",
        category=FuelCategory.GASOLINE,
        price_per_liter=Decimal("10000.00"),
        subsidy_price_per_liter=Decimal("6500.00"),
        subsidy_type=SubsidyType.SUBSIDIZED,
    )

    unsubsidized_fuel = FuelType(
        name="Pertamax",
        octane="92",
        category=FuelCategory.GASOLINE,
        price_per_liter=Decimal("13000.00"),
        subsidy_type=SubsidyType.NON_SUBSIDIZED,
    )

    my_registry_vehicle = VehicleRegistryMockup(
        plate_number="B 7777 QTA",
        registration_number=f"STNK-QTA-{uuid4().hex[:8]}",
        brand="Honda",
        vehicle_type="Civic",
        manufacture_year=2021,
        color="Merah",
        engine_capacity_cc=1498,
        pkb="4500000.00",
        njkb="280000000.00",
        owner_name="John Doe",
        owner_nik=buyer_profile.nik_snapshot,
    )

    # Variables for teardown
    kk_id = None
    user_id = None
    buyer_profile_id = None
    policy_id = None
    gas_station_id = None
    subsidized_fuel_id = None
    unsubsidized_fuel_id = None
    vehicle_registry_id = None
    ownership_id = None
    transaction_id_1 = None
    transaction_id_2 = None
    quota_id = None

    try:
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select
            policy_result = await session.execute(
                select(SubsidyPolicy).filter(SubsidyPolicy.usage_type == VehicleUsageType.PERSONAL)
            )
            policy = policy_result.scalars().first()
            created_policy = False
            if not policy:
                policy = SubsidyPolicy(
                    name="Personal Fuel Subsidy Policy",
                    usage_type=VehicleUsageType.PERSONAL,
                    monthly_quota_liters=Decimal("200.00"),
                    max_allowed_njkb=Decimal("300000000.00"),
                    is_active=True,
                )
                session.add(policy)
                await session.flush()
                created_policy = True
            else:
                policy.monthly_quota_liters = Decimal("200.00")
                await session.flush()

            session.add_all([
                kk, user, buyer_profile, gas_station,
                subsidized_fuel, unsubsidized_fuel, my_registry_vehicle
            ])
            await session.commit()
            
            await session.refresh(kk)
            await session.refresh(user)
            await session.refresh(buyer_profile)
            await session.refresh(gas_station)
            await session.refresh(subsidized_fuel)
            await session.refresh(unsubsidized_fuel)
            await session.refresh(my_registry_vehicle)

            kk_id = kk.id
            user_id = user.id
            buyer_profile_id = buyer_profile.id
            policy_id = policy.id if created_policy else None
            gas_station_id = gas_station.id
            subsidized_fuel_id = subsidized_fuel.id
            unsubsidized_fuel_id = unsubsidized_fuel.id
            vehicle_registry_id = my_registry_vehicle.id

            # Create personal quota
            # Risk factor: 200 * (1 - 20/100) = 160.00
            quota = SubsidyQuota(
                owner_type=SubsidyOwnerType.BUYER_PROFILE,
                owner_id=buyer_profile.id,
                subsidy_policy_id=policy.id,
                month=now.month,
                year=now.year,
                quota_liters=Decimal("160.00"),
                used_liters=Decimal("30.00"),
                is_active=True,
            )
            session.add(quota)
            await session.flush()
            quota_id = quota.id

            # Create vehicle ownership
            ownership = VehicleOwnership(
                owner_type=VehicleOwnerType.BUYER_PROFILE,
                owner_id=buyer_profile.id,
                vehicle_id=my_registry_vehicle.id,
                ownership_status=VehicleOwnershipStatus.PERSONAL,
                usage_type=VehicleUsageType.PERSONAL,
                quota_mode=VehicleQuotaMode.OWNER_PERSONAL_QUOTA,
                plate_number_snapshot=my_registry_vehicle.plate_number,
                ktp_nfc_id_snapshot=buyer_profile.ktp_nfc_id_snapshot,
            )
            session.add(ownership)
            await session.flush()
            ownership_id = ownership.id

            # Completed transaction for vehicle: 20 liters
            tx1 = FuelTransaction(
                buyer_type=BuyerType.PERSONAL,
                buyer_profile_id=buyer_profile.id,
                vehicle_ownership_id=ownership.id,
                gas_station_id=gas_station.id,
                fuel_type_id=subsidized_fuel.id,
                liters=Decimal("20.00"),
                is_subsidized=True,
                total_amount=Decimal("130000.00"),
                payment_method=PaymentMethod.CASH,
                transaction_status=FuelTransactionStatus.COMPLETED,
                plate_number_snapshot=my_registry_vehicle.plate_number,
                market_price_per_liter=Decimal("10000.00"),
                subsidized_price_per_liter=Decimal("6500.00"),
            )

            # Pending/Cancelled transaction for vehicle: 10 liters (should NOT be included in total)
            tx2 = FuelTransaction(
                buyer_type=BuyerType.PERSONAL,
                buyer_profile_id=buyer_profile.id,
                vehicle_ownership_id=ownership.id,
                gas_station_id=gas_station.id,
                fuel_type_id=subsidized_fuel.id,
                liters=Decimal("10.00"),
                is_subsidized=True,
                total_amount=Decimal("65000.00"),
                payment_method=PaymentMethod.CASH,
                transaction_status=FuelTransactionStatus.CANCELLED,
                plate_number_snapshot=my_registry_vehicle.plate_number,
                market_price_per_liter=Decimal("10000.00"),
                subsidized_price_per_liter=Decimal("6500.00"),
            )

            session.add_all([tx1, tx2])
            await session.commit()
            await session.refresh(tx1)
            await session.refresh(tx2)
            transaction_id_1 = tx1.id
            transaction_id_2 = tx2.id

        # Make the API request
        token = _build_buyer_token(str(user_id))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get(
                "/api/v1/users/me/quota",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 200
            data = res.json()

            # Verify personal quota details
            assert data["personal_quota"]["quota_liters"] == 160.0
            assert data["personal_quota"]["used_liters"] == 30.0
            assert data["personal_quota"]["remaining_liters"] == 130.0
            assert data["personal_quota"]["month"] == now.month
            assert data["personal_quota"]["year"] == now.year

            # Verify subsidized fuels
            sub_fuels = data["subsidized_fuels"]
            pertalite = next((item for item in sub_fuels if item["id"] == str(subsidized_fuel_id)), None)
            assert pertalite is not None
            assert pertalite["name"] == "Pertalite"
            assert pertalite["price_per_liter"] == 10000.0
            assert pertalite["subsidy_price_per_liter"] == 6500.0

            # Verify vehicle and aggregated completed liters
            vehicles = data["vehicles"]
            assert len(vehicles) == 1
            assert vehicles[0]["plate_number"] == "B 7777 QTA"
            assert vehicles[0]["brand"] == "Honda"
            assert vehicles[0]["total_liters_purchased"] == 20.0

    finally:
        # Cleanup
        async with AsyncSessionLocal() as session:
            if transaction_id_1:
                await session.execute(delete(FuelTransaction).where(FuelTransaction.id == transaction_id_1))
            if transaction_id_2:
                await session.execute(delete(FuelTransaction).where(FuelTransaction.id == transaction_id_2))
            if ownership_id:
                await session.execute(delete(VehicleOwnership).where(VehicleOwnership.id == ownership_id))
            if quota_id:
                await session.execute(delete(SubsidyQuota).where(SubsidyQuota.id == quota_id))
            if vehicle_registry_id:
                await session.execute(delete(VehicleRegistryMockup).where(VehicleRegistryMockup.id == vehicle_registry_id))
            if subsidized_fuel_id:
                await session.execute(delete(FuelType).where(FuelType.id == subsidized_fuel_id))
            if unsubsidized_fuel_id:
                await session.execute(delete(FuelType).where(FuelType.id == unsubsidized_fuel_id))
            if gas_station_id:
                await session.execute(delete(GasStation).where(GasStation.id == gas_station_id))
            if policy_id:
                await session.execute(delete(SubsidyPolicy).where(SubsidyPolicy.id == policy_id))
            if buyer_profile_id:
                await session.execute(delete(BuyerProfile).where(BuyerProfile.id == buyer_profile_id))
            if user_id:
                await session.execute(delete(User).where(User.id == user_id))
            if kk_id:
                await session.execute(delete(KK).where(KK.id == kk_id))
            await session.commit()


@pytest.mark.anyio
async def test_get_buyer_home_with_company_operational_vehicle():
    now = datetime.utcnow()
    kk = KK(code=f"KK-HOME-{uuid4().hex[:8]}")
    user = User(
        name="Jane Doe",
        email=f"jane-home-{uuid4().hex[:8]}@example.com",
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
        risk_score=Decimal("20.00"),
    )
    registry_vehicle = VehicleRegistryMockup(
        plate_number="B 8888 HOM",
        registration_number=f"STNK-HOM-{uuid4().hex[:8]}",
        brand="Toyota",
        vehicle_type="Avanza",
        manufacture_year=2022,
        color="Hitam",
        engine_capacity_cc=1496,
        pkb="3500000.00",
        njkb="220000000.00",
        owner_name="Jane Doe",
        owner_nik=buyer_profile.nik_snapshot,
    )

    kk_id = None
    user_id = None
    buyer_profile_id = None
    vehicle_registry_id = None
    ownership_id = None

    try:
        async with AsyncSessionLocal() as session:
            session.add_all([kk, user, buyer_profile, registry_vehicle])
            await session.commit()

            await session.refresh(kk)
            await session.refresh(user)
            await session.refresh(buyer_profile)
            await session.refresh(registry_vehicle)

            kk_id = kk.id
            user_id = user.id
            buyer_profile_id = buyer_profile.id
            vehicle_registry_id = registry_vehicle.id

            ownership = VehicleOwnership(
                owner_type=VehicleOwnerType.BUYER_PROFILE,
                owner_id=buyer_profile.id,
                vehicle_id=registry_vehicle.id,
                ownership_status=VehicleOwnershipStatus.COMPANY,
                usage_type=VehicleUsageType.COMPANY_OPERATIONAL,
                quota_mode=VehicleQuotaMode.DEDICATED_VEHICLE_QUOTA,
                plate_number_snapshot=registry_vehicle.plate_number,
                ktp_nfc_id_snapshot=buyer_profile.ktp_nfc_id_snapshot,
            )
            session.add(ownership)
            await session.commit()

            await session.refresh(ownership)
            ownership_id = ownership.id

        token = _build_buyer_token(str(user_id))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            home_res = await ac.get(
                "/api/v1/users/me/home",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert home_res.status_code == 200
            home_data = home_res.json()
            assert home_data["vehicle_verification"]["has_verified_vehicle"] is False
            assert home_data["vehicle_verification"]["show_verify_vehicle_cta"] is True
    finally:
        async with AsyncSessionLocal() as session:
            if ownership_id:
                await session.execute(delete(VehicleOwnership).where(VehicleOwnership.id == ownership_id))
            if vehicle_registry_id:
                await session.execute(delete(VehicleRegistryMockup).where(VehicleRegistryMockup.id == vehicle_registry_id))
            if buyer_profile_id:
                await session.execute(delete(BuyerProfile).where(BuyerProfile.id == buyer_profile_id))
            if user_id:
                await session.execute(delete(User).where(User.id == user_id))
            if kk_id:
                await session.execute(delete(KK).where(KK.id == kk_id))
            await session.commit()


@pytest.mark.anyio
async def test_home_hides_personal_quota_when_eligibility_record_is_missing():
    kk = KK(code=f"KK-QUOTA-MISSING-{uuid4().hex[:8]}")
    user = User(
        name="Missing Eligibility Buyer",
        email=f"missing-eligibility-{uuid4().hex[:8]}@example.com",
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
        risk_score=Decimal("60.00"),
    )

    created_policy = False
    policy_id = None
    kk_id = None
    user_id = None
    buyer_profile_id = None

    try:
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select

            policy_result = await session.execute(
                select(SubsidyPolicy).filter(SubsidyPolicy.usage_type == VehicleUsageType.PERSONAL)
            )
            policy = policy_result.scalars().first()
            if policy is None:
                policy = SubsidyPolicy(
                    name="Quota Personal",
                    usage_type=VehicleUsageType.PERSONAL,
                    monthly_quota_liters=Decimal("250.00"),
                    max_allowed_njkb=Decimal("250000000.00"),
                    is_active=True,
                )
                session.add(policy)
                await session.commit()
                await session.refresh(policy)
                created_policy = True
            policy_id = policy.id

            session.add_all([kk, user, buyer_profile])
            await session.commit()

            await session.refresh(kk)
            await session.refresh(user)
            await session.refresh(buyer_profile)

            kk_id = kk.id
            user_id = user.id
            buyer_profile_id = buyer_profile.id

        token = _build_buyer_token(str(user_id))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            home_res = await ac.get(
                "/api/v1/users/me/home",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert home_res.status_code == 200
            home_data = home_res.json()
            assert home_data["personal_quota"] is None

            profile_res = await ac.get(
                "/api/v1/users/me/profile",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert profile_res.status_code == 200
            profile_data = profile_res.json()
            assert profile_data["isEligible"] is False
            assert profile_data["quotaRemaining"] == 0
    finally:
        async with AsyncSessionLocal() as session:
            if buyer_profile_id:
                await session.execute(delete(BuyerProfile).where(BuyerProfile.id == buyer_profile_id))
            if user_id:
                await session.execute(delete(User).where(User.id == user_id))
            if kk_id:
                await session.execute(delete(KK).where(KK.id == kk_id))
            if created_policy and policy_id:
                await session.execute(delete(SubsidyPolicy).where(SubsidyPolicy.id == policy_id))
            await session.commit()


@pytest.mark.anyio
async def test_ineligible_buyer_quota_is_hidden_from_home_and_quota_api():
    now = datetime.utcnow()
    kk = KK(code=f"KK-NONELIG-{uuid4().hex[:8]}")
    user = User(
        name="Jane Doe",
        email=f"jane-quota-{uuid4().hex[:8]}@example.com",
        password=get_password_hash("secret123"),
        role=[UserRole.BUYER],
        is_active=True,
    )
    buyer_profile = BuyerProfile(
        nik_snapshot=f"3172{uuid4().hex[:12]}",
        ktp_nfc_id_snapshot=f"NFC-{uuid4().hex[:8]}",
        kk=kk,
        user=user,
        verification_status=VerificationStatus.VERIFIED,
        risk_score=Decimal("10.00"),
    )
    registry_vehicle = VehicleRegistryMockup(
        plate_number="B 9999 NEL",
        registration_number=f"STNK-NEL-{uuid4().hex[:8]}",
        brand="Toyota",
        vehicle_type="Fortuner",
        manufacture_year=2024,
        color="Hitam",
        engine_capacity_cc=2755,
        pkb="8500000.00",
        njkb="650000000.00",
        owner_name="Jane Doe",
        owner_nik=buyer_profile.nik_snapshot,
    )

    kk_id = None
    user_id = None
    buyer_profile_id = None
    policy_id = None
    vehicle_registry_id = None
    ownership_id = None
    quota_id = None
    eligibility_id = None

    try:
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select

            policy_result = await session.execute(
                select(SubsidyPolicy).filter(SubsidyPolicy.usage_type == VehicleUsageType.PERSONAL)
            )
            policy = policy_result.scalars().first()
            created_policy = False
            if not policy:
                policy = SubsidyPolicy(
                    name="Personal Fuel Subsidy Policy",
                    usage_type=VehicleUsageType.PERSONAL,
                    monthly_quota_liters=Decimal("200.00"),
                    max_allowed_njkb=Decimal("300000000.00"),
                    is_active=True,
                )
                session.add(policy)
                await session.flush()
                created_policy = True

            session.add_all([kk, user, buyer_profile, registry_vehicle])
            await session.commit()

            await session.refresh(kk)
            await session.refresh(user)
            await session.refresh(buyer_profile)
            await session.refresh(registry_vehicle)

            kk_id = kk.id
            user_id = user.id
            buyer_profile_id = buyer_profile.id
            policy_id = policy.id if created_policy else None
            vehicle_registry_id = registry_vehicle.id

            ownership = VehicleOwnership(
                owner_type=VehicleOwnerType.BUYER_PROFILE,
                owner_id=buyer_profile.id,
                vehicle_id=registry_vehicle.id,
                ownership_status=VehicleOwnershipStatus.PERSONAL,
                usage_type=VehicleUsageType.PERSONAL,
                quota_mode=VehicleQuotaMode.OWNER_PERSONAL_QUOTA,
                plate_number_snapshot=registry_vehicle.plate_number,
                ktp_nfc_id_snapshot=buyer_profile.ktp_nfc_id_snapshot,
            )
            quota = SubsidyQuota(
                owner_type=SubsidyOwnerType.BUYER_PROFILE,
                owner_id=buyer_profile.id,
                subsidy_policy_id=policy.id,
                month=now.month,
                year=now.year,
                quota_liters=Decimal("180.00"),
                used_liters=Decimal("20.00"),
                is_active=True,
            )
            eligibility = KKSubsidyEligibility(
                kk_id=buyer_profile.kk_id,
                subsidy_policy_id=policy.id,
                total_njkb=Decimal("650000000.00"),
                eligibility_status=EligibilityStatus.NOT_ELIGIBLE,
                eligibility_reason="Total NJKB kendaraan unik dalam KK melebihi batas.",
                checked_at=now,
            )
            session.add_all([ownership, quota, eligibility])
            await session.commit()

            await session.refresh(ownership)
            await session.refresh(quota)
            await session.refresh(eligibility)
            ownership_id = ownership.id
            quota_id = quota.id
            eligibility_id = eligibility.id

        token = _build_buyer_token(str(user_id))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            quota_res = await ac.get(
                "/api/v1/users/me/quota",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert quota_res.status_code == 200
            quota_data = quota_res.json()
            assert quota_data["personal_quota"] is None
            assert len(quota_data["vehicles"]) == 1

            home_res = await ac.get(
                "/api/v1/users/me/home",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert home_res.status_code == 200
            home_data = home_res.json()
            assert home_data["personal_quota"] is None
            assert home_data["vehicle_verification"]["has_verified_vehicle"] is True
    finally:
        async with AsyncSessionLocal() as session:
            if ownership_id:
                await session.execute(delete(VehicleOwnership).where(VehicleOwnership.id == ownership_id))
            if quota_id:
                await session.execute(delete(SubsidyQuota).where(SubsidyQuota.id == quota_id))
            if eligibility_id:
                await session.execute(delete(KKSubsidyEligibility).where(KKSubsidyEligibility.id == eligibility_id))
            if vehicle_registry_id:
                await session.execute(delete(VehicleRegistryMockup).where(VehicleRegistryMockup.id == vehicle_registry_id))
            if policy_id:
                await session.execute(delete(SubsidyPolicy).where(SubsidyPolicy.id == policy_id))
            if buyer_profile_id:
                await session.execute(delete(BuyerProfile).where(BuyerProfile.id == buyer_profile_id))
            if user_id:
                await session.execute(delete(User).where(User.id == user_id))
            if kk_id:
                await session.execute(delete(KK).where(KK.id == kk_id))
            await session.commit()
