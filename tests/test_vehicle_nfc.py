import pytest
from httpx import AsyncClient, ASGITransport
from uuid import uuid4
from decimal import Decimal
from datetime import datetime
from sqlalchemy import delete

from app.main import app
from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, get_password_hash
from app.modules.users.models import User, UserRole, BuyerProfile, VerificationStatus
from app.modules.registries.models import KK, CitizenRegistryMockup, VehicleRegistryMockup, VehicleClass
from app.modules.vehicles.models import VehicleOwnership, VehicleUsageType, VehicleOwnerType, VehicleQuotaMode, VehicleOwnershipStatus
from app.modules.companies.models import Company

def _build_company_admin_token(user_id: str) -> str:
    return create_access_token(
        subject=user_id,
        session_id=str(uuid4()),
        client_type="PORTAL_WEB",
        roles=[UserRole.COMPANY_ADMIN.value],
        allowed_apps=["PORTAL_WEB"],
    )

def _build_cashier_token(user_id: str) -> str:
    return create_access_token(
        subject=user_id,
        session_id=str(uuid4()),
        client_type="POS_ANDROID",
        roles=[UserRole.SALES_OFFICER.value],
        allowed_apps=["POS_ANDROID"],
    )

@pytest.mark.anyio
async def test_vehicle_nfc_flow():
    # Setup IDs
    kk_code = f"KK_NFC_{uuid4().hex[:6]}"
    citizen_nik = f"320101{uuid4().hex[:10]}"
    citizen_name = "Commercial Driver"
    citizen_nfc = f"NFC_DRV_{uuid4().hex[:6]}"
    
    vehicle_plate = f"B {uuid4().hex[:4].upper()} NFC"
    vehicle_reg = f"STNK_{uuid4().hex[:8]}"
    vehicle_nfc = f"NFC_VEH_{uuid4().hex[:6]}"

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
            penghasilan=Decimal("4500000.00"),
        )
        db.add(citizen)

        # 2. Create Police Vehicle Registry
        vehicle_reg_mock = VehicleRegistryMockup(
            plate_number=vehicle_plate,
            registration_number=vehicle_reg,
            brand="Hino",
            vehicle_type="Truck",
            jenis=VehicleClass.TRUCK,
            vehicle_nfc_id=None,
        )
        db.add(vehicle_reg_mock)

        # 3. Create Company
        company = Company(
            name=f"Logistics Co {uuid4().hex[:4]}",
            siup_no=f"SIUP-{uuid4().hex[:5]}",
            nib=f"NIB-{uuid4().hex[:5]}",
            npwp_no=f"NPWP-{uuid4().hex[:5]}",
            status="Approved",
        )
        db.add(company)
        await db.flush()

        # 4. Create Driver User & BuyerProfile
        driver_user = User(
            name=citizen_name,
            email=f"driver-{uuid4().hex[:6]}@example.com",
            password=get_password_hash("secret123"),
            role=[UserRole.BUYER],
            is_active=True,
            shift="Morning",
            employee_id=f"EMP-{uuid4().hex[:6]}",
            company_id=company.id,
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


        company_admin = User(
            name="Company Admin",
            email=f"admin-{uuid4().hex[:6]}@company.com",
            password=get_password_hash("secret123"),
            role=[UserRole.COMPANY_ADMIN],
            is_active=True,
            company_id=company.id,
            shift="Morning",
            employee_id=f"EMP-{uuid4().hex[:6]}",
        )
        db.add(company_admin)

        # Create Gas Station
        from app.modules.gas_stations.models import GasStation
        gas_station = GasStation(
            name="SPBU Test",
            longitude=106.8,
            latitude=-6.2,
        )
        db.add(gas_station)
        await db.commit()
        await db.refresh(gas_station)

        # 5. Create Sales Officer (Cashier)
        cashier = User(
            name="Cashier Officer",
            email=f"cashier-{uuid4().hex[:6]}@mysuf.id",
            password=get_password_hash("secret123"),
            role=[UserRole.SALES_OFFICER],
            is_active=True,
            gas_station_id=gas_station.id,
            shift="Morning",
            employee_id=f"EMP-{uuid4().hex[:6]}",
        )
        db.add(cashier)

        await db.commit()

        admin_id = company_admin.id
        cashier_id = cashier.id
        driver_user_id = driver_user.id
        vehicle_registry_id = vehicle_reg_mock.id
        gas_station_id = gas_station.id

    # Authenticate Header Tokens
    admin_token = _build_company_admin_token(str(admin_id))
    cashier_token = _build_cashier_token(str(cashier_id))
    
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    cashier_headers = {"Authorization": f"Bearer {cashier_token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # ----------------------------------------------------
        # Test Case A: Register Fleet Vehicle with Duplicate NFC ID (Bentrok dengan KTP driver)
        # ----------------------------------------------------
        res = await ac.post(
            "/api/v1/fleet/vehicles",
            headers=admin_headers,
            json={"plate": vehicle_plate, "vehicle_nfc_id": citizen_nfc}, # bentrok!
        )
        assert res.status_code == 400
        assert "sudah terdaftar" in res.json()["detail"]

        # ----------------------------------------------------
        # Test Case B: Register Fleet Vehicle with Valid Unique NFC ID
        # ----------------------------------------------------
        res = await ac.post(
            "/api/v1/fleet/vehicles",
            headers=admin_headers,
            json={"plate": vehicle_plate, "vehicle_nfc_id": vehicle_nfc},
        )
        assert res.status_code == 200
        vehicle_data = res.json()
        assert vehicle_data["vehicle_nfc_id"] == vehicle_nfc
        ownership_id = vehicle_data["id"]

        # ----------------------------------------------------
        # Test Case C: Assign Driver to the vehicle
        # ----------------------------------------------------
        res = await ac.put(
            f"/api/v1/fleet/vehicles/{ownership_id}/assign-driver",
            headers=admin_headers,
            json={"driver_id": str(driver_user_id)},
        )
        assert res.status_code == 200, f"Failed at Test Case C: {res.status_code} - {res.text} (URL: {res.url})"

        # Execute lookup in Cashier API using Vehicle's NFC Card ID
        res = await ac.get(
            f"/api/v1/vehicle-ownerships/cashier/by-nfc/{vehicle_nfc}",
            headers=cashier_headers,
        )
        assert res.status_code == 200
        res_data = res.json()
        assert res_data["buyer"]["name"] == citizen_name
        assert res_data["buyer"]["nik_snapshot"] == citizen_nik
        assert len(res_data["vehicles"]) == 1
        assert res_data["vehicles"][0]["plate_number"] == vehicle_plate

        # ----------------------------------------------------
        # Test Case E: Cross-table Check - Try to register citizen with NFC that belongs to a vehicle
        # ----------------------------------------------------
        res = await ac.post(
            "/api/v1/registries/citizens",
            json={
                "nik": f"320101{uuid4().hex[:10]}",
                "nama": "Duplicate NFC Citizen",
                "ktp_nfc_id": vehicle_nfc, # bentrok dengan nfc kendaraan!
                "kk_id": str(kk.id),
            }
        )
        assert res.status_code == 400
        assert "sudah terdaftar" in res.json()["detail"]

    # Cleanup DB
    async with AsyncSessionLocal() as db:
        from app.modules.gas_stations.models import GasStation
        from app.modules.transactions.models import CashierScanEvent
        await db.execute(delete(VehicleOwnership).filter(VehicleOwnership.id == ownership_id))
        await db.execute(delete(CashierScanEvent).filter(CashierScanEvent.cashier_user_id == cashier_id))
        await db.execute(delete(BuyerProfile).filter(BuyerProfile.user_id == driver_user_id))
        await db.execute(delete(User).filter(User.id.in_([admin_id, cashier_id, driver_user_id])))
        await db.execute(delete(GasStation).filter(GasStation.id == gas_station_id))
        await db.execute(delete(Company).filter(Company.id == company.id))
        await db.execute(delete(CitizenRegistryMockup).filter(CitizenRegistryMockup.nik == citizen_nik))
        await db.execute(delete(VehicleRegistryMockup).filter(VehicleRegistryMockup.id == vehicle_registry_id))
        await db.execute(delete(KK).filter(KK.id == kk.id))
        await db.commit()
