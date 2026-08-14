import pytest
from httpx import AsyncClient, ASGITransport
from uuid import uuid4
from decimal import Decimal
from datetime import datetime
from sqlalchemy import delete, select

from app.main import app
from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, get_password_hash
from app.modules.users.models import User, UserRole, BuyerProfile, VerificationStatus
from app.modules.registries.models import KK, CitizenRegistryMockup, VehicleRegistryMockup, VehicleClass
from app.modules.vehicles.models import VehicleOwnership, VehicleUsageType, VehicleOwnerType, VehicleQuotaMode, VehicleOwnershipStatus
from app.modules.fuels.models import FuelType, SubsidyType
from app.modules.subsidies.models import SubsidyPolicy, SubsidyQuota, KKSubsidyEligibility, EligibilityStatus

def _build_cashier_token(user_id: str) -> str:
    return create_access_token(
        subject=user_id,
        session_id=str(uuid4()),
        client_type="POS_ANDROID",
        roles=[UserRole.SALES_OFFICER.value],
        allowed_apps=["POS_ANDROID"],
    )

@pytest.mark.anyio
async def test_cashier_pricing_api():
    # Setup IDs
    kk_code = f"KK_PRC_{uuid4().hex[:6]}"
    citizen_nik = f"320202{uuid4().hex[:10]}"
    citizen_name = "Pricing Driver"
    citizen_nfc = f"NFC_PRC_{uuid4().hex[:6]}"

    async with AsyncSessionLocal() as db:
        # 1. Create KK & Citizen Registry
        kk = KK(code=kk_code)
        db.add(kk)
        await db.flush()

        citizen = CitizenRegistryMockup(
            nik=citizen_nik,
            nama=citizen_name,
            ktp_nfc_id=citizen_nfc,
            kk_id=kk.id,
            pekerjaan="DRIVER",
            penghasilan=Decimal("2000000.00"),  # Eligible for subsidy
        )
        db.add(citizen)

        # 2. Create Driver User & BuyerProfile
        driver_user = User(
            name=citizen_name,
            email=f"driver-{uuid4().hex[:6]}@example.com",
            password=get_password_hash("secret123"),
            role=[UserRole.BUYER],
            is_active=True,
        )
        db.add(driver_user)
        await db.flush()

        buyer_profile = BuyerProfile(
            user_id=driver_user.id,
            nik_snapshot=citizen_nik,
            ktp_nfc_id_snapshot=citizen_nfc,
            kk_id=kk.id,
            verification_status=VerificationStatus.VERIFIED,
            risk_score=Decimal("0.00"),
        )
        db.add(buyer_profile)

        # 3. Create Fuel Types
        from app.modules.fuels.models import FuelCategory
        subsidized_fuel = FuelType(
            name=f"Subsidized Fuel {uuid4().hex[:4]}",
            price_per_liter=Decimal("10000.00"),
            subsidy_price_per_liter=Decimal("6800.00"),
            subsidy_type=SubsidyType.SUBSIDIZED,
            category=FuelCategory.GASOLINE,
        )
        non_subsidized_fuel = FuelType(
            name=f"Market Fuel {uuid4().hex[:4]}",
            price_per_liter=Decimal("13000.00"),
            subsidy_type=SubsidyType.NON_SUBSIDIZED,
            category=FuelCategory.GASOLINE,
        )
        db.add(subsidized_fuel)
        db.add(non_subsidized_fuel)
        await db.flush()

        # 4. Create Subsidy Policy and Quota
        res_policy = await db.execute(select(SubsidyPolicy).filter(SubsidyPolicy.usage_type == VehicleUsageType.PERSONAL))
        policy = res_policy.scalars().first()
        created_policy = False
        if not policy:
            policy = SubsidyPolicy(
                name="Personal Quota Policy",
                usage_type=VehicleUsageType.PERSONAL,
                monthly_quota_liters=Decimal("40.00"),
                max_allowed_njkb=Decimal("0.00"),
                is_active=True,
            )
            db.add(policy)
            await db.flush()
            created_policy = True

        eligibility = KKSubsidyEligibility(
            kk_id=kk.id,
            subsidy_policy_id=policy.id,
            total_njkb=Decimal("0.00"),
            eligibility_status=EligibilityStatus.ELIGIBLE,
        )
        db.add(eligibility)
        await db.flush()

        # Let the service initialize or sync the quota
        from app.modules.subsidies.service import SubsidyService
        subsidy_service = SubsidyService(db)
        quota = await subsidy_service.get_or_sync_personal_quota(
            buyer_profile=buyer_profile,
            month=datetime.utcnow().month,
            year=datetime.utcnow().year,
        )
        # Dynamically set used_liters to ensure exactly 30 liters remaining
        quota.used_liters = quota.quota_liters - Decimal("30.00")
        await db.commit()
        await db.refresh(quota)

        # Create Gas Station
        from app.modules.gas_stations.models import GasStation
        gas_station = GasStation(
            name="SPBU Pricing Test",
            longitude=106.8,
            latitude=-6.2,
        )
        db.add(gas_station)
        await db.flush()

        # 5. Create Sales Officer (Cashier)
        cashier = User(
            name="Cashier Officer",
            email=f"cashier-{uuid4().hex[:6]}@sidia.id",
            password=get_password_hash("secret123"),
            role=[UserRole.SALES_OFFICER],
            is_active=True,
            gas_station_id=gas_station.id,
            shift="Morning",
            employee_id=f"EMP-{uuid4().hex[:6]}",
        )
        db.add(cashier)
        await db.commit()

        cashier_id = cashier.id
        subsidized_fuel_id = subsidized_fuel.id
        non_subsidized_fuel_id = non_subsidized_fuel.id

    # Authenticate Header Tokens
    cashier_token = _build_cashier_token(str(cashier_id))
    cashier_headers = {"Authorization": f"Bearer {cashier_token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Test Case 1: Subsidized fuel with calculation by liters within remaining quota (30L)
        res = await ac.post(
            "/api/v1/vehicle-ownerships/cashier/pricing",
            headers=cashier_headers,
            json={
                "nik": citizen_nik,
                "fuel_type_id": str(subsidized_fuel_id),
                "calc_type": "LITERS",
                "nominal": 20.0,
            }
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["account_status"] == "ACTIVE"
        assert data["price_per_liter_market"] == 10000.0
        assert data["price_per_liter_subsidy"] == 6800.0
        assert data["subsidized_liters"] == 20.0
        assert data["non_subsidized_liters"] == 0.0
        assert data["total_liters"] == 20.0
        assert data["total_amount"] == 20 * 6800

        # Test Case 2: Subsidized fuel exceeding remaining quota (30L)
        res = await ac.post(
            "/api/v1/vehicle-ownerships/cashier/pricing",
            headers=cashier_headers,
            json={
                "nik": citizen_nik,
                "fuel_type_id": str(subsidized_fuel_id),
                "calc_type": "LITERS",
                "nominal": 40.0,
            }
        )
        assert res.status_code == 200
        data = res.json()
        assert data["subsidized_liters"] == 30.0
        assert data["non_subsidized_liters"] == 10.0
        assert data["total_liters"] == 40.0
        assert data["total_amount"] == (30 * 6800) + (10 * 10000)

        # Test Case 3: Calculation by AMOUNT (Rupiah) with subsidized fuel
        res = await ac.post(
            "/api/v1/vehicle-ownerships/cashier/pricing",
            headers=cashier_headers,
            json={
                "nik": citizen_nik,
                "fuel_type_id": str(subsidized_fuel_id),
                "calc_type": "AMOUNT",
                "nominal": 300000.0,
            }
        )
        assert res.status_code == 200
        data = res.json()
        assert data["subsidized_liters"] == 30.0
        assert data["non_subsidized_liters"] == 9.6
        assert data["total_liters"] == 39.6
        assert data["total_amount"] == 300000

        # Cleanup
        async with AsyncSessionLocal() as db:
            await db.execute(delete(SubsidyQuota).where(SubsidyQuota.id == quota.id))
            await db.execute(delete(KKSubsidyEligibility).where(KKSubsidyEligibility.id == eligibility.id))
            if created_policy:
                await db.execute(delete(SubsidyPolicy).where(SubsidyPolicy.id == policy.id))
            await db.execute(delete(FuelType).where(FuelType.id.in_([subsidized_fuel_id, non_subsidized_fuel_id])))
            await db.execute(delete(BuyerProfile).where(BuyerProfile.id == buyer_profile.id))
            await db.execute(delete(User).where(User.id.in_([driver_user.id, cashier_id])))
            await db.execute(delete(CitizenRegistryMockup).where(CitizenRegistryMockup.id == citizen.id))
            await db.execute(delete(KK).where(KK.id == kk.id))
            await db.execute(delete(GasStation).where(GasStation.id == gas_station.id))
            await db.commit()
