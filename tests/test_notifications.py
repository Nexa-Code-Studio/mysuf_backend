import pytest
from httpx import AsyncClient, ASGITransport
from uuid import uuid4, UUID
from unittest.mock import patch, AsyncMock
from sqlalchemy import delete
from sqlalchemy.future import select

from app.main import app
from app.core.database import AsyncSessionLocal
from app.modules.users.models import User, UserRole
from app.modules.wallets.models import Wallet
from app.modules.transactions.models import PaymentTransaction, WalletTransaction, WebhookAuditLog, PaymentStatus, PaymentProvider
from app.core.security import get_password_hash, create_access_token
from app.core.config import settings

@pytest.mark.anyio
async def test_notifications_integration_flow():
    # 1. Setup mock user accounts (Sender and Recipient)
    sender_id = uuid4()
    recipient_id = uuid4()
    
    sender_email = f"sender_{uuid4()}@example.com"
    recipient_email = f"recipient_{uuid4()}@example.com"
    
    async with AsyncSessionLocal() as session:
        # Create Sender
        sender = User(
            id=sender_id,
            name="Sender Warga",
            email=sender_email,
            password=get_password_hash("password123"),
            role=[UserRole.BUYER],
            is_active=True
        )
        session.add(sender)
        
        # Create Recipient
        recipient = User(
            id=recipient_id,
            name="Recipient Warga",
            email=recipient_email,
            password=get_password_hash("password123"),
            role=[UserRole.BUYER],
            is_active=True
        )
        session.add(recipient)
        
        await session.commit()

    # Generate token
    sender_token = create_access_token(
        subject=sender_id,
        session_id=str(uuid4()),
        client_type="BUYER_ANDROID",
        roles=["BUYER"],
        allowed_apps=["BUYER_ANDROID"]
    )
    
    sender_headers = {"Authorization": f"Bearer {sender_token}"}
    wallet_uuid = None
    
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # --- TEST CASE 1: Device Token Update Endpoint ---
            fcm_token_val = "test_fcm_device_token_xyz_123"
            res = await ac.post(
                "/api/v1/users/me/device-token",
                headers=sender_headers,
                json={"token": fcm_token_val}
            )
            assert res.status_code == 200
            assert res.json()["message"] == "Token perangkat berhasil didaftarkan."
            
            # Verify token saved in database
            async with AsyncSessionLocal() as session:
                user_db = await session.get(User, sender_id)
                assert user_db is not None
                assert user_db.fcm_token == fcm_token_val

            # --- TEST CASE 2: Top Up Notification Trigger ---
            # Mock FCMService.send_push_notification to verify it is called on complete payment transaction
            with patch("app.core.notifications.FCMService.send_push_notification", new_callable=AsyncMock) as mock_send:
                # Trigger lazy wallet creation via API
                res_balance = await ac.get("/api/v1/wallet/balance", headers=sender_headers)
                assert res_balance.status_code == 200
                wallet_uuid = UUID(res_balance.json()["id"])
                
                async with AsyncSessionLocal() as session:
                    payment_tx = PaymentTransaction(
                        id=uuid4(),
                        wallet_id=wallet_uuid,
                        amount=50000.00,
                        provider=PaymentProvider.XENDIT,
                        status=PaymentStatus.PENDING,
                        provider_reference_id="session_123_notif",
                        external_id="ext_123_notif"
                    )
                    session.add(payment_tx)
                    await session.commit()
                
                # Trigger webhook payment completion
                webhook_payload = {
                    "event": "payment_session.completed",
                    "data": {
                        "id": "session_123_notif",
                        "reference_id": "ext_123_notif",
                        "status": "COMPLETED",
                        "amount": 50000.00
                    }
                }
                res = await ac.post(
                    "/api/v1/webhooks/xendit",
                    json=webhook_payload,
                    headers={"x-callback-token": settings.XENDIT_CALLBACK_TOKEN}
                )
                assert res.status_code == 200
                
                # Check that send_push_notification was called with successful topup title/body
                mock_send.assert_called_once()
                call_args = mock_send.call_args[1]
                assert call_args["token"] == fcm_token_val
                assert "Top Up Berhasil" in call_args["title"]
                assert "Rp 50.000" in call_args["body"]

                # --- TEST CASE 3: Persistent Notifications API Endpoints ---
                # 1. List notifications (should have 1 item from the Top Up)
                res_list = await ac.get("/api/v1/notifications", headers=sender_headers)
                assert res_list.status_code == 200
                data_list = res_list.json()
                assert data_list["total"] == 1
                notif_item = data_list["items"][0]
                assert notif_item["title"] == "Top Up Berhasil"
                assert notif_item["is_read"] is False
                assert notif_item["data"]["type"] == "TOP_UP"
                
                notif_uuid = notif_item["id"]
                
                # 2. Mark notification as read
                res_read = await ac.post(f"/api/v1/notifications/{notif_uuid}/read", headers=sender_headers)
                assert res_read.status_code == 200
                assert res_read.json()["is_read"] is True
                
                # Verify status in database
                async with AsyncSessionLocal() as session:
                    from app.modules.notifications.models import Notification
                    notif_db = await session.get(Notification, UUID(notif_uuid))
                    assert notif_db is not None
                    assert notif_db.is_read is True

                # 3. Create another notification to test mark all as read
                from app.modules.notifications.service import NotificationService
                async with AsyncSessionLocal() as session:
                    await NotificationService.create_notification(
                        db=session,
                        user_id=sender_id,
                        title="Transfer Berhasil",
                        body="Anda mengirim transfer...",
                        data={"type": "TRANSFER_OUT"}
                    )
                
                # Verify we have 2 notifications total (1 read, 1 unread)
                res_list = await ac.get("/api/v1/notifications", headers=sender_headers)
                assert res_list.status_code == 200
                assert res_list.json()["total"] == 2
                
                # Call read-all
                res_read_all = await ac.post("/api/v1/notifications/read-all", headers=sender_headers)
                assert res_read_all.status_code == 200
                assert res_read_all.json()["count"] == 1 # 1 was unread, 1 was already read
                
                # Verify all are read now
                res_list = await ac.get("/api/v1/notifications", headers=sender_headers)
                assert res_list.status_code == 200
                for item in res_list.json()["items"]:
                    assert item["is_read"] is True

    finally:
        # Clean up database entities
        from app.modules.notifications.models import Notification
        async with AsyncSessionLocal() as session:
            await session.execute(delete(Notification).where(Notification.user_id.in_([sender_id, recipient_id])))
            if wallet_uuid:
                await session.execute(delete(WalletTransaction).where(WalletTransaction.wallet_id == wallet_uuid))
                await session.execute(delete(PaymentTransaction).where(PaymentTransaction.wallet_id == wallet_uuid))
            await session.execute(delete(WebhookAuditLog).where(WebhookAuditLog.provider == "XENDIT"))
            await session.execute(delete(Wallet).where(Wallet.owner_id.in_([sender_id, recipient_id])))
            await session.execute(delete(User).where(User.id.in_([sender_id, recipient_id])))
            await session.commit()
