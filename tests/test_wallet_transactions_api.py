import pytest
from httpx import AsyncClient, ASGITransport
from uuid import uuid4, UUID
from sqlalchemy import delete
from sqlalchemy.future import select
from datetime import datetime

from app.main import app
from app.core.database import AsyncSessionLocal
from app.modules.users.models import User, UserRole
from app.modules.wallets.models import Wallet
from app.modules.transactions.models import WalletTransaction, TransactionType, TransactionFlow, WalletTransactionStatus
from app.core.security import get_password_hash, create_access_token

@pytest.mark.anyio
async def test_wallet_transactions_pagination_and_details():
    # 1. Setup mock user accounts
    buyer1_id = uuid4()
    buyer2_id = uuid4()
    
    email_buyer1 = f"buyer1_{uuid4()}@example.com"
    email_buyer2 = f"buyer2_{uuid4()}@example.com"
    
    async with AsyncSessionLocal() as session:
        # Create Buyer 1
        buyer1 = User(
            id=buyer1_id,
            name="Buyer One",
            email=email_buyer1,
            password=get_password_hash("password123"),
            role=[UserRole.BUYER],
            is_active=True
        )
        session.add(buyer1)

        # Create Buyer 2
        buyer2 = User(
            id=buyer2_id,
            name="Buyer Two",
            email=email_buyer2,
            password=get_password_hash("password123"),
            role=[UserRole.BUYER],
            is_active=True
        )
        session.add(buyer2)
        
        # Create Wallet for Buyer 1
        wallet1 = Wallet(
            id=uuid4(),
            owner_type="USER",
            owner_id=buyer1_id,
            balance=100000.00,
            is_active=True
        )
        session.add(wallet1)

        # Create Wallet for Buyer 2
        wallet2 = Wallet(
            id=uuid4(),
            owner_type="USER",
            owner_id=buyer2_id,
            balance=50000.00,
            is_active=True
        )
        session.add(wallet2)
        
        await session.commit()

        # Add 5 transaction entries to Wallet 1
        for i in range(5):
            tx = WalletTransaction(
                id=uuid4(),
                wallet_id=wallet1.id,
                type=TransactionType.TOP_UP,
                transaction_flow=TransactionFlow.IN,
                amount=10000.00 * (i + 1),
                balance_before=10000.00 * i,
                balance_after=10000.00 * (i + 1),
                description=f"Top Up #{i+1}",
                status=WalletTransactionStatus.SUCCESS,
                created_at=datetime.utcnow()
            )
            session.add(tx)
            
        await session.commit()
        
    # Generate tokens
    buyer1_token = create_access_token(
        subject=buyer1_id,
        session_id=str(uuid4()),
        client_type="BUYER_ANDROID",
        roles=["BUYER"],
        allowed_apps=["BUYER_ANDROID"]
    )
    buyer2_token = create_access_token(
        subject=buyer2_id,
        session_id=str(uuid4()),
        client_type="BUYER_ANDROID",
        roles=["BUYER"],
        allowed_apps=["BUYER_ANDROID"]
    )
    
    buyer1_headers = {"Authorization": f"Bearer {buyer1_token}"}
    buyer2_headers = {"Authorization": f"Bearer {buyer2_token}"}
    
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # --- TEST CASE 1: Query Paginated List (Page 1, Size 3) ---
            res = await ac.get("/api/v1/wallet/transactions?page=1&size=3", headers=buyer1_headers)
            assert res.status_code == 200
            data = res.json()
            assert "items" in data
            assert data["total"] == 5
            assert len(data["items"]) == 3
            assert data["page"] == 1
            assert data["size"] == 3
            assert data["pages"] == 2
            
            # Check chronological sort (descending order)
            assert data["items"][0]["description"] == "Top Up #5"
            assert data["items"][1]["description"] == "Top Up #4"
            assert data["items"][2]["description"] == "Top Up #3"
            
            tx1_id = data["items"][0]["id"]
            
            # --- TEST CASE 2: Query Page 2 (Page 2, Size 3) ---
            res = await ac.get("/api/v1/wallet/transactions?page=2&size=3", headers=buyer1_headers)
            assert res.status_code == 200
            data2 = res.json()
            assert len(data2["items"]) == 2
            assert data2["items"][0]["description"] == "Top Up #2"
            assert data2["items"][1]["description"] == "Top Up #1"

            # --- TEST CASE 3: Get Transaction Details by ID ---
            res = await ac.get(f"/api/v1/wallet/transactions/{tx1_id}", headers=buyer1_headers)
            assert res.status_code == 200
            detail = res.json()
            assert detail["id"] == tx1_id
            assert detail["description"] == "Top Up #5"
            assert float(detail["amount"]) == 50000.00
            
            # --- TEST CASE 4: Security Access Check (Buyer 2 cannot view Buyer 1's details) ---
            res = await ac.get(f"/api/v1/wallet/transactions/{tx1_id}", headers=buyer2_headers)
            assert res.status_code == 403

    finally:
        # DB Cleanup
        async with AsyncSessionLocal() as session:
            await session.execute(delete(WalletTransaction).where(WalletTransaction.wallet_id.in_([wallet1.id, wallet2.id])))
            await session.execute(delete(Wallet).where(Wallet.id.in_([wallet1.id, wallet2.id])))
            await session.execute(delete(User).where(User.id.in_([buyer1_id, buyer2_id])))
            await session.commit()
