import pytest
from httpx import AsyncClient, ASGITransport
from uuid import uuid4
from sqlalchemy import delete

from app.main import app
from app.core.database import AsyncSessionLocal
from app.modules.users.models import User, UserRole
from app.modules.gas_stations.models import GasStation
from app.core.security import get_password_hash, create_access_token

@pytest.mark.anyio
async def test_spbu_staff_crud_api():
    # 1. Setup mock resources
    station_a_id = uuid4()
    station_b_id = uuid4()
    
    admin_a_id = uuid4()
    admin_b_id = uuid4()
    
    staff_a_id = uuid4()
    staff_b_id = uuid4()
    
    new_staff_id = None
    
    async with AsyncSessionLocal() as session:
        # Create Gas Stations
        station_a = GasStation(id=station_a_id, name="SPBU Station A", latitude=-6.29, longitude=106.79)
        station_b = GasStation(id=station_b_id, name="SPBU Station B", latitude=-6.30, longitude=106.80)
        session.add_all([station_a, station_b])
        
        # Create SPBU Admins
        admin_a = User(
            id=admin_a_id,
            name="Admin Station A",
            email=f"admin-a-{uuid4().hex[:6]}@example.com",
            password=get_password_hash("password123"),
            role=[UserRole.SPBU_ADMIN],
            gas_station_id=station_a_id,
            is_active=True
        )
        admin_b = User(
            id=admin_b_id,
            name="Admin Station B",
            email=f"admin-b-{uuid4().hex[:6]}@example.com",
            password=get_password_hash("password123"),
            role=[UserRole.SPBU_ADMIN],
            gas_station_id=station_b_id,
            is_active=True
        )
        
        # Create Staff members
        staff_a = User(
            id=staff_a_id,
            name="Cashier A",
            email=f"cashier-a-{uuid4().hex[:6]}@example.com",
            password=get_password_hash("password123"),
            role=[UserRole.SALES_OFFICER],
            gas_station_id=station_a_id,
            shift="Morning (06:00 - 14:00)",
            is_active=True
        )
        staff_b = User(
            id=staff_b_id,
            name="Cashier B",
            email=f"cashier-b-{uuid4().hex[:6]}@example.com",
            password=get_password_hash("password123"),
            role=[UserRole.SALES_OFFICER],
            gas_station_id=station_b_id,
            shift="Afternoon (14:00 - 22:00)",
            is_active=True
        )
        
        session.add_all([admin_a, admin_b, staff_a, staff_b])
        await session.commit()

    # Generate Auth Tokens
    token_admin_a = create_access_token(
        subject=admin_a_id,
        session_id=str(uuid4()),
        client_type="DASHBOARD",
        roles=["SPBU_ADMIN"],
        allowed_apps=["DASHBOARD"]
    )
    token_cashier_a = create_access_token(
        subject=staff_a_id,
        session_id=str(uuid4()),
        client_type="APP",
        roles=["SALES_OFFICER"],
        allowed_apps=["CASHIER"]
    )
    
    headers_admin_a = {"Authorization": f"Bearer {token_admin_a}"}
    headers_cashier_a = {"Authorization": f"Bearer {token_cashier_a}"}

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Test 1: Restrict access for non-admins
            res = await ac.get("/api/v1/spbu/staff", headers=headers_cashier_a)
            assert res.status_code == 403

            # Test 2: Admin A list staff members (should see Admin A and Cashier A, not Admin B or Cashier B)
            res = await ac.get("/api/v1/spbu/staff", headers=headers_admin_a)
            assert res.status_code == 200
            data = res.json()
            assert len(data) == 2
            
            emails = [u["email"] for u in data]
            assert any(e.startswith("admin-a-") for e in emails)
            assert any(e.startswith("cashier-a-") for e in emails)
            assert not any(e.startswith("admin-b-") for e in emails)
            assert not any(e.startswith("cashier-b-") for e in emails)

            # Test 3: Admin A creates a new staff member at Station A
            new_staff_email = f"new-cashier-{uuid4().hex[:6]}@example.com"
            payload = {
                "name": "New Cashier A",
                "email": new_staff_email,
                "password": "newpassword123",
                "role": ["SALES_OFFICER"],
                "shift": "Night (22:00 - 06:00)",
                "is_active": True
            }
            res = await ac.post("/api/v1/spbu/staff", json=payload, headers=headers_admin_a)
            assert res.status_code == 201
            new_staff_data = res.json()
            new_staff_id = new_staff_data["id"]
            assert new_staff_data["name"] == "New Cashier A"
            assert new_staff_data["shift"] == "Night (22:00 - 06:00)"
            
            # Test 4: Admin A updates staff A (e.g. status/shift)
            update_payload = {
                "name": "Cashier A Updated",
                "shift": "Afternoon (14:00 - 22:00)",
                "is_active": False
            }
            res = await ac.put(f"/api/v1/spbu/staff/{staff_a_id}", json=update_payload, headers=headers_admin_a)
            assert res.status_code == 200
            updated_data = res.json()
            assert updated_data["name"] == "Cashier A Updated"
            assert updated_data["shift"] == "Afternoon (14:00 - 22:00)"
            assert updated_data["is_active"] is False

            # Test 5: Admin A attempts to update staff B (should fail with 403)
            res = await ac.put(f"/api/v1/spbu/staff/{staff_b_id}", json=update_payload, headers=headers_admin_a)
            assert res.status_code == 403

            # Test 6: Admin A attempts to delete staff B (should fail with 403)
            res = await ac.delete(f"/api/v1/spbu/staff/{staff_b_id}", headers=headers_admin_a)
            assert res.status_code == 403

            # Test 7: Admin A deletes staff A
            res = await ac.delete(f"/api/v1/spbu/staff/{staff_a_id}", headers=headers_admin_a)
            assert res.status_code == 204

    finally:
        # Cleanup
        async with AsyncSessionLocal() as session:
            ids_to_delete = [admin_a_id, admin_b_id, staff_a_id, staff_b_id]
            if new_staff_id:
                ids_to_delete.append(new_staff_id)
            await session.execute(delete(User).where(User.id.in_(ids_to_delete)))
            await session.execute(delete(GasStation).where(GasStation.id.in_([station_a_id, station_b_id])))
            await session.commit()
