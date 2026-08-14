import pytest
from httpx import AsyncClient, ASGITransport
from uuid import uuid4
from sqlalchemy import delete
from datetime import datetime

from app.main import app
from app.core.database import AsyncSessionLocal
from app.modules.users.models import User, UserRole
from app.modules.gas_stations.models import GasStation
from app.modules.spbu_activities.models import SpbuActivityLog, SpbuActivityCategory
from app.core.security import get_password_hash, create_access_token

@pytest.mark.anyio
async def test_spbu_activity_logs_api():
    # 1. Setup mock resources
    spbu_admin_id = uuid4()
    station_id = uuid4()

    async with AsyncSessionLocal() as session:
        # Create Station
        station = GasStation(
            id=station_id,
            name="Activity SPBU Stasiun",
            latitude=-6.290000,
            longitude=106.790000
        )
        session.add(station)

        # Create SPBU Admin User
        spbu_admin = User(
            id=spbu_admin_id,
            name="Activity Logger Admin",
            email=f"spbu-act-{uuid4().hex[:8]}@example.com",
            password=get_password_hash("password123"),
            role=[UserRole.SPBU_ADMIN],
            gas_station_id=station_id,
            is_active=True
        )
        session.add(spbu_admin)
        await session.commit()

    # Generate Auth Token
    spbu_token = create_access_token(
        subject=spbu_admin_id,
        session_id=str(uuid4()),
        client_type="DASHBOARD",
        roles=["SPBU_ADMIN"],
        allowed_apps=["DASHBOARD"]
    )
    headers_spbu = {"Authorization": f"Bearer {spbu_token}"}

    try:
        from datetime import timedelta
        async with AsyncSessionLocal() as session:
            mock_data = [
                (SpbuActivityCategory.Keamanan, "Fraud alert ditandai untuk Plat D 9012 DEF.", 10),
                (SpbuActivityCategory.Sistem, "Pergantian shift berhasil diverifikasi otomatis oleh AI Engine.", 25),
                (SpbuActivityCategory.Penjualan, "Audit stok tangki solar bawah tanah selesai. Kapasitas: 85%.", 50),
                (SpbuActivityCategory.Keamanan, "Tindakan cepat diambil terhadap Plat B 9123 KZ. Kasus diselesaikan.", 75),
                (SpbuActivityCategory.Penjualan, "Penjualan Solar Subsidi mencapai batas kuota harian wilayah (Nozzle 03).", 165),
                (SpbuActivityCategory.Sistem, "Sistem SUBSIDIA sinkronisasi data dengan server BPH Migas berhasil.", 240)
            ]
            now = datetime.utcnow()
            for cat, detail, minutes_ago in mock_data:
                log_entry = SpbuActivityLog(
                    gas_station_id=station_id,
                    category=cat,
                    detail=detail,
                    created_at=now - timedelta(minutes=minutes_ago)
                )
                session.add(log_entry)
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Test 1: Fetch activity logs
            res = await ac.get("/api/v1/spbu/activity", headers=headers_spbu)

            assert res.status_code == 200
            data = res.json()
            assert data["total"] == 6
            assert len(data["items"]) == 6

            # Verify that one of the seeded logs exists
            details = [item["detail"] for item in data["items"]]
            assert "Sistem SUBSIDIA sinkronisasi data dengan server BPH Migas berhasil." in details

            # Test 2: Filter by category = Keamanan (should return 2 items)
            res_keamanan = await ac.get("/api/v1/spbu/activity?category=Keamanan", headers=headers_spbu)
            assert res_keamanan.status_code == 200
            data_keamanan = res_keamanan.json()
            assert data_keamanan["total"] == 2
            assert all(item["category"] == "Keamanan" for item in data_keamanan["items"])

            # Test 3: Search filter
            res_search = await ac.get("/api/v1/spbu/activity?search=BPH%20Migas", headers=headers_spbu)
            assert res_search.status_code == 200
            data_search = res_search.json()
            assert data_search["total"] == 1
            assert "BPH Migas" in data_search["items"][0]["detail"]

    finally:
        # Cleanup
        async with AsyncSessionLocal() as session:
            await session.execute(delete(SpbuActivityLog).where(SpbuActivityLog.gas_station_id == station_id))
            await session.execute(delete(User).where(User.id == spbu_admin_id))
            await session.execute(delete(GasStation).where(GasStation.id == station_id))
            await session.commit()
