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
async def test_spbu_dashboard_summary_api():
    # 1. Setup mock resources
    spbu_admin_id = uuid4()
    gov_admin_id = uuid4()
    station_id = uuid4()
    fuel_type_id = uuid4()
    
    tx1_id = uuid4()
    tx2_id = uuid4()
    log1_id = uuid4()
    
    async with AsyncSessionLocal() as session:
        # Create Station
        station = GasStation(
            id=station_id,
            name="Test SPBU Fatmawati",
            latitude=-6.290000,
            longitude=106.790000
        )
        session.add(station)
        
        # Create Fuel Type
        fuel_type = FuelType(
            id=fuel_type_id,
            name="Pertalite",
            category=FuelCategory.GASOLINE,
            price_per_liter=Decimal("10000.00"),
            subsidy_type=SubsidyType.SUBSIDIZED,
        )
        session.add(fuel_type)
        
        # Create Users
        spbu_admin = User(
            id=spbu_admin_id,
            name="Fatmawati Admin",
            email=f"spbu-{uuid4().hex[:8]}@example.com",
            password=get_password_hash("password123"),
            role=[UserRole.SPBU_ADMIN],
            gas_station_id=station_id,
            is_active=True
        )
        gov_admin = User(
            id=gov_admin_id,
            name="Government Admin",
            email=f"gov-{uuid4().hex[:8]}@example.com",
            password=get_password_hash("password123"),
            role=[UserRole.GOV_ADMIN],
            is_active=True
        )
        session.add_all([spbu_admin, gov_admin])
        await session.commit()

        # Create Fuel Transactions: 1 Completed, 1 Failed
        tx1 = FuelTransaction(
            id=tx1_id,
            buyer_type=BuyerType.PERSONAL,
            gas_station_id=station_id,
            fuel_type_id=fuel_type_id,
            liters=Decimal("25.50"),
            is_subsidized=True,
            subsidized_liters=Decimal("25.50"),
            non_subsidized_liters=Decimal("0.00"),
            market_price_per_liter=Decimal("10000.00"),
            total_amount=Decimal("255000.00"),
            payment_method=PaymentMethod.CASH,
            transaction_status=FuelTransactionStatus.COMPLETED,
            plate_number_snapshot="B 8888 XYZ",
            nik_snapshot="3171998877665544",
            created_at=datetime.utcnow()
        )
        tx2 = FuelTransaction(
            id=tx2_id,
            buyer_type=BuyerType.PERSONAL,
            gas_station_id=station_id,
            fuel_type_id=fuel_type_id,
            liters=Decimal("10.00"),
            is_subsidized=False,
            subsidized_liters=Decimal("0.00"),
            non_subsidized_liters=Decimal("10.00"),
            market_price_per_liter=Decimal("12500.00"),
            total_amount=Decimal("125000.00"),
            payment_method=PaymentMethod.CASH,
            transaction_status=FuelTransactionStatus.FAILED,
            plate_number_snapshot="B 9999 DEF",
            nik_snapshot="3171000011112222",
            created_at=datetime.utcnow()
        )
        session.add_all([tx1, tx2])
        
        # Create 1 Fraud Log
        log1 = FraudLog(
            id=log1_id,
            case_id=f"FR-{datetime.utcnow().strftime('%y%m%d')}-{uuid4().hex[:4].upper()}",
            gas_station_id=station_id,
            plate_number_snapshot="B 8888 XYZ",
            nik_snapshot="3171998877665544",
            risk_score=90,
            risk_level=FraudRiskLevel.CRITICAL,
            action_taken=FraudActionTaken.BLOCK_ACCOUNT,
            detected_frauds=[{"type": "STOLEN_CARD_USAGE", "points": 90, "reason": "Sikat kuota subsidi liar"}],
            status=FraudCaseStatus.PENDING,
            created_at=datetime.utcnow()
        )
        session.add(log1)
        await session.commit()

    # Generate Auth Tokens
    spbu_token = create_access_token(
        subject=spbu_admin_id,
        session_id=str(uuid4()),
        client_type="DASHBOARD",
        roles=["SPBU_ADMIN"],
        allowed_apps=["DASHBOARD"]
    )
    gov_token = create_access_token(
        subject=gov_admin_id,
        session_id=str(uuid4()),
        client_type="DASHBOARD",
        roles=["GOV_ADMIN"],
        allowed_apps=["DASHBOARD"]
    )
    
    headers_spbu = {"Authorization": f"Bearer {spbu_token}"}
    headers_gov = {"Authorization": f"Bearer {gov_token}"}
    
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Test 1: Fetch dashboard summary as SPBU Admin
            res = await ac.get("/api/v1/spbu/summary", headers=headers_spbu)
            assert res.status_code == 200
            data = res.json()
            
            assert data["gas_station_name"] == "Test SPBU Fatmawati"
            assert data["gas_station_id"] == str(station_id)
            
            # Check stats
            stats = {s["label"]: s["value"] for s in data["stats"]}
            assert stats["Total Transactions"] == "2"
            assert "25.5 L" in stats["Fuel Distributed"]
            assert stats["Rejected Transactions"] == "1"
            assert stats["High-Risk Users"] == "1"
            
            # Check fuel types
            sub_type = next(f for f in data["fuelTypes"] if f["name"] == "Subsidi")
            assert sub_type["value"] == 25.5
            
            # Check fraud alerts
            assert len(data["fraudAlerts"]) == 1
            alert = data["fraudAlerts"][0]
            assert alert["buyer_name"] == "Pengguna"
            assert alert["risk"] == "CRITICAL"
            assert alert["reason"] == "Sikat kuota subsidi liar"
            
            # Test 2: Fetch dashboard summary as Gov Admin
            res_gov = await ac.get(f"/api/v1/spbu/summary?gas_station_id={station_id}", headers=headers_gov)
            assert res_gov.status_code == 200
            data_gov = res_gov.json()
            assert data_gov["gas_station_id"] == str(station_id)

    finally:
        # Cleanup
        async with AsyncSessionLocal() as session:
            await session.execute(delete(FraudLog).where(FraudLog.id == log1_id))
            await session.execute(delete(FuelTransaction).where(FuelTransaction.id.in_([tx1_id, tx2_id])))
            await session.execute(delete(User).where(User.id.in_([spbu_admin_id, gov_admin_id])))
            await session.execute(delete(FuelType).where(FuelType.id == fuel_type_id))
            await session.execute(delete(GasStation).where(GasStation.id == station_id))
            await session.commit()
