import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete

from app.main import app
from app.core.database import AsyncSessionLocal
from app.modules.users.models import User, UserRole, BuyerProfile
from app.modules.users.service import UserService
from app.modules.auth.models import AuthSessionRecord
from app.core.security import get_password_hash, create_access_token
from fastapi import HTTPException, status

@pytest.mark.anyio
async def test_smart_freeze_duration_calculation():
    # 1. Setup mock user
    user = User(
        id=uuid4(),
        name="Smart Freeze Test User",
        email=f"smart_freeze_{uuid4()}@example.com",
        password=get_password_hash("password123"),
        role=[UserRole.BUYER],
        is_active=True
    )
    
    # Tier 1: Safe (0-30)
    UserService.update_user_fraud_status(user, 15.5)
    assert user.is_blocked is False
    assert user.frozen_until is None

    # Tier 2: Suspicious (31-60)
    UserService.update_user_fraud_status(user, 50.0)
    assert user.is_blocked is False
    assert user.frozen_until is None

    # Tier 3: High Risk (61-100) -> Smart calculations
    # Score 61 - 70 -> 1 Day
    UserService.update_user_fraud_status(user, 65.0)
    assert user.is_blocked is False
    assert user.frozen_until is not None
    duration = user.frozen_until - datetime.utcnow()
    assert 23 < duration.total_seconds() / 3600 <= 24

    # Score 71 - 80 -> 3 Days
    UserService.update_user_fraud_status(user, 75.0)
    assert user.is_blocked is False
    assert user.frozen_until is not None
    duration = user.frozen_until - datetime.utcnow()
    assert 71 < duration.total_seconds() / 3600 <= 72

    # Score 81 - 90 -> 7 Days
    UserService.update_user_fraud_status(user, 85.0)
    assert user.is_blocked is False
    assert user.frozen_until is not None
    duration = user.frozen_until - datetime.utcnow()
    assert 167 < duration.total_seconds() / 3600 <= 168

    # Score 91 - 100 -> 14 Days
    UserService.update_user_fraud_status(user, 95.0)
    assert user.is_blocked is False
    assert user.frozen_until is not None
    duration = user.frozen_until - datetime.utcnow()
    assert 335 < duration.total_seconds() / 3600 <= 336

    # Tier 4: Critical (> 100) -> Permanent Block
    UserService.update_user_fraud_status(user, 105.0)
    assert user.is_blocked is True
    assert user.frozen_until is None


@pytest.mark.anyio
async def test_check_user_fraud_status_behavior():
    user = User(
        id=uuid4(),
        name="Status Guard Test User",
        email=f"status_guard_{uuid4()}@example.com",
        password=get_password_hash("password123"),
        role=[UserRole.BUYER],
        is_active=True
    )

    # 1. Normal/Safe user: should pass without exception
    user.is_blocked = False
    user.frozen_until = None
    UserService.check_user_fraud_status(user)

    # 2. Blocked user: should raise 403 Forbidden with specific message
    user.is_blocked = True
    user.frozen_until = None
    with pytest.raises(HTTPException) as exc_info:
        UserService.check_user_fraud_status(user)
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "diblokir secara permanen" in exc_info.value.detail

    # 3. Frozen user: should raise 403 Forbidden with detailed remaining time
    user.is_blocked = False
    user.frozen_until = datetime.utcnow() + timedelta(hours=5, minutes=30)
    with pytest.raises(HTTPException) as exc_info:
        UserService.check_user_fraud_status(user)
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "dibekukan sementara" in exc_info.value.detail
    assert "Tersisa 5 jam" in exc_info.value.detail

    # 4. Expired freeze user: should pass without exception (automatically restored)
    user.is_blocked = False
    user.frozen_until = datetime.utcnow() - timedelta(hours=1)
    UserService.check_user_fraud_status(user)


@pytest.mark.anyio
async def test_auth_guard_integration():
    user_id = uuid4()
    email = f"auth_guard_test_{uuid4()}@example.com"
    password = "SecretPassword123"

    async with AsyncSessionLocal() as session:
        user = User(
            id=user_id,
            name="Auth Guard Integration User",
            email=email,
            password=get_password_hash(password),
            role=[UserRole.BUYER],
            is_active=True,
            is_blocked=False,
            frozen_until=None
        )
        session.add(user)
        await session.commit()

    try:
        # A. Normal User: Login works perfectly
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.post("/api/v1/auth/login", json={
                "email": email,
                "password": password,
                "client_type": "BUYER_ANDROID"
            })
            assert res.status_code == 200
            login_data = res.json()
            access_token = login_data["access_token"]
            refresh_token = login_data["refresh_token"]

            # Standard endpoint works
            res = await ac.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
            assert res.status_code == 200

            # B. Freeze Account: Update frozen_until in DB
            async with AsyncSessionLocal() as session:
                db_user = await session.get(User, user_id)
                db_user.frozen_until = datetime.utcnow() + timedelta(hours=2, minutes=15)
                await session.commit()

            # Attempt Login -> 403 Forbidden
            res = await ac.post("/api/v1/auth/login", json={
                "email": email,
                "password": password,
                "client_type": "BUYER_ANDROID"
            })
            assert res.status_code == 403
            assert "dibekukan sementara" in res.json()["detail"]

            # Attempt access with existing token -> 403 Forbidden
            res = await ac.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
            assert res.status_code == 403
            assert "dibekukan sementara" in res.json()["detail"]

            # Attempt refresh -> 403 Forbidden
            res = await ac.post("/api/v1/auth/refresh", json={
                "refresh_token": refresh_token,
                "client_type": "BUYER_ANDROID"
            })
            assert res.status_code == 403
            assert "dibekukan sementara" in res.json()["detail"]

            # C. Block Account: Update is_blocked to True
            async with AsyncSessionLocal() as session:
                db_user = await session.get(User, user_id)
                db_user.is_blocked = True
                db_user.frozen_until = None
                await session.commit()

            # Attempt Login -> 403 Forbidden
            res = await ac.post("/api/v1/auth/login", json={
                "email": email,
                "password": password,
                "client_type": "BUYER_ANDROID"
            })
            assert res.status_code == 403
            assert "diblokir secara permanen" in res.json()["detail"]

            # Attempt access with existing token -> 403 Forbidden
            res = await ac.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
            assert res.status_code == 403
            assert "diblokir secara permanen" in res.json()["detail"]

    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(AuthSessionRecord).where(AuthSessionRecord.user_id == user_id)
            )
            await session.execute(
                delete(User).where(User.id == user_id)
            )
            await session.commit()


@pytest.mark.anyio
async def test_accumulated_freeze_creates_fraud_log():
    from decimal import Decimal
    from sqlalchemy.future import select
    from app.modules.subsidies.models import EligibilityStatus
    from app.modules.transactions.service import TransactionService
    from app.modules.transactions.schemas import FuelPurchaseRequest
    from app.modules.transactions.models import PaymentMethod, FraudLog, FraudRiskLevel
    from app.modules.users.models import VerificationStatus
    from test_cashier_qris_fuel_purchase import _build_wallet_purchase_fixture, _cleanup_fixture
    
    async with AsyncSessionLocal() as session:
        fixture = await _build_wallet_purchase_fixture(
            session,
            eligibility_status=EligibilityStatus.ELIGIBLE,
            quota_liters=Decimal("200.00"),
            used_liters=Decimal("0.00"),
        )
        service = TransactionService(session)
        
        # Verify initial state
        assert fixture["buyer_profile"].risk_score == 0
        assert fixture["buyer_profile"].verification_status == VerificationStatus.VERIFIED
        
        request = FuelPurchaseRequest(
            nik=fixture["buyer_profile"].nik_snapshot,
            plate_number=fixture["vehicle"].plate_number_snapshot,
            fuel_type_id=fixture["fuel"].id,
            liters=Decimal("10.00"),
            total_amount=Decimal("65000.00"),
            payment_method=PaymentMethod.WALLET,
        )
        
        try:
            # 1. First purchase: normal and completes
            tx1 = await service.execute_fuel_purchase(fixture["cashier"], request)
            assert tx1["status"] == "COMPLETED"
            
            # Move the tx1 timestamp to 5 minutes ago to trigger RAPID_PURCHASE on the next buy
            db_tx1 = await service.repo.get_fuel_transaction_by_id(tx1["transaction_id"])
            db_tx1.created_at = datetime.utcnow() - timedelta(minutes=5)
            await session.commit()
            
            # 2. Second purchase: triggers RAPID_PURCHASE (+25 points).
            # Buyer risk score becomes 25.
            tx2 = await service.execute_fuel_purchase(fixture["cashier"], request)
            assert tx2["status"] == "COMPLETED"
            
            # Move tx2 timestamp to 3 minutes ago
            db_tx2 = await service.repo.get_fuel_transaction_by_id(tx2["transaction_id"])
            db_tx2.created_at = datetime.utcnow() - timedelta(minutes=3)
            await session.commit()
            
            # 3. Third purchase: triggers RAPID_PURCHASE again (+25 points).
            # Buyer risk score becomes 50.
            tx3 = await service.execute_fuel_purchase(fixture["cashier"], request)
            assert tx3["status"] == "COMPLETED"
            
            # Move tx3 timestamp to 2 minutes ago
            db_tx3 = await service.repo.get_fuel_transaction_by_id(tx3["transaction_id"])
            db_tx3.created_at = datetime.utcnow() - timedelta(minutes=2)
            await session.commit()
            
            # 4. Fourth purchase: triggers RAPID_PURCHASE again (+25 points).
            # Buyer risk score becomes 75.
            # This crosses the freeze threshold (>= 61), so the user gets frozen
            # and a FraudLog is successfully saved in the database.
            tx4 = await service.execute_fuel_purchase(fixture["cashier"], request)
            assert tx4["status"] == "COMPLETED"
            
            await session.refresh(fixture["buyer_profile"])
            await session.refresh(fixture["buyer_user"])
            
            assert float(fixture["buyer_profile"].risk_score) == 75.0
            assert fixture["buyer_profile"].verification_status == VerificationStatus.UNVERIFIED
            assert fixture["buyer_user"].frozen_until is not None
            
            # Check that a fraud log was created for this freeze
            res_logs = await session.execute(
                select(FraudLog).filter(FraudLog.buyer_profile_id == fixture["buyer_profile"].id)
            )
            logs = res_logs.scalars().all()
            assert len(logs) == 1
            assert logs[0].risk_score == 75
            assert logs[0].risk_level == FraudRiskLevel.HIGH_RISK
            assert logs[0].detected_frauds[0]["type"] == "RAPID_PURCHASE"
            
        finally:
            async with AsyncSessionLocal() as cleanup_session:
                await cleanup_session.execute(
                    delete(FraudLog).filter(FraudLog.buyer_profile_id == fixture["buyer_profile"].id)
                )
                from app.modules.transactions.models import FuelTransaction, WalletTransaction
                await cleanup_session.execute(
                    delete(FuelTransaction).filter(FuelTransaction.verified_by_user_id == fixture["cashier"].id)
                )
                await cleanup_session.execute(
                    delete(WalletTransaction).filter(WalletTransaction.wallet_id == fixture["wallet"].id)
                )
                await cleanup_session.commit()
            await _cleanup_fixture(session, fixture["ids"])
