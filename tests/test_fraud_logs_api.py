import pytest
from httpx import AsyncClient, ASGITransport
from uuid import uuid4, UUID
from sqlalchemy import delete
from sqlalchemy.future import select
from datetime import datetime

from app.main import app
from app.core.database import AsyncSessionLocal
from app.modules.users.models import User, UserRole, BuyerProfile, VerificationStatus
from app.modules.gas_stations.models import GasStation
from app.modules.registries.models import KK
from app.modules.transactions.models import FraudLog, FraudRiskLevel, FraudActionTaken, FraudCaseStatus
from app.core.security import get_password_hash, create_access_token

@pytest.mark.anyio
async def test_fraud_logs_api_scoping_and_updates():
    # 1. Setup mock resources
    gov_admin_id = uuid4()
    spbu1_admin_id = uuid4()
    spbu2_admin_id = uuid4()
    buyer_user_id = uuid4()
    
    station1_id = uuid4()
    station2_id = uuid4()
    kk_id = uuid4()
    
    async with AsyncSessionLocal() as session:
        # Create KK
        kk = KK(
            id=kk_id,
            code=f"KK-FRAUD-{uuid4().hex[:8]}"
        )
        session.add(kk)

        # Create Stations
        station1 = GasStation(
            id=station1_id,
            name="Test SPBU Kebon Jeruk",
            latitude=-6.190000,
            longitude=106.780000
        )
        station2 = GasStation(
            id=station2_id,
            name="Test SPBU Kuningan",
            latitude=-6.220000,
            longitude=106.830000
        )
        session.add_all([station1, station2])
        
        # Create Users
        gov_admin = User(
            id=gov_admin_id,
            name="Gov Administrator",
            email=f"gov-{uuid4().hex[:8]}@example.com",
            password=get_password_hash("password123"),
            role=[UserRole.GOV_ADMIN],
            is_active=True
        )
        spbu1_admin = User(
            id=spbu1_admin_id,
            name="Kebon Jeruk Admin",
            email=f"spbu1-{uuid4().hex[:8]}@example.com",
            password=get_password_hash("password123"),
            role=[UserRole.SPBU_ADMIN],
            gas_station_id=station1_id,
            is_active=True
        )
        spbu2_admin = User(
            id=spbu2_admin_id,
            name="Kuningan Admin",
            email=f"spbu2-{uuid4().hex[:8]}@example.com",
            password=get_password_hash("password123"),
            role=[UserRole.SPBU_ADMIN],
            gas_station_id=station2_id,
            is_active=True
        )
        buyer_user = User(
            id=buyer_user_id,
            name="John Suspicious",
            email=f"buyer-{uuid4().hex[:8]}@example.com",
            password=get_password_hash("password123"),
            role=[UserRole.BUYER],
            is_active=True
        )
        session.add_all([gov_admin, spbu1_admin, spbu2_admin, buyer_user])
        
        # Create Buyer Profile
        buyer_profile = BuyerProfile(
            id=uuid4(),
            nik_snapshot="3171998877665544",
            ktp_nfc_id_snapshot=f"NFC-{uuid4().hex[:8]}",
            user_id=buyer_user_id,
            kk_id=kk_id,
            verification_status=VerificationStatus.VERIFIED,
            risk_score=45.00
        )
        session.add(buyer_profile)
        await session.commit()
        await session.refresh(buyer_profile)
        
        # Create 3 Fraud Logs: 2 for Station 1, 1 for Station 2
        log1 = FraudLog(
            id=uuid4(),
            case_id=f"FR-{datetime.utcnow().strftime('%y%m%d')}-{uuid4().hex[:4].upper()}",
            gas_station_id=station1_id,
            buyer_profile_id=buyer_profile.id,
            plate_number_snapshot="B 1234 ABC",
            nik_snapshot="3171998877665544",
            risk_score=40,
            risk_level=FraudRiskLevel.SUSPICIOUS,
            action_taken=FraudActionTaken.WARNING,
            detected_frauds=[{"type": "RAPID_PURCHASE", "points": 40}],
            status=FraudCaseStatus.PENDING,
            created_at=datetime.utcnow()
        )
        log2 = FraudLog(
            id=uuid4(),
            case_id=f"FR-{datetime.utcnow().strftime('%y%m%d')}-{uuid4().hex[:4].upper()}",
            gas_station_id=station1_id,
            buyer_profile_id=buyer_profile.id,
            plate_number_snapshot="B 5678 DEF",
            nik_snapshot="3171998877665544",
            risk_score=80,
            risk_level=FraudRiskLevel.HIGH_RISK,
            action_taken=FraudActionTaken.FREEZE_ACCOUNT,
            detected_frauds=[{"type": "MULTI_LOCATION_ABUSE", "points": 80}],
            status=FraudCaseStatus.PENDING,
            created_at=datetime.utcnow()
        )
        log3 = FraudLog(
            id=uuid4(),
            case_id=f"FR-{datetime.utcnow().strftime('%y%m%d')}-{uuid4().hex[:4].upper()}",
            gas_station_id=station2_id,
            buyer_profile_id=buyer_profile.id,
            plate_number_snapshot="B 9999 XYZ",
            nik_snapshot="3171998877665544",
            risk_score=95,
            risk_level=FraudRiskLevel.CRITICAL,
            action_taken=FraudActionTaken.BLOCK_ACCOUNT,
            detected_frauds=[{"type": "STOLEN_CARD_USAGE", "points": 95}],
            status=FraudCaseStatus.PENDING,
            created_at=datetime.utcnow()
        )
        session.add_all([log1, log2, log3])
        await session.commit()
        
        log1_id = log1.id
        log2_id = log2.id
        log3_id = log3.id
        buyer_profile_id = buyer_profile.id

    # Generate Auth Tokens
    gov_token = create_access_token(
        subject=gov_admin_id,
        session_id=str(uuid4()),
        client_type="DASHBOARD",
        roles=["GOV_ADMIN"],
        allowed_apps=["DASHBOARD"]
    )
    spbu1_token = create_access_token(
        subject=spbu1_admin_id,
        session_id=str(uuid4()),
        client_type="DASHBOARD",
        roles=["SPBU_ADMIN"],
        allowed_apps=["DASHBOARD"]
    )
    
    gov_headers = {"Authorization": f"Bearer {gov_token}"}
    spbu1_headers = {"Authorization": f"Bearer {spbu1_token}"}
    
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # 1. Gov Admin reads all logs (should get 3 logs total)
            res = await ac.get("/api/v1/fraud-logs", headers=gov_headers)
            assert res.status_code == 200
            data = res.json()
            assert "items" in data
            assert data["total_count"] == 3
            assert len(data["items"]) == 3
            
            # Check stats structure
            assert "stats" in data
            assert data["stats"]["total"] == 3
            assert data["stats"]["suspicious"] == 1
            assert data["stats"]["high_risk"] == 1
            assert data["stats"]["critical"] == 1
            
            # Check buyer_name preloading works
            assert data["items"][0]["buyer_name"] == "John Suspicious"

            # 2. SPBU 1 Admin reads logs (should only get 2 logs, scoped to station 1)
            res_spbu = await ac.get("/api/v1/fraud-logs", headers=spbu1_headers)
            assert res_spbu.status_code == 200
            data_spbu = res_spbu.json()
            assert data_spbu["total_count"] == 2
            assert len(data_spbu["items"]) == 2
            assert data_spbu["stats"]["total"] == 2
            assert data_spbu["stats"]["suspicious"] == 1
            assert data_spbu["stats"]["high_risk"] == 1
            assert data_spbu["stats"]["critical"] == 0  # CRITICAL is from station 2
            
            # Verify stasiun 2 is NOT present in spbu 1 items
            for item in data_spbu["items"]:
                assert item["gas_station_id"] == str(station1_id)

            # 3. SPBU 1 Admin tries to update status of Station 2 log (Should return 403 Forbidden)
            payload_status = {"status": "RESOLVED", "resolution_notes": "Checked CCTV, false alarm."}
            res_forbidden = await ac.patch(f"/api/v1/fraud-logs/{log3_id}/status", json=payload_status, headers=spbu1_headers)
            assert res_forbidden.status_code == 403

            # 4. Gov Admin updates status of log 1 (Should succeed)
            res_update = await ac.patch(f"/api/v1/fraud-logs/{log1_id}/status", json=payload_status, headers=gov_headers)
            assert res_update.status_code == 200
            update_data = res_update.json()
            assert update_data["status"] == "RESOLVED"
            assert update_data["resolution_notes"] == "Checked CCTV, false alarm."
            assert update_data["resolved_by_name"] == "Gov Administrator"

    finally:
        # DB Cleanup
        async with AsyncSessionLocal() as session:
            await session.execute(delete(FraudLog).where(FraudLog.id.in_([log1_id, log2_id, log3_id])))
            await session.execute(delete(BuyerProfile).where(BuyerProfile.id == buyer_profile_id))
            await session.execute(delete(User).where(User.id.in_([gov_admin_id, spbu1_admin_id, spbu2_admin_id, buyer_user_id])))
            await session.execute(delete(GasStation).where(GasStation.id.in_([station1_id, station2_id])))
            await session.execute(delete(KK).where(KK.id == kk_id))
            await session.commit()
