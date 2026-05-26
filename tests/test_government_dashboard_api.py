import pytest
from httpx import AsyncClient, ASGITransport
from uuid import uuid4
from sqlalchemy import delete
from datetime import datetime
from decimal import Decimal

from app.main import app
from app.core.database import AsyncSessionLocal
from app.modules.users.models import User, UserRole
from app.modules.gas_stations.models import GasStation
from app.modules.fuels.models import FuelType, FuelCategory, SubsidyType

from app.modules.transactions.models import (
    FuelTransaction, 
    FuelTransactionStatus, 
    FraudLog, 
    FraudRiskLevel, 
    FraudActionTaken, 
    FraudCaseStatus,
    BuyerType,
    PaymentMethod
)
from app.core.security import get_password_hash, create_access_token

@pytest.mark.anyio
async def test_government_dashboard_summary_api():
    # 0. Query initial counts
    gov_admin_id = uuid4()
    spbu_admin_id = uuid4()
    station_id = uuid4()
    fuel_type_id = uuid4()
    
    tx1_id = uuid4()
    tx2_id = uuid4()
    log1_id = uuid4()
    log2_id = uuid4()

    async with AsyncSessionLocal() as session:
        from sqlalchemy import func, select
        initial_tx = (await session.execute(select(func.count(FuelTransaction.id)))).scalar() or 0
        initial_high = (await session.execute(select(func.count(FraudLog.id).filter(FraudLog.risk_level == FraudRiskLevel.HIGH_RISK)))).scalar() or 0
        initial_crit = (await session.execute(select(func.count(FraudLog.id).filter(FraudLog.risk_level == FraudRiskLevel.CRITICAL)))).scalar() or 0
        initial_liters = (await session.execute(select(func.sum(FuelTransaction.liters).filter(FuelTransaction.transaction_status == FuelTransactionStatus.COMPLETED)))).scalar() or Decimal("0.0")
        initial_liters = float(initial_liters)

    async with AsyncSessionLocal() as session:


        # Create Station
        station = GasStation(
            id=station_id,
            name="Regulatory Test SPBU",
            latitude=-6.200000,
            longitude=106.800000
        )
        session.add(station)
        
        # Create Fuel Type
        fuel_type = FuelType(
            id=fuel_type_id,
            name="Pertalite",
            price_per_liter=Decimal("10000.00"),
            subsidy_price_per_liter=Decimal("10000.00"),
            category=FuelCategory.GASOLINE,
            subsidy_type=SubsidyType.SUBSIDIZED
        )
        session.add(fuel_type)
        
        # Create Users (GOV_ADMIN and SPBU_ADMIN)
        gov_admin = User(
            id=gov_admin_id,
            name="Gov Inspector",
            email=f"gov-{uuid4().hex[:8]}@example.com",
            password=get_password_hash("password123"),
            role=[UserRole.GOV_ADMIN],
            is_active=True
        )
        spbu_admin = User(
            id=spbu_admin_id,
            name="SPBU Manager",
            email=f"spbu-{uuid4().hex[:8]}@example.com",
            password=get_password_hash("password123"),
            role=[UserRole.SPBU_ADMIN],
            gas_station_id=station_id,
            is_active=True
        )
        session.add_all([gov_admin, spbu_admin])
        await session.commit()

        # Create Fuel Transactions: 2 Completed
        tx1 = FuelTransaction(
            id=tx1_id,
            buyer_type=BuyerType.PERSONAL,
            gas_station_id=station_id,
            fuel_type_id=fuel_type_id,
            liters=Decimal("20.00"),
            is_subsidized=True,
            subsidized_liters=Decimal("20.00"),
            non_subsidized_liters=Decimal("0.00"),
            market_price_per_liter=Decimal("10000.00"),
            total_amount=Decimal("200000.00"),
            payment_method=PaymentMethod.CASH,
            transaction_status=FuelTransactionStatus.COMPLETED,
            plate_number_snapshot="B 1111 AAA",
            nik_snapshot="1234567890123456",
            created_at=datetime.utcnow()
        )
        tx2 = FuelTransaction(
            id=tx2_id,
            buyer_type=BuyerType.PERSONAL,
            gas_station_id=station_id,
            fuel_type_id=fuel_type_id,
            liters=Decimal("40.00"),
            is_subsidized=True,
            subsidized_liters=Decimal("40.00"),
            non_subsidized_liters=Decimal("0.00"),
            market_price_per_liter=Decimal("10000.00"),
            total_amount=Decimal("400000.00"),
            payment_method=PaymentMethod.CASH,
            transaction_status=FuelTransactionStatus.COMPLETED,
            plate_number_snapshot="B 2222 BBB",
            nik_snapshot="1234567890123457",
            created_at=datetime.utcnow()
        )
        session.add_all([tx1, tx2])
        
        # Create 2 Fraud Logs (1 HIGH_RISK, 1 CRITICAL)
        log1 = FraudLog(
            id=log1_id,
            case_id=f"FR-{datetime.utcnow().strftime('%y%m%d')}-{uuid4().hex[:4].upper()}",
            gas_station_id=station_id,
            plate_number_snapshot="B 1111 AAA",
            nik_snapshot="1234567890123456",
            risk_score=70,
            risk_level=FraudRiskLevel.HIGH_RISK,
            action_taken=FraudActionTaken.FREEZE_ACCOUNT,
            detected_frauds=[{"type": "RAPID_PURCHASE", "points": 70, "reason": "Beli berulang kali"}],
            status=FraudCaseStatus.PENDING,
            created_at=datetime.utcnow()
        )
        log2 = FraudLog(
            id=log2_id,
            case_id=f"FR-{datetime.utcnow().strftime('%y%m%d')}-{uuid4().hex[:4].upper()}",
            gas_station_id=station_id,
            plate_number_snapshot="B 2222 BBB",
            nik_snapshot="1234567890123457",
            risk_score=110,
            risk_level=FraudRiskLevel.CRITICAL,
            action_taken=FraudActionTaken.BLOCK_ACCOUNT,
            detected_frauds=[{"type": "MULTI_LOCATION_ABUSE", "points": 110, "reason": "Teleportasi kendaraan"}],
            status=FraudCaseStatus.PENDING,
            created_at=datetime.utcnow()
        )
        session.add_all([log1, log2])
        await session.commit()

    # Generate Auth Tokens
    gov_token = create_access_token(
        subject=gov_admin_id,
        session_id=str(uuid4()),
        client_type="DASHBOARD",
        roles=["GOV_ADMIN"],
        allowed_apps=["DASHBOARD"]
    )
    spbu_token = create_access_token(
        subject=spbu_admin_id,
        session_id=str(uuid4()),
        client_type="DASHBOARD",
        roles=["SPBU_ADMIN"],
        allowed_apps=["DASHBOARD"]
    )
    
    headers_gov = {"Authorization": f"Bearer {gov_token}"}
    headers_spbu = {"Authorization": f"Bearer {spbu_token}"}
    
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Test 1: Fetch government dashboard summary as GOV_ADMIN (permitted)
            res = await ac.get("/api/v1/government/summary", headers=headers_gov)
            assert res.status_code == 200
            data = res.json()
            
            assert data["totalTransactions"] == initial_tx + 2
            assert data["highRiskCount"] == initial_high + 1
            assert data["criticalCount"] == initial_crit + 1
            assert data["totalLiters"] == initial_liters + 60.0
            
            # Check fraud stations
            stations = data["stationsWithHighestFraudCount"]
            assert len(stations) >= 1
            target_station = next((s for s in stations if s["label"] == "Regulatory Test SPBU"), None)
            assert target_station is not None
            assert target_station["transactionCount"] == 2
            assert target_station["fraudCount"] == 2
            assert target_station["score"] == 180 # 70 + 110

            
            # Test 2: Fetch government dashboard summary as SPBU_ADMIN (forbidden)
            res_spbu = await ac.get("/api/v1/government/summary", headers=headers_spbu)
            assert res_spbu.status_code == 403

    finally:
        # Cleanup
        async with AsyncSessionLocal() as session:
            await session.execute(delete(FraudLog).where(FraudLog.id.in_([log1_id, log2_id])))
            await session.execute(delete(FuelTransaction).where(FuelTransaction.id.in_([tx1_id, tx2_id])))
            await session.execute(delete(User).where(User.id.in_([gov_admin_id, spbu_admin_id])))
            await session.execute(delete(FuelType).where(FuelType.id == fuel_type_id))
            await session.execute(delete(GasStation).where(GasStation.id == station_id))
            await session.commit()


@pytest.mark.anyio
async def test_government_heatmap_api():
    gov_admin_id = uuid4()
    spbu_admin_id = uuid4()
    station_id = uuid4()
    fuel_type_id = uuid4()
    
    tx_id = uuid4()
    log_id = uuid4()

    async with AsyncSessionLocal() as session:
        # Create Station with explicit Banten coordinates
        station = GasStation(
            id=station_id,
            name="Regulatory Heatmap SPBU (Banten - Zone 99)",
            latitude=-6.150000,
            longitude=106.100000
        )
        session.add(station)
        
        # Create Fuel Type
        fuel_type = FuelType(
            id=fuel_type_id,
            name="Pertalite",
            price_per_liter=Decimal("10000.00"),
            subsidy_price_per_liter=Decimal("10000.00"),
            category=FuelCategory.GASOLINE,
            subsidy_type=SubsidyType.SUBSIDIZED
        )
        session.add(fuel_type)
        
        # Create Users (GOV_ADMIN and SPBU_ADMIN)
        gov_admin = User(
            id=gov_admin_id,
            name="Gov Inspector 2",
            email=f"gov2-{uuid4().hex[:8]}@example.com",
            password=get_password_hash("password123"),
            role=[UserRole.GOV_ADMIN],
            is_active=True
        )
        spbu_admin = User(
            id=spbu_admin_id,
            name="SPBU Manager 2",
            email=f"spbu2-{uuid4().hex[:8]}@example.com",
            password=get_password_hash("password123"),
            role=[UserRole.SPBU_ADMIN],
            gas_station_id=station_id,
            is_active=True
        )
        session.add_all([gov_admin, spbu_admin])
        await session.commit()

        # Create Fuel Transactions: 1 Completed
        tx = FuelTransaction(
            id=tx_id,
            buyer_type=BuyerType.PERSONAL,
            gas_station_id=station_id,
            fuel_type_id=fuel_type_id,
            liters=Decimal("250.00"),
            is_subsidized=True,
            subsidized_liters=Decimal("250.00"),
            non_subsidized_liters=Decimal("0.00"),
            market_price_per_liter=Decimal("10000.00"),
            total_amount=Decimal("2500000.00"),
            payment_method=PaymentMethod.CASH,
            transaction_status=FuelTransactionStatus.COMPLETED,
            plate_number_snapshot="B 9999 CC",
            nik_snapshot="1234567890123459",
            created_at=datetime.utcnow()
        )
        session.add(tx)
        
        # Create 1 Fraud Log
        log = FraudLog(
            id=log_id,
            case_id=f"FR-{datetime.utcnow().strftime('%y%m%d')}-{uuid4().hex[:4].upper()}",
            gas_station_id=station_id,
            plate_number_snapshot="B 9999 CC",
            nik_snapshot="1234567890123459",
            risk_score=95,
            risk_level=FraudRiskLevel.CRITICAL,
            action_taken=FraudActionTaken.BLOCK_ACCOUNT,
            detected_frauds=[{"type": "OVER_LIMIT", "points": 95, "reason": "Beli melebihi batas kuota"}],
            status=FraudCaseStatus.PENDING,
            created_at=datetime.utcnow()
        )
        session.add(log)
        await session.commit()

    # Generate Auth Tokens
    gov_token = create_access_token(
        subject=gov_admin_id,
        session_id=str(uuid4()),
        client_type="DASHBOARD",
        roles=["GOV_ADMIN"],
        allowed_apps=["DASHBOARD"]
    )
    spbu_token = create_access_token(
        subject=spbu_admin_id,
        session_id=str(uuid4()),
        client_type="DASHBOARD",
        roles=["SPBU_ADMIN"],
        allowed_apps=["DASHBOARD"]
    )
    
    headers_gov = {"Authorization": f"Bearer {gov_token}"}
    headers_spbu = {"Authorization": f"Bearer {spbu_token}"}
    
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Test 1: Fetch government heatmap as GOV_ADMIN (permitted)
            res = await ac.get("/api/v1/government/heatmap", headers=headers_gov)
            assert res.status_code == 200
            data = res.json()
            
            # Verify Map GeoJSON structure
            assert "map_data" in data
            map_data = data["map_data"]
            assert map_data["type"] == "FeatureCollection"
            assert isinstance(map_data["features"], list)
            
            # Check for seeded features
            our_feature = next((f for f in map_data["features"] if f["properties"]["id"] == "Regulatory Heatmap SPBU (Banten - Zone 99)"), None)
            assert our_feature is not None
            assert our_feature["geometry"]["type"] == "Point"
            assert our_feature["geometry"]["coordinates"] == [106.100000, -6.150000] # [longitude, latitude]
            assert our_feature["properties"]["fraud_cases"] == 1
            assert our_feature["properties"]["intensity"] == 0.95 # 95 / 100
            
            # Verify Province breakdown list structure
            assert "provinces" in data
            provinces = data["provinces"]
            assert isinstance(provinces, list)
            
            # Check for our seeded province (Banten)
            banten_prov = next((p for p in provinces if p["province"] == "Banten"), None)
            assert banten_prov is not None
            assert banten_prov["island"] == "Jawa"
            assert banten_prov["volume"] >= 250.0
            assert banten_prov["activeSpbu"] >= 1
            assert banten_prov["intensity"] == "Sangat Tinggi" # risk 95 is Sangat Tinggi
            assert banten_prov["fraudScore"] == 95
            
            # Test 2: Fetch government heatmap as SPBU_ADMIN (forbidden)
            res_spbu = await ac.get("/api/v1/government/heatmap", headers=headers_spbu)
            assert res_spbu.status_code == 403

    finally:
        # Cleanup
        async with AsyncSessionLocal() as session:
            await session.execute(delete(FraudLog).where(FraudLog.id == log_id))
            await session.execute(delete(FuelTransaction).where(FuelTransaction.id == tx_id))
            await session.execute(delete(User).where(User.id.in_([gov_admin_id, spbu_admin_id])))
            await session.execute(delete(FuelType).where(FuelType.id == fuel_type_id))
            await session.execute(delete(GasStation).where(GasStation.id == station_id))
            await session.commit()

