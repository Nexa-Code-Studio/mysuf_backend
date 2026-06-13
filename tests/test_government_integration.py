import pytest
from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from httpx import ASGITransport, AsyncClient

from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.modules.registries.models import KK
from app.modules.subsidies.models import SubsidyPolicy
from app.modules.users.models import User, UserRole, BuyerProfile, VerificationStatus
from app.modules.vehicles.models import VehicleUsageType

def _build_gov_token(user_id: str) -> str:
    return create_access_token(
        subject=user_id,
        session_id=str(uuid4()),
        client_type="PORTAL_WEB",
        roles=[UserRole.GOV_ADMIN.value],
        allowed_apps=["PORTAL_WEB"],
    )

@pytest.mark.anyio
async def test_government_endpoints():
    kk = KK(code=f"KK-GOV-{uuid4().hex[:8]}")
    user = User(
        name="Gov Inspector",
        email=f"gov-inspector-{uuid4().hex[:8]}@example.com",
        password=get_password_hash("secret123"),
        role=[UserRole.GOV_ADMIN],
        is_active=True,
    )
    buyer = User(
        name="Regular Buyer",
        email=f"buyer-enforce-{uuid4().hex[:8]}@example.com",
        password=get_password_hash("secret123"),
        role=[UserRole.BUYER],
        is_active=True,
    )
    
    kk_id = None
    user_id = None
    buyer_id = None
    buyer_profile_id = None

    try:
        async with AsyncSessionLocal() as session:
            # Check or create PERSONAL subsidy policy
            from sqlalchemy import select
            policy_result = await session.execute(
                select(SubsidyPolicy).filter(SubsidyPolicy.usage_type == VehicleUsageType.PERSONAL)
            )
            policy = policy_result.scalars().first()
            if not policy:
                policy = SubsidyPolicy(
                    name="Personal Fuel Subsidy Policy",
                    usage_type=VehicleUsageType.PERSONAL,
                    monthly_quota_liters=Decimal("200.00"),
                    max_allowed_njkb=Decimal("300000000.00"),
                    is_active=True,
                )
                session.add(policy)
            
            session.add_all([kk, user, buyer])
            await session.commit()
            
            await session.refresh(kk)
            await session.refresh(user)
            await session.refresh(buyer)

            kk_id = kk.id
            user_id = user.id
            buyer_id = buyer.id

            # Create BuyerProfile
            buyer_profile = BuyerProfile(
                nik_snapshot=f"3201{uuid4().hex[:12]}",
                ktp_nfc_id_snapshot=f"NFC-{uuid4().hex[:8]}",
                kk_id=kk.id,
                user_id=buyer.id,
                verification_status=VerificationStatus.VERIFIED,
                risk_score=Decimal("20.00"),
            )
            session.add(buyer_profile)
            await session.commit()
            await session.refresh(buyer_profile)
            buyer_profile_id = buyer_profile.id

        token = _build_gov_token(str(user_id))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # 1. Test GET /api/v1/government/eligibility
            res = await ac.get(
                "/api/v1/government/eligibility",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 200
            data = res.json()
            assert "items" in data
            assert len(data["items"]) >= 1

            # 2. Test PUT /api/v1/government/eligibility/threshold
            res = await ac.put(
                "/api/v1/government/eligibility/threshold",
                json={"threshold": 350000000},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 200
            assert res.json()["threshold"] == 350000000

            # 3. Test GET /api/v1/government/quota-policies
            res = await ac.get(
                "/api/v1/government/quota-policies",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 200
            data = res.json()
            assert "warga" in data
            assert "motor_komersial" in data

            # 4. Test PUT /api/v1/government/quota-policies
            res = await ac.put(
                "/api/v1/government/quota-policies",
                json={
                    "warga": 280,
                    "motor_komersial": 120,
                    "mobil_komersial": 260,
                    "truk_komersial": 550
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 200
            assert res.json()["status"] == "success"

            # 5. Test GET /api/v1/government/quota-transactions
            res = await ac.get(
                "/api/v1/government/quota-transactions",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 200
            assert len(res.json()["items"]) >= 1

            # 6. Test POST /api/v1/government/blacklist (Block account)
            res = await ac.post(
                "/api/v1/government/blacklist",
                json={
                    "accountId": f"NIK {buyer_profile.nik_snapshot}",
                    "holderName": buyer.name,
                    "plate": "B 1234 ABC",
                    "type": "Car",
                    "status": "BLOCKED",
                    "reason": "Dugaan penimbunan BBM subsidi"
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 200
            
            # Verify user is blocked in DB
            async with AsyncSessionLocal() as session:
                refreshed_buyer = await session.get(User, buyer_id)
                assert refreshed_buyer.is_blocked is True

            # 7. Test GET /api/v1/government/blacklist
            res = await ac.get(
                "/api/v1/government/blacklist",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 200
            blacklist_items = res.json()["items"]
            assert any(item["holderName"] == buyer.name for item in blacklist_items)

            # 8. Test PUT /api/v1/government/blacklist/{user_id}/restore
            res = await ac.put(
                f"/api/v1/government/blacklist/{buyer_id}/restore",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 200

            # Verify user is unblocked in DB
            async with AsyncSessionLocal() as session:
                refreshed_buyer = await session.get(User, buyer_id)
                assert refreshed_buyer.is_blocked is False

    finally:
        # Teardown
        async with AsyncSessionLocal() as session:
            from sqlalchemy import delete
            from app.modules.subsidies.models import KKSubsidyEligibility
            from app.modules.transactions.models import FraudLog
            from app.modules.gas_stations.models import GasStation

            if buyer_profile_id:
                await session.execute(delete(FraudLog).where(FraudLog.buyer_profile_id == buyer_profile_id))
                await session.execute(delete(BuyerProfile).where(BuyerProfile.id == buyer_profile_id))
            if kk_id:
                await session.execute(delete(KKSubsidyEligibility).where(KKSubsidyEligibility.kk_id == kk_id))
            if buyer_id:
                await session.execute(delete(User).where(User.id == buyer_id))
            if user_id:
                await session.execute(delete(User).where(User.id == user_id))
            if kk_id:
                await session.execute(delete(KK).where(KK.id == kk_id))
            
            # Clean up SPBU Temp if it was created
            await session.execute(delete(GasStation).where(GasStation.name == "SPBU Temp"))
            
            await session.commit()
