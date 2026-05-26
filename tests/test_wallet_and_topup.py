import pytest
from httpx import AsyncClient, ASGITransport
from uuid import uuid4, UUID
from sqlalchemy import delete
from sqlalchemy.future import select

from app.main import app
from app.core.database import AsyncSessionLocal
from app.modules.users.models import User, UserRole
from app.modules.wallets.models import Wallet
from app.modules.transactions.models import PaymentTransaction, WalletTransaction, WebhookAuditLog, PaymentStatus
from app.core.security import get_password_hash, create_access_token
from app.core.config import settings

@pytest.mark.anyio
async def test_wallet_and_topup_flow():
    # 1. Setup mock user accounts
    buyer_id = uuid4()
    admin_id = uuid4()
    
    email_buyer = f"buyer_{uuid4()}@example.com"
    email_admin = f"admin_{uuid4()}@example.com"
    
    async with AsyncSessionLocal() as session:
        # Create BUYER User
        buyer = User(
            id=buyer_id,
            name="Test Wallet Buyer",
            email=email_buyer,
            password=get_password_hash("password123"),
            role=[UserRole.BUYER],
            is_active=True
        )
        session.add(buyer)
        
        # Create SUPER_ADMIN User
        admin = User(
            id=admin_id,
            name="Test Wallet Admin",
            email=email_admin,
            password=get_password_hash("password123"),
            role=[UserRole.SUPER_ADMIN],
            is_active=True
        )
        session.add(admin)
        
        await session.commit()
        
    # Generate tokens
    buyer_token = create_access_token(
        subject=buyer_id,
        session_id=str(uuid4()),
        client_type="BUYER_ANDROID",
        roles=["BUYER"],
        allowed_apps=["BUYER_ANDROID"]
    )
    
    admin_token = create_access_token(
        subject=admin_id,
        session_id=str(uuid4()),
        client_type="ADMIN_WEB",
        roles=["SUPER_ADMIN"],
        allowed_apps=["ADMIN_WEB"]
    )
    
    buyer_headers = {"Authorization": f"Bearer {buyer_token}"}
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            
            # --- TEST CASE 1: Lazy Wallet Creation on Balance Check ---
            res = await ac.get("/api/v1/wallet/balance", headers=buyer_headers)
            assert res.status_code == 200
            wallet_data = res.json()
            assert wallet_data["owner_id"] == str(buyer_id)
            assert float(wallet_data["balance"]) == 0.00
            
            wallet_uuid = wallet_data["id"]
            
            # Verify in DB
            async with AsyncSessionLocal() as session:
                wallet_db = await session.get(Wallet, UUID(wallet_uuid))
                assert wallet_db is not None
                assert wallet_db.balance == 0.00
            
            # --- TEST CASE 2: Validation of Minimum Top-Up Amount ---
            res = await ac.post("/api/v1/wallet/topups", headers=buyer_headers, json={"amount": 5000})
            assert res.status_code == 422
            
            # --- TEST CASE 3: Successful Top-Up Session Creation with REAL Xendit API ---
            # This makes a live Sandbox API call to Xendit
            res = await ac.post("/api/v1/wallet/topups", headers=buyer_headers, json={"amount": 50000})
            assert res.status_code == 200
            topup_data = res.json()
            assert topup_data["payment_link_url"].startswith("https://")
            assert topup_data["provider_reference_id"] is not None
            assert topup_data["status"] == "PENDING"
            assert float(topup_data["amount"]) == 50000.00
            
            reference_id = topup_data["external_id"]
            topup_uuid = topup_data["id"]
            real_session_id = topup_data["provider_reference_id"]

            # --- TEST CASE 3b: Status Polling Endpoint (PENDING) ---
            # Retrieve status using the status endpoint
            res = await ac.get(f"/api/v1/wallet/topups/{topup_uuid}", headers=buyer_headers)
            assert res.status_code == 200
            status_data = res.json()
            assert status_data["status"] == "PENDING"
            assert status_data["payment_link_url"] == topup_data["payment_link_url"]

            # --- TEST CASE 4: Webhook Security (Token Checking) ---
            webhook_payload = {
                "event": "payment_session.completed",
                "data": {
                    "id": real_session_id,
                    "reference_id": reference_id,
                    "status": "COMPLETED",
                    "amount": 50000.00
                }
            }
            res = await ac.post(
                "/api/v1/webhooks/xendit", 
                json=webhook_payload, 
                headers={"x-callback-token": "wrong_token"}
            )
            assert res.status_code == 401
            
            # --- TEST CASE 5: Webhook Processing (Credit Balance) ---
            # Process webhook using the real callback token
            res = await ac.post(
                "/api/v1/webhooks/xendit",
                json=webhook_payload,
                headers={"x-callback-token": settings.XENDIT_CALLBACK_TOKEN}
            )
            assert res.status_code == 200
            assert res.json()["status"] == "success"
            
            # Check wallet balance updated
            res = await ac.get("/api/v1/wallet/balance", headers=buyer_headers)
            assert res.status_code == 200
            assert float(res.json()["balance"]) == 50000.00

            # --- TEST CASE 5b: Status Polling Endpoint (PAID) ---
            # Polling again, status should now be PAID
            res = await ac.get(f"/api/v1/wallet/topups/{topup_uuid}", headers=buyer_headers)
            assert res.status_code == 200
            assert res.json()["status"] == "PAID"

            # --- TEST CASE 6: Webhook Idempotency ---
            # Resend webhook callback, balance should NOT increase again
            res = await ac.post(
                "/api/v1/webhooks/xendit",
                json=webhook_payload,
                headers={"x-callback-token": settings.XENDIT_CALLBACK_TOKEN}
            )
            assert res.status_code == 200
            
            # Verify balance remains 50000.00
            res = await ac.get("/api/v1/wallet/balance", headers=buyer_headers)
            assert res.status_code == 200
            assert float(res.json()["balance"]) == 50000.00

            # --- TEST CASE 7: Admin Sync Session (REAL Server-to-Server API GET call) ---
            # 1. Create a second topup session on Xendit
            res = await ac.post("/api/v1/wallet/topups", headers=buyer_headers, json={"amount": 25000})
            assert res.status_code == 200
            topup_data_2 = res.json()
            real_session_id_2 = topup_data_2["provider_reference_id"]
            
            # 2. Trigger Admin manual sync (makes a real GET request to Xendit Sandbox)
            # Since the payment hasn't been completed on Xendit, status is returned as "ACTIVE" (PENDING)
            res = await ac.get(f"/api/v1/wallet/sessions/{real_session_id_2}", headers=admin_headers)
            assert res.status_code == 200
            sync_data = res.json()
            assert sync_data["status"] == "PENDING"

    finally:
        # Clean up database entities manually
        async with AsyncSessionLocal() as session:
            # Delete Wallet Transactions
            await session.execute(delete(WalletTransaction).where(WalletTransaction.wallet_id == UUID(wallet_uuid)))
            # Delete Payment Transactions
            await session.execute(delete(PaymentTransaction).where(PaymentTransaction.wallet_id == UUID(wallet_uuid)))
            # Delete Webhook Logs
            await session.execute(delete(WebhookAuditLog).where(WebhookAuditLog.provider == "XENDIT"))
            # Delete Wallets
            await session.execute(delete(Wallet).where(Wallet.id == UUID(wallet_uuid)))
            # Delete Users
            await session.execute(delete(User).where(User.id.in_([buyer_id, admin_id])))
            
            await session.commit()
