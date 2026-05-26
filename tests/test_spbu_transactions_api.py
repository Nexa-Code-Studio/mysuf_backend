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
from app.modules.fuels.models import FuelType
from app.modules.transactions.models import (
    FuelTransaction, 
    FuelTransactionStatus, 
    BuyerType,
    PaymentMethod
)
from app.core.security import get_password_hash, create_access_token

@pytest.mark.anyio
async def test_spbu_transactions_api():
    # 1. Setup mock resources
    spbu_admin_id = uuid4()
    gov_admin_id = uuid4()
    station_id = uuid4()
    fuel_type_id = uuid4()
    
    tx1_id = uuid4()
    tx2_id = uuid4()
    
    async with AsyncSessionLocal() as session:
        # Create Station
        station = GasStation(
            id=station_id,
            name="Test SPBU Fatmawati 2",
            latitude=-6.290000,
            longitude=106.790000
        )
        session.add(station)
        
        # Create Fuel Type
        from app.modules.fuels.models import FuelCategory, SubsidyType
        fuel_type = FuelType(
            id=fuel_type_id,
            name="Pertamax Turbo",
            octane="98",
            category=FuelCategory.GASOLINE,
            price_per_liter=Decimal("16000.00"),
            subsidy_price_per_liter=None,
            subsidy_type=SubsidyType.NON_SUBSIDIZED
        )
        session.add(fuel_type)
        
        # Create Users
        spbu_admin = User(
            id=spbu_admin_id,
            name="Fatmawati Admin 2",
            email=f"spbu-{uuid4().hex[:8]}@example.com",
            password=get_password_hash("password123"),
            role=[UserRole.SPBU_ADMIN],
            gas_station_id=station_id,
            is_active=True
        )
        gov_admin = User(
            id=gov_admin_id,
            name="Government Admin 2",
            email=f"gov-{uuid4().hex[:8]}@example.com",
            password=get_password_hash("password123"),
            role=[UserRole.GOV_ADMIN],
            is_active=True
        )
        session.add_all([spbu_admin, gov_admin])
        await session.commit()

        # Create Fuel Transactions: 1 Completed, 1 Pending
        tx1 = FuelTransaction(
            id=tx1_id,
            buyer_type=BuyerType.PERSONAL,
            gas_station_id=station_id,
            fuel_type_id=fuel_type_id,
            liters=Decimal("20.00"),
            is_subsidized=False,
            subsidized_liters=Decimal("0.00"),
            non_subsidized_liters=Decimal("20.00"),
            market_price_per_liter=Decimal("16000.00"),
            total_amount=Decimal("320000.00"),
            payment_method=PaymentMethod.CASH,
            transaction_status=FuelTransactionStatus.COMPLETED,
            plate_number_snapshot="B 7777 ABC",
            nik_snapshot="3171998877665599",
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
            market_price_per_liter=Decimal("16000.00"),
            total_amount=Decimal("160000.00"),
            payment_method=PaymentMethod.CASH,
            transaction_status=FuelTransactionStatus.PENDING,
            plate_number_snapshot="B 8888 DEF",
            nik_snapshot="3171000011112299",
            created_at=datetime.utcnow()
        )
        session.add_all([tx1, tx2])
        await session.commit()

    # Generate Auth Tokens
    spbu_token = create_access_token(
        subject=spbu_admin_id,
        session_id=str(uuid4()),
        client_type="DASHBOARD",
        roles=["SPBU_ADMIN"],
        allowed_apps=["DASHBOARD"]
    )
    headers_spbu = {"Authorization": f"Bearer {spbu_token}"}
    
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Test 1: Fetch transactions list
            res = await ac.get("/api/v1/spbu/transactions?page=1&size=10", headers=headers_spbu)
            assert res.status_code == 200
            data = res.json()
            
            assert data["total"] == 2
            assert len(data["items"]) == 2
            
            # Check serialization items
            items = {item["id"]: item for item in data["items"]}
            assert str(tx1_id) in items
            assert str(tx2_id) in items
            
            tx1_data = items[str(tx1_id)]
            assert tx1_data["plate"] == "B 7777 ABC"
            assert tx1_data["fuel"] == "Pertamax Turbo"
            assert tx1_data["volume"] == 20.0
            assert tx1_data["price"] == 320000.0
            assert tx1_data["status"] == "Success"
            
            tx2_data = items[str(tx2_id)]
            assert tx2_data["plate"] == "B 8888 DEF"
            assert tx2_data["status"] == "Review"

            # Check stats
            summary = data["summary"]
            assert summary["total_active_transactions"] == 2
            assert summary["total_volume"] == 20.0 # only completed
            assert summary["total_revenue"] == 320000.0

            # Test 2: Filter by status
            res_filtered = await ac.get("/api/v1/spbu/transactions?status=Success", headers=headers_spbu)
            assert res_filtered.status_code == 200
            data_filtered = res_filtered.json()
            assert data_filtered["total"] == 1
            assert data_filtered["items"][0]["plate"] == "B 7777 ABC"

            # Test 3: Search plates
            res_search = await ac.get("/api/v1/spbu/transactions?search=DEF", headers=headers_spbu)
            assert res_search.status_code == 200
            data_search = res_search.json()
            assert data_search["total"] == 1
            assert data_search["items"][0]["plate"] == "B 8888 DEF"

    finally:
        # Cleanup
        async with AsyncSessionLocal() as session:
            await session.execute(delete(FuelTransaction).where(FuelTransaction.id.in_([tx1_id, tx2_id])))
            await session.execute(delete(User).where(User.id.in_([spbu_admin_id, gov_admin_id])))
            await session.execute(delete(FuelType).where(FuelType.id == fuel_type_id))
            await session.execute(delete(GasStation).where(GasStation.id == station_id))
            await session.commit()
