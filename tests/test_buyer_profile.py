import pytest
from httpx import AsyncClient, ASGITransport
from uuid import uuid4
from sqlalchemy import delete
from sqlalchemy.future import select

from app.main import app
from app.core.database import AsyncSessionLocal
from app.modules.registries.models import KK
from app.modules.users.models import User, UserRole, BuyerProfile
from app.core.security import get_password_hash, create_access_token

@pytest.mark.anyio
async def test_buyer_profile_flow():
    # 1. Create a unique KK and User (BUYER) directly in the database
    kk_id = uuid4()
    buyer_id = uuid4()
    non_buyer_id = uuid4()
    
    email_buyer = f"buyer_{uuid4()}@example.com"
    email_non_buyer = f"non_buyer_{uuid4()}@example.com"
    
    async with AsyncSessionLocal() as session:
        # Create KK
        kk = KK(id=kk_id, code=f"KK_{uuid4().hex[:10]}")
        session.add(kk)
        
        # Create BUYER User
        buyer = User(
            id=buyer_id,
            name="Test Buyer",
            email=email_buyer,
            password=get_password_hash("password123"),
            role=[UserRole.BUYER],
            is_active=True
        )
        session.add(buyer)
        
        # Create Non-BUYER User (SUPERADMIN)
        non_buyer = User(
            id=non_buyer_id,
            name="Test Admin",
            email=email_non_buyer,
            password=get_password_hash("password123"),
            role=[UserRole.SUPERADMIN],
            is_active=True
        )
        session.add(non_buyer)
        
        await session.commit()
        
    # Generate JWT tokens
    buyer_token = create_access_token(
        subject=buyer_id,
        session_id=str(uuid4()),
        client_type="BUYER_ANDROID",
        roles=["BUYER"],
        allowed_apps=["BUYER_ANDROID"]
    )
    
    non_buyer_token = create_access_token(
        subject=non_buyer_id,
        session_id=str(uuid4()),
        client_type="ADMIN_WEB",
        roles=["SUPERADMIN"],
        allowed_apps=["ADMIN_WEB"]
    )
    
    profile_uuid = None
    
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            buyer_headers = {"Authorization": f"Bearer {buyer_token}"}
            non_buyer_headers = {"Authorization": f"Bearer {non_buyer_token}"}
            
            # A. Check before create: GET /me/buyer-profile/check (BUYER)
            res = await ac.get("/api/v1/users/me/buyer-profile/check", headers=buyer_headers)
            assert res.status_code == 200
            data = res.json()
            assert data["has_buyer_profile"] is False
            assert data["buyer_profile_id"] is None
            assert data["verification_status"] is None
            
            # B. Get before create: GET /me/buyer-profile -> 404
            res = await ac.get("/api/v1/users/me/buyer-profile", headers=buyer_headers)
            assert res.status_code == 404

            # B2. Get aggregated profile before buyer profile is created
            res = await ac.get("/api/v1/users/me/profile", headers=buyer_headers)
            assert res.status_code == 200
            profile_data = res.json()
            assert profile_data["name"] == "Test Buyer"
            assert profile_data["nikMasked"] == ""
            assert profile_data["isVerified"] is False
            assert profile_data["isEligible"] is False
            assert profile_data["familyCardNumber"] == ""
            assert profile_data["vehiclesCount"] == 0
            assert profile_data["quotaRemaining"] == 0
            assert profile_data["walletBalance"] == 0
            
            # C. Update before create: PUT /me/buyer-profile -> 404
            res = await ac.put("/api/v1/users/me/buyer-profile", headers=buyer_headers, json={"nik_snapshot": "123"})
            assert res.status_code == 404
            
            # D. Non-BUYER access attempt: POST /me/buyer-profile -> 403
            res = await ac.post("/api/v1/users/me/buyer-profile", headers=non_buyer_headers, json={
                "nik_snapshot": "3201010101010001",
                "ktp_nfc_id_snapshot": "NFC123456",
                "kk_id": str(kk_id)
            })
            assert res.status_code == 403
            
            # E. Create BuyerProfile: POST /me/buyer-profile (BUYER) -> 201
            res = await ac.post("/api/v1/users/me/buyer-profile", headers=buyer_headers, json={
                "nik_snapshot": "3201010101010001",
                "ktp_nfc_id_snapshot": "NFC123456",
                "kk_id": str(kk_id)
            })
            assert res.status_code == 201
            profile_data = res.json()
            assert profile_data["nik_snapshot"] == "3201010101010001"
            assert profile_data["ktp_nfc_id_snapshot"] == "NFC123456"
            assert profile_data["kk_id"] == str(kk_id)
            assert profile_data["user_id"] == str(buyer_id)
            assert profile_data["verification_status"] == "UNVERIFIED"
            
            profile_uuid = profile_data["id"]
            
            # F. Create second time: POST /me/buyer-profile -> 400 (Duplicate)
            res = await ac.post("/api/v1/users/me/buyer-profile", headers=buyer_headers, json={
                "nik_snapshot": "3201010101010001",
                "ktp_nfc_id_snapshot": "NFC123456",
                "kk_id": str(kk_id)
            })
            assert res.status_code == 400
            
            # G. Check after create: GET /me/buyer-profile/check -> True
            res = await ac.get("/api/v1/users/me/buyer-profile/check", headers=buyer_headers)
            assert res.status_code == 200
            data = res.json()
            assert data["has_buyer_profile"] is True
            assert data["buyer_profile_id"] == profile_uuid
            assert data["verification_status"] == "UNVERIFIED"
            
            # H. Get profile: GET /me/buyer-profile -> 200
            res = await ac.get("/api/v1/users/me/buyer-profile", headers=buyer_headers)
            assert res.status_code == 200
            assert res.json()["nik_snapshot"] == "3201010101010001"

            # H2. Get aggregated profile after buyer profile is created
            res = await ac.get("/api/v1/users/me/profile", headers=buyer_headers)
            assert res.status_code == 200
            profile_data = res.json()
            assert profile_data["name"] == "Test Buyer"
            assert profile_data["nikMasked"] == "3201****0001"
            assert profile_data["isVerified"] is False
            assert profile_data["isEligible"] is False
            assert profile_data["familyCardNumber"].startswith("KK_")
            assert profile_data["vehiclesCount"] == 0
            assert profile_data["quotaRemaining"] == 150
            assert profile_data["walletBalance"] == 0
            
            # I. Update profile with invalid KK: PUT /me/buyer-profile -> 400
            res = await ac.put("/api/v1/users/me/buyer-profile", headers=buyer_headers, json={
                "kk_id": str(uuid4())
            })
            assert res.status_code == 400
            
            # J. Update profile with valid KK and new NIK: PUT /me/buyer-profile -> 200
            res = await ac.put("/api/v1/users/me/buyer-profile", headers=buyer_headers, json={
                "nik_snapshot": "3201010101010002"
            })
            assert res.status_code == 200
            assert res.json()["nik_snapshot"] == "3201010101010002"
            
            # K. Get /auth/me -> should include BUYER access context with buyer_profile_id
            res = await ac.get("/api/v1/auth/me", headers=buyer_headers)
            assert res.status_code == 200
            auth_data = res.json()
            buyer_context = next(
                (ctx for ctx in auth_data["user"]["access_contexts"] if ctx["role"] == "BUYER"), None
            )
            assert buyer_context is not None
            assert buyer_context["buyer_profile_id"] == profile_uuid
            
    finally:
        # Clean up database
        async with AsyncSessionLocal() as session:
            if profile_uuid:
                await session.execute(
                    delete(BuyerProfile).where(BuyerProfile.id == profile_uuid)
                )
            await session.execute(
                delete(User).where(User.id.in_([buyer_id, non_buyer_id]))
            )
            await session.execute(
                delete(KK).where(KK.id == kk_id)
            )
            await session.commit()
