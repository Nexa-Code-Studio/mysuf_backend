import pytest
from httpx import AsyncClient, ASGITransport
from uuid import uuid4
from sqlalchemy import delete
from decimal import Decimal

from app.main import app
from app.core.database import AsyncSessionLocal
from app.modules.registries.models import KK, CitizenRegistryMockup, VehicleRegistryMockup

@pytest.mark.anyio
async def test_registries_crud_flow():
    # Setup test IDs and codes
    kk_code = f"KK_TEST_{uuid4().hex[:8]}"
    kk_code_updated = f"KK_TEST_{uuid4().hex[:8]}_UPD"
    
    citizen_nik = f"NIK_TEST_{uuid4().hex[:8]}"
    citizen_nik_updated = f"NIK_TEST_{uuid4().hex[:8]}_UPD"
    citizen_name = "Ahmad Test"
    citizen_nfc = f"NFC_TEST_{uuid4().hex[:8]}"
    
    vehicle_plate = f"B {uuid4().hex[:4].upper()} TST"
    vehicle_reg = f"STNK_TEST_{uuid4().hex[:8]}"
    vehicle_reg_updated = f"STNK_TEST_{uuid4().hex[:8]}_UPD"
    
    kk_id = None
    citizen_id = None
    vehicle_id = None

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # ----------------------------------------------------
            # 1. KK CRUD Tests
            # ----------------------------------------------------
            # Create KK
            res = await ac.post("/api/v1/registries/kk", json={"code": kk_code})
            assert res.status_code == 201
            kk_data = res.json()
            assert kk_data["code"] == kk_code
            assert "id" in kk_data
            kk_id = kk_data["id"]

            # Create KK (duplicate check)
            res = await ac.post("/api/v1/registries/kk", json={"code": kk_code})
            assert res.status_code == 400

            # List KKs
            res = await ac.get("/api/v1/registries/kk")
            assert res.status_code == 200
            list_data = res.json()
            assert "items" in list_data
            assert "pagination" in list_data
            assert any(item["id"] == kk_id for item in list_data["items"])

            # Read KK
            res = await ac.get(f"/api/v1/registries/kk/{kk_id}")
            assert res.status_code == 200
            assert res.json()["code"] == kk_code

            # Update KK
            res = await ac.put(f"/api/v1/registries/kk/{kk_id}", json={"code": kk_code_updated})
            assert res.status_code == 200
            assert res.json()["code"] == kk_code_updated

            # ----------------------------------------------------
            # 2. Citizen CRUD Tests
            # ----------------------------------------------------
            # Create Citizen (invalid KK ID)
            res = await ac.post("/api/v1/registries/citizens", json={
                "nik": citizen_nik,
                "nama": citizen_name,
                "ktp_nfc_id": citizen_nfc,
                "kk_id": str(uuid4())
            })
            assert res.status_code == 400

            # Create Citizen (valid KK ID)
            res = await ac.post("/api/v1/registries/citizens", json={
                "nik": citizen_nik,
                "nama": citizen_name,
                "ktp_nfc_id": citizen_nfc,
                "kk_id": kk_id
            })
            assert res.status_code == 201
            cit_data = res.json()
            assert cit_data["nik"] == citizen_nik
            assert cit_data["nama"] == citizen_name
            assert cit_data["ktp_nfc_id"] == citizen_nfc
            assert cit_data["kk_id"] == kk_id
            citizen_id = cit_data["id"]

            # Create Citizen (duplicate NIK)
            res = await ac.post("/api/v1/registries/citizens", json={
                "nik": citizen_nik,
                "nama": "Another Name",
                "ktp_nfc_id": f"NFC_{uuid4().hex[:8]}",
                "kk_id": kk_id
            })
            assert res.status_code == 400

            # Read Citizen
            res = await ac.get(f"/api/v1/registries/citizens/{citizen_id}")
            assert res.status_code == 200
            assert res.json()["nik"] == citizen_nik

            # Update Citizen
            res = await ac.put(f"/api/v1/registries/citizens/{citizen_id}", json={
                "nik": citizen_nik_updated,
                "nama": "Ahmad Test Updated"
            })
            assert res.status_code == 200
            assert res.json()["nik"] == citizen_nik_updated
            assert res.json()["nama"] == "Ahmad Test Updated"

            # ----------------------------------------------------
            # 3. Vehicle CRUD Tests
            # ----------------------------------------------------
            # Create Vehicle
            res = await ac.post("/api/v1/registries/vehicles", json={
                "plate_number": vehicle_plate,
                "registration_number": vehicle_reg,
                "brand": "Toyota",
                "vehicle_type": "Camry",
                "manufacture_year": 2022,
                "color": "Hitam",
                "engine_capacity_cc": 2494,
                "pkb": "3500000.00",
                "njkb": "450000000.00",
                "owner_name": "Ahmad Test Updated",
                "owner_nik": citizen_nik_updated
            })
            assert res.status_code == 201
            veh_data = res.json()
            assert veh_data["plate_number"] == vehicle_plate
            assert veh_data["registration_number"] == vehicle_reg
            assert veh_data["brand"] == "Toyota"
            assert Decimal(veh_data["pkb"]) == Decimal("3500000.00")
            vehicle_id = veh_data["id"]

            # Create Vehicle (duplicate registration number check)
            res = await ac.post("/api/v1/registries/vehicles", json={
                "plate_number": f"B {uuid4().hex[:4].upper()} TST",
                "registration_number": vehicle_reg,
                "brand": "Honda",
                "vehicle_type": "Civic",
                "manufacture_year": 2021,
                "color": "Putih",
                "engine_capacity_cc": 1498,
                "pkb": "2500000.00",
                "njkb": "350000000.00"
            })
            assert res.status_code == 400

            # Read Vehicle
            res = await ac.get(f"/api/v1/registries/vehicles/{vehicle_id}")
            assert res.status_code == 200
            assert res.json()["plate_number"] == vehicle_plate

            # Update Vehicle
            res = await ac.put(f"/api/v1/registries/vehicles/{vehicle_id}", json={
                "registration_number": vehicle_reg_updated,
                "color": "Silver"
            })
            assert res.status_code == 200
            assert res.json()["registration_number"] == vehicle_reg_updated
            assert res.json()["color"] == "Silver"

            # ----------------------------------------------------
            # 4. Deletions
            # ----------------------------------------------------
            # Delete Citizen
            res = await ac.delete(f"/api/v1/registries/citizens/{citizen_id}")
            assert res.status_code == 204
            # Verify deleted
            res = await ac.get(f"/api/v1/registries/citizens/{citizen_id}")
            assert res.status_code == 404

            # Delete Vehicle
            res = await ac.delete(f"/api/v1/registries/vehicles/{vehicle_id}")
            assert res.status_code == 204
            # Verify deleted
            res = await ac.get(f"/api/v1/registries/vehicles/{vehicle_id}")
            assert res.status_code == 404

            # Delete KK
            res = await ac.delete(f"/api/v1/registries/kk/{kk_id}")
            assert res.status_code == 204
            # Verify deleted
            res = await ac.get(f"/api/v1/registries/kk/{kk_id}")
            assert res.status_code == 404

    finally:
        # DB cleanup in case of failures during assertion
        async with AsyncSessionLocal() as session:
            if citizen_id:
                await session.execute(delete(CitizenRegistryMockup).where(CitizenRegistryMockup.id == citizen_id))
            if vehicle_id:
                await session.execute(delete(VehicleRegistryMockup).where(VehicleRegistryMockup.id == vehicle_id))
            if kk_id:
                await session.execute(delete(KK).where(KK.id == kk_id))
            await session.commit()
