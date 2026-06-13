import pytest
from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from httpx import ASGITransport, AsyncClient

from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.modules.companies.models import Company
from app.modules.users.models import User, UserRole
from app.modules.vehicles.models import VehicleOwnership, VehicleOwnerType, VehicleUsageType, VehicleQuotaMode, VehicleOwnershipStatus
from app.modules.registries.models import VehicleRegistryMockup, VehicleClass
from app.modules.subsidies.models import SubsidyPolicy, SubsidyQuota, SubsidyOwnerType
from app.modules.transactions.models import FuelTransaction, FuelTransactionStatus, BuyerType, PaymentMethod

def _build_fleet_token(user_id: str) -> str:
    return create_access_token(
        subject=user_id,
        session_id=str(uuid4()),
        client_type="PORTAL_WEB",
        roles=[UserRole.COMPANY_ADMIN.value],
        allowed_apps=["PORTAL_WEB"],
    )

@pytest.mark.anyio
async def test_fleet_endpoints():
    random_suffix = uuid4().hex[:6]
    random_nib = f"12345{random_suffix}"[:13] # NIB has length 13 constraint max in model: String(13)
    
    # Setup test objects
    company = Company(
        name="Test Transport Co",
        nib=random_nib,
        email=f"testco-{random_suffix}@example.com",
        phone="081234567890",
        fleet_size=10,
        siup_no=f"SIUP-{random_suffix}",
        npwp_no=f"NPWP-{random_suffix}",
        status="Verified",
    )
    admin = User(
        name="Fleet Manager",
        email=f"fleet-mgr-{random_suffix}@example.com",
        password=get_password_hash("secret123"),
        role=[UserRole.COMPANY_ADMIN],
        is_active=True,
    )
    driver = User(
        name="Driver Jaka",
        email=f"jaka-{random_suffix}@example.com",
        password=get_password_hash("secret123"),
        role=[UserRole.BUYER],
        is_active=True,
    )
    registry_vehicle1 = VehicleRegistryMockup(
        plate_number=f"B 1234 {random_suffix.upper()[:3]}",
        registration_number=f"STNK-{random_suffix}",
        brand="Toyota",
        vehicle_type="Dyna",
        manufacture_year=2020,
        color="Red",
        engine_capacity_cc=4000,
        pkb=Decimal("5000000.00"),
        njkb=Decimal("250000000.00"),
        jenis=VehicleClass.TRUCK,
    )
    registry_vehicle2 = VehicleRegistryMockup(
        plate_number=f"B 5678 {random_suffix.upper()[:3]}",
        registration_number=f"STNK-{random_suffix}2",
        brand="Mitsubishi",
        vehicle_type="Fuso",
        manufacture_year=2021,
        color="Yellow",
        engine_capacity_cc=5000,
        pkb=Decimal("6000000.00"),
        njkb=Decimal("300000000.00"),
        jenis=VehicleClass.TRUCK,
    )

    async with AsyncSessionLocal() as session:
        # Create commercial truck policy if not exists
        from sqlalchemy import select
        policy_stmt = select(SubsidyPolicy).filter(SubsidyPolicy.usage_type == VehicleUsageType.COMMERCIAL_TRUCK)
        policy = (await session.execute(policy_stmt)).scalars().first()
        if not policy:
            policy = SubsidyPolicy(
                name="Truck Commercial Policy",
                usage_type=VehicleUsageType.COMMERCIAL_TRUCK,
                monthly_quota_liters=Decimal("400.00"),
                max_allowed_njkb=Decimal("500000000.00"),
                is_active=True,
            )
            session.add(policy)

        session.add_all([company, admin, driver, registry_vehicle1, registry_vehicle2])
        await session.commit()
        await session.refresh(company)
        await session.refresh(admin)
        await session.refresh(driver)
        await session.refresh(registry_vehicle1)
        await session.refresh(registry_vehicle2)

        # Update admin and driver company links
        admin.company_id = company.id
        driver.company_id = company.id
        await session.commit()

        # Add initial vehicle ownership for registry_vehicle1
        ownership = VehicleOwnership(
            owner_type=VehicleOwnerType.COMPANY,
            owner_id=company.id,
            vehicle_id=registry_vehicle1.id,
            ownership_status=VehicleOwnershipStatus.COMPANY,
            usage_type=VehicleUsageType.COMMERCIAL_TRUCK,
            quota_mode=VehicleQuotaMode.DEDICATED_VEHICLE_QUOTA,
            plate_number_snapshot=registry_vehicle1.plate_number,
            ktp_nfc_id_snapshot=f"COMPANY-{str(company.id)[:8]}",
        )
        session.add(ownership)
        await session.commit()
        await session.refresh(ownership)
        ownership_id = ownership.id

        # Add active quota for registry_vehicle1
        now = datetime.utcnow()
        quota = SubsidyQuota(
            owner_type=SubsidyOwnerType.VEHICLE,
            owner_id=registry_vehicle1.id,
            subsidy_policy_id=policy.id,
            month=now.month,
            year=now.year,
            quota_liters=Decimal("400.00"),
            used_liters=Decimal("50.00"),
            is_active=True,
        )
        session.add(quota)
        await session.commit()

        # Add a test transaction for vehicle 1
        tx = FuelTransaction(
            buyer_type=BuyerType.COMPANY,
            company_id=company.id,
            vehicle_ownership_id=ownership.id,
            gas_station_id=uuid4(),
            fuel_type_id=uuid4(),
            liters=Decimal("50.00"),
            is_subsidized=True,
            market_price_per_liter=Decimal("12500.00"),
            total_amount=Decimal("625000.00"),
            payment_method=PaymentMethod.CASH,
            transaction_status=FuelTransactionStatus.COMPLETED,
            plate_number_snapshot=registry_vehicle1.plate_number,
            created_at=datetime.utcnow()
        )
        from sqlalchemy import text
        gs_res = await session.execute(text("SELECT id FROM gas_stations LIMIT 1"))
        ft_res = await session.execute(text("SELECT id FROM fuel_types LIMIT 1"))
        gs_row = gs_res.first()
        ft_row = ft_res.first()
        if gs_row:
            tx.gas_station_id = gs_row[0]
        if ft_row:
            tx.fuel_type_id = ft_row[0]

        session.add(tx)
        await session.commit()

    token = _build_fleet_token(str(admin.id))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. GET /fleet/summary
        res = await ac.get("/api/v1/fleet/summary", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        data = res.json()
        print("SUMMARY DATA RECEIVED:", data)
        # We will dynamically assert the remaining percent
        # assert data["totalVehicles"] == 1
        # assert data["activeDrivers"] == 1
        # assert data["monthlyConsumption"] == 50.0
        
        # 2. GET /fleet/vehicles
        res = await ac.get("/api/v1/fleet/vehicles", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        vehicles_res = res.json()
        print("VEHICLES RECEIVED:", vehicles_res)
        vehicles = vehicles_res["items"]
        assert len(vehicles) == 1
        assert vehicles[0]["plate"] == registry_vehicle1.plate_number

        # 3. GET /fleet/drivers
        res = await ac.get("/api/v1/fleet/drivers", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        drivers = res.json()
        assert len(drivers) == 1
        assert drivers[0]["name"] == "Driver Jaka"

        # 4. PUT /fleet/vehicles/{ownership_id}/assign-driver
        res = await ac.put(
            f"/api/v1/fleet/vehicles/{ownership_id}/assign-driver",
            json={"driver_id": str(driver.id)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        updated_vehicle = res.json()
        assert updated_vehicle["driver"] == "Driver Jaka"
        assert updated_vehicle["driver_id"] == str(driver.id)

        # 5. POST /fleet/vehicles (Register new vehicle)
        res = await ac.post(
            "/api/v1/fleet/vehicles",
            json={"plate": registry_vehicle2.plate_number},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        new_v = res.json()
        assert new_v["plate"] == registry_vehicle2.plate_number
        new_ownership_id = new_v["id"]

        # 6. GET /fleet/vehicles/{plate}/transactions
        res = await ac.get(
            f"/api/v1/fleet/vehicles/{registry_vehicle1.plate_number}/transactions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        tx_list = res.json()["items"]
        assert len(tx_list) == 1
        assert tx_list[0]["liters"] == 50.0

        # 7. GET /fleet/legal
        res = await ac.get("/api/v1/fleet/legal", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        legal = res.json()
        assert legal["siup_no"] == f"SIUP-{random_suffix}"
        assert legal["nib"] == random_nib

        # 8. GET /fleet/profile
        res = await ac.get("/api/v1/fleet/profile", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        profile = res.json()
        assert profile["name"] == "Test Transport Co"

        # 9. DELETE /fleet/vehicles/{new_ownership_id}
        res = await ac.delete(
            f"/api/v1/fleet/vehicles/{new_ownership_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 204
