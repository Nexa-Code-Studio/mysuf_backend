from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.modules.fuels.models import FuelCategory, FuelType, SubsidyType
from app.modules.gas_stations.models import GasStation
from app.modules.transactions.models import BuyerType, FuelTransaction, FuelTransactionStatus, PaymentMethod
from app.modules.users.models import User, UserRole


def _build_cashier_token(user_id: str) -> str:
    return create_access_token(
        subject=user_id,
        session_id=str(uuid4()),
        client_type="POS_ANDROID",
        roles=[UserRole.SALES_OFFICER.value],
        allowed_apps=["POS_ANDROID"],
    )


@pytest.mark.anyio
async def test_cashier_performance_returns_today_summary_and_recent_transactions():
    now = datetime.utcnow()
    today = datetime(now.year, now.month, now.day, 9, 0, 0)
    yesterday = today - timedelta(days=1)

    gas_station = GasStation(
        name=f"SPBU Performance {uuid4().hex[:6]}",
        longitude=106.8,
        latitude=-6.2,
    )
    fuel_type = FuelType(
        name="Pertalite",
        octane="90",
        category=FuelCategory.GASOLINE,
        price_per_liter=Decimal("10000.00"),
        subsidy_price_per_liter=Decimal("10000.00"),
        subsidy_type=SubsidyType.SUBSIDIZED,
    )
    cashier = User(
        name="Cashier Performance",
        email=f"cashier-performance-{uuid4().hex[:8]}@example.com",
        password=get_password_hash("secret123"),
        role=[UserRole.SALES_OFFICER],
        is_active=True,
    )

    gas_station_id = None
    fuel_type_id = None
    cashier_id = None
    transaction_ids: list = []

    try:
        async with AsyncSessionLocal() as session:
            session.add_all([gas_station, fuel_type])
            await session.commit()
            await session.refresh(gas_station)
            await session.refresh(fuel_type)

            cashier.gas_station_id = gas_station.id
            session.add(cashier)
            await session.commit()
            await session.refresh(cashier)

            transactions = [
                FuelTransaction(
                    buyer_type=BuyerType.PERSONAL,
                    gas_station_id=gas_station.id,
                    fuel_type_id=fuel_type.id,
                    liters=Decimal("10.00"),
                    is_subsidized=True,
                    subsidized_liters=Decimal("10.00"),
                    non_subsidized_liters=Decimal("0.00"),
                    market_price_per_liter=Decimal("10000.00"),
                    subsidized_price_per_liter=Decimal("10000.00"),
                    total_amount=Decimal("100000.00"),
                    payment_method=PaymentMethod.CASH,
                    transaction_status=FuelTransactionStatus.COMPLETED,
                    verified_by_user_id=cashier.id,
                    plate_number_snapshot="B 1234 AAA",
                    nik_snapshot="3171000000000001",
                    created_at=today + timedelta(minutes=15),
                    updated_at=today + timedelta(minutes=15),
                ),
                FuelTransaction(
                    buyer_type=BuyerType.PERSONAL,
                    gas_station_id=gas_station.id,
                    fuel_type_id=fuel_type.id,
                    liters=Decimal("15.00"),
                    is_subsidized=True,
                    subsidized_liters=Decimal("15.00"),
                    non_subsidized_liters=Decimal("0.00"),
                    market_price_per_liter=Decimal("10000.00"),
                    subsidized_price_per_liter=Decimal("10000.00"),
                    total_amount=Decimal("150000.00"),
                    payment_method=PaymentMethod.CASH,
                    transaction_status=FuelTransactionStatus.FAILED,
                    verified_by_user_id=cashier.id,
                    plate_number_snapshot="B 5678 BBB",
                    nik_snapshot="3171000000000002",
                    created_at=today + timedelta(minutes=30),
                    updated_at=today + timedelta(minutes=30),
                ),
                FuelTransaction(
                    buyer_type=BuyerType.PERSONAL,
                    gas_station_id=gas_station.id,
                    fuel_type_id=fuel_type.id,
                    liters=Decimal("5.00"),
                    is_subsidized=True,
                    subsidized_liters=Decimal("5.00"),
                    non_subsidized_liters=Decimal("0.00"),
                    market_price_per_liter=Decimal("10000.00"),
                    subsidized_price_per_liter=Decimal("10000.00"),
                    total_amount=Decimal("50000.00"),
                    payment_method=PaymentMethod.CASH,
                    transaction_status=FuelTransactionStatus.CANCELLED,
                    verified_by_user_id=cashier.id,
                    plate_number_snapshot="B 5678 BBB",
                    nik_snapshot="3171000000000003",
                    created_at=today + timedelta(minutes=45),
                    updated_at=today + timedelta(minutes=45),
                ),
                FuelTransaction(
                    buyer_type=BuyerType.PERSONAL,
                    gas_station_id=gas_station.id,
                    fuel_type_id=fuel_type.id,
                    liters=Decimal("7.00"),
                    is_subsidized=True,
                    subsidized_liters=Decimal("7.00"),
                    non_subsidized_liters=Decimal("0.00"),
                    market_price_per_liter=Decimal("10000.00"),
                    subsidized_price_per_liter=Decimal("10000.00"),
                    total_amount=Decimal("70000.00"),
                    payment_method=PaymentMethod.CASH,
                    transaction_status=FuelTransactionStatus.COMPLETED,
                    verified_by_user_id=cashier.id,
                    plate_number_snapshot="B 9999 YYY",
                    nik_snapshot="3171000000000004",
                    created_at=yesterday,
                    updated_at=yesterday,
                ),
            ]

            session.add_all(transactions)
            await session.commit()
            transaction_ids.extend(item.id for item in transactions)

            gas_station_id = gas_station.id
            fuel_type_id = fuel_type.id
            cashier_id = cashier.id

        token = _build_cashier_token(str(cashier_id))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(
                "/api/v1/cashier/performance",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        body = response.json()
        summary = body["summary"]
        assert summary == {
            "total_transactions": 3,
            "completed_transactions": 1,
            "failed_transactions": 1,
            "cancelled_transactions": 1,
            "pending_transactions": 0,
            "served_vehicles": 2,
            "total_liters": 30.0,
            "total_revenue": 100000.0,
            "average_transaction_minutes": 15.0,
        }

        recent_transactions = body["recent_transactions"]
        assert len(recent_transactions) == 3
        assert recent_transactions[0]["plate_number_snapshot"] == "B 5678 BBB"
        assert recent_transactions[0]["transaction_status"] == "CANCELLED"
        assert recent_transactions[1]["transaction_status"] == "FAILED"
        assert recent_transactions[2]["transaction_status"] == "COMPLETED"
    finally:
        async with AsyncSessionLocal() as session:
            if transaction_ids:
                await session.execute(delete(FuelTransaction).where(FuelTransaction.id.in_(transaction_ids)))
            if cashier_id is not None:
                await session.execute(delete(User).where(User.id == cashier_id))
            if fuel_type_id is not None:
                await session.execute(delete(FuelType).where(FuelType.id == fuel_type_id))
            if gas_station_id is not None:
                await session.execute(delete(GasStation).where(GasStation.id == gas_station_id))
            await session.commit()
