import httpx
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extensions import uuid7

from app.core.config import settings
from app.modules.wallets.service import WalletService
from app.modules.transactions.models import (
    PaymentTransaction,
    WalletTransaction,
    TransactionFlow,
    TransactionType,
    WebhookAuditLog,
    PaymentProvider,
    PaymentStatus,
    WalletTransactionStatus
)
from app.modules.transactions.repository import TransactionRepository

logger = logging.getLogger(__name__)

class TransactionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = TransactionRepository(db)
        self.wallet_service = WalletService(db)

    async def create_topup_session(self, user_id: str | UUID, amount: Decimal) -> PaymentTransaction:
        # 1. Retrieve or lazily create the user's wallet
        wallet = await self.wallet_service.get_or_create_user_wallet(user_id)

        # 2. Generate unique reference ID
        reference_id = f"topup_{uuid7().hex}"

        # 3. Create a pending internal PaymentTransaction record
        payment_tx = PaymentTransaction(
            wallet_id=wallet.id,
            provider=PaymentProvider.XENDIT,
            external_id=reference_id,
            amount=amount,
            status=PaymentStatus.PENDING
        )
        await self.repo.create_payment_transaction(payment_tx)

        # 4. Request session from Xendit
        xendit_payload = {
            "reference_id": reference_id,
            "session_type": "PAY",
            "mode": "PAYMENT_LINK",
            "amount": float(amount),
            "currency": "IDR",
            "country": "ID",
            "success_return_url": settings.XENDIT_SUCCESS_URL,
            "cancel_return_url": settings.XENDIT_CANCEL_URL,
            "description": "Wallet top up",
            "metadata": {
                "user_id": str(user_id),
                "topup_id": str(payment_tx.id)
            }
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.xendit.co/sessions",
                    json=xendit_payload,
                    auth=(settings.XENDIT_SECRET_KEY, ""),
                    timeout=15.0
                )
                
                if response.status_code not in (200, 201):
                    logger.error(f"Xendit Session creation failed: {response.text}")
                    # Update status to FAILED in case of provider failure
                    payment_tx.status = PaymentStatus.FAILED
                    await self.db.commit()
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="Failed to initiate payment session with Xendit."
                    )

                data = response.json()
                payment_tx.provider_reference_id = data.get("payment_session_id") or data.get("id")
                payment_tx.payment_link_url = data.get("payment_link_url")
                
                # Commit Xendit reference updates
                await self.db.commit()
                await self.db.refresh(payment_tx)
                
                return payment_tx

        except httpx.RequestError as e:
            logger.exception(f"HTTP request to Xendit failed: {e}")
            payment_tx.status = PaymentStatus.FAILED
            await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Connection to payment gateway timed out or failed."
            )

    async def process_webhook_payment(self, payload: dict, raw_payload_str: str) -> None:
        event_type = payload.get("event")
        
        # 1. Store the incoming webhook payload for audit
        audit_log = WebhookAuditLog(
            provider="XENDIT",
            event_type=event_type or "unknown",
            payload=raw_payload_str
        )
        await self.repo.create_webhook_audit_log(audit_log)

        # 2. Only handle payment_session.completed
        if event_type != "payment_session.completed":
            logger.info(f"Ignoring unhandled webhook event: {event_type}")
            return

        data = payload.get("data", {})
        session_status = data.get("status")
        reference_id = data.get("reference_id")
        session_id = data.get("id")
        
        if session_status != "COMPLETED":
            logger.info(f"Session {session_id} status is {session_status}. Skipping wallet credit.")
            return

        if not reference_id:
            logger.error("Webhook data missing reference_id.")
            return

        # 3. Retrieve internal payment transaction
        payment_tx = await self.repo.get_payment_transaction_by_ref(reference_id)
        if not payment_tx:
            logger.error(f"Payment transaction not found for reference_id: {reference_id}")
            return

        # 4. IDEMPOTENCY CHECK: If already PAID, do nothing
        if payment_tx.status == PaymentStatus.PAID:
            logger.info(f"Payment transaction {payment_tx.id} is already processed (PAID). Skipping.")
            return

        # 5. Complete payment and add wallet balance
        await self._complete_payment_transaction(payment_tx, session_id)

    async def sync_session_from_xendit(self, session_id: str) -> PaymentTransaction:
        # 1. Query Xendit server-to-server for session status
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.xendit.co/sessions/{session_id}",
                    auth=(settings.XENDIT_SECRET_KEY, ""),
                    timeout=15.0
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to fetch session from Xendit: {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail="Failed to retrieve session from payment gateway."
                    )
                
                data = response.json()
        except httpx.RequestError as e:
            logger.exception(f"HTTP request to sync session failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Connection to payment gateway failed."
            )

        session_status = data.get("status")
        reference_id = data.get("reference_id")

        # 2. Find payment transaction by session_id or reference_id
        payment_tx = await self.repo.get_payment_transaction_by_provider_ref(session_id)
        if not payment_tx and reference_id:
            payment_tx = await self.repo.get_payment_transaction_by_ref(reference_id)

        if not payment_tx:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Internal payment transaction record not found."
            )

        # 3. Check and process completion if Xendit is COMPLETED
        if session_status == "COMPLETED":
            if payment_tx.status != PaymentStatus.PAID:
                await self._complete_payment_transaction(payment_tx, session_id)
            else:
                logger.info(f"Transaction {payment_tx.id} is already PAID.")
        elif session_status in ("EXPIRED", "CANCELLED"):
            if payment_tx.status == PaymentStatus.PENDING:
                payment_tx.status = PaymentStatus.EXPIRED if session_status == "EXPIRED" else PaymentStatus.FAILED
                await self.db.commit()
                await self.db.refresh(payment_tx)
        
        return payment_tx

    async def get_topup_status(self, topup_id: UUID, user_id: UUID) -> PaymentTransaction:
        """
        Retrieve transaction status and verify ownership.
        """
        payment_tx = await self.repo.get_payment_transaction_by_id(topup_id)
        if not payment_tx:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Top-up transaction not found."
            )
        
        from sqlalchemy.future import select
        from app.modules.wallets.models import Wallet
        result = await self.db.execute(
            select(Wallet).filter(Wallet.id == payment_tx.wallet_id)
        )
        wallet = result.scalars().first()
        if not wallet or wallet.owner_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view this transaction."
            )

        # Automatically synchronize the transaction status from Xendit if the local status is PENDING.
        # This is incredibly helpful in local development environments where webhooks are not reachable.
        if payment_tx.status == PaymentStatus.PENDING and payment_tx.provider_reference_id:
            try:
                payment_tx = await self.sync_session_from_xendit(payment_tx.provider_reference_id)
            except Exception as e:
                logger.warning(f"Auto-sync during status check failed: {e}")
            
        return payment_tx

    async def get_wallet_transactions(
        self, user_id: UUID, page: int, size: int
    ) -> dict:
        wallet = await self.wallet_service.get_or_create_user_wallet(user_id)
        offset = (page - 1) * size
        limit = size

        items = await self.repo.get_wallet_transactions_paginated(wallet.id, offset, limit)
        total = await self.repo.count_wallet_transactions(wallet.id)
        pages = (total + size - 1) // size

        return {
            "items": [self._serialize_wallet_transaction(item) for item in items],
            "total": total,
            "page": page,
            "size": size,
            "pages": pages
        }

    async def get_wallet_transaction_detail(self, tx_id: UUID, user_id: UUID) -> WalletTransaction:
        from sqlalchemy.future import select
        from app.modules.wallets.models import Wallet

        wallet_tx = await self.repo.get_wallet_transaction_by_id(tx_id)
        if not wallet_tx:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transaction not found."
            )
        
        result = await self.db.execute(
            select(Wallet).filter(Wallet.id == wallet_tx.wallet_id)
        )
        wallet = result.scalars().first()
        if not wallet or wallet.owner_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view this transaction."
            )
            
        return self._serialize_wallet_transaction(wallet_tx)

    def _serialize_wallet_transaction(self, wallet_tx: WalletTransaction) -> dict:
        fuel_transaction = wallet_tx.fuel_transactions[0] if wallet_tx.fuel_transactions else None
        if fuel_transaction is not None:
            fuel_type_name = fuel_transaction.fuel_type.name if fuel_transaction.fuel_type else "Bahan Bakar"
            gas_station_name = fuel_transaction.gas_station.name if fuel_transaction.gas_station else "SPBU"
            description = f"{fuel_type_name} - {gas_station_name}"
            return {
                "id": wallet_tx.id,
                "wallet_id": wallet_tx.wallet_id,
                "type": TransactionType.FUEL_PURCHASE,
                "transaction_flow": TransactionFlow.OUT,
                "amount": wallet_tx.amount,
                "balance_before": wallet_tx.balance_before,
                "balance_after": wallet_tx.balance_after,
                "counterparty_wallet_id": wallet_tx.counterparty_wallet_id,
                "payment_transaction_id": wallet_tx.payment_transaction_id,
                "description": description,
                "status": wallet_tx.status,
                "created_at": wallet_tx.created_at,
                "tile_type": "FUEL",
                "fuel_type_name": fuel_type_name,
                "gas_station_name": gas_station_name,
                "liters": fuel_transaction.liters,
            }

        tile_type = None
        description = wallet_tx.description
        transaction_type = wallet_tx.type
        if wallet_tx.type == TransactionType.TOP_UP:
            tile_type = "TOP_UP"
            description = description or "Top Up Saldo"
        elif wallet_tx.type == TransactionType.TRANSFER:
            tile_type = "TRANSFER"
            description = description or "Transfer Saldo"

        return {
            "id": wallet_tx.id,
            "wallet_id": wallet_tx.wallet_id,
            "type": transaction_type,
            "transaction_flow": wallet_tx.transaction_flow,
            "amount": wallet_tx.amount,
            "balance_before": wallet_tx.balance_before,
            "balance_after": wallet_tx.balance_after,
            "counterparty_wallet_id": wallet_tx.counterparty_wallet_id,
            "payment_transaction_id": wallet_tx.payment_transaction_id,
            "description": description,
            "status": wallet_tx.status,
            "created_at": wallet_tx.created_at,
            "tile_type": tile_type,
            "fuel_type_name": None,
            "gas_station_name": None,
            "liters": None,
        }

    async def _complete_payment_transaction(self, payment_tx: PaymentTransaction, session_id: str) -> None:
        # Load associated wallet
        from sqlalchemy.future import select
        from app.modules.wallets.models import Wallet
        
        result = await self.db.execute(
            select(Wallet).filter(Wallet.id == payment_tx.wallet_id)
        )
        wallet = result.scalars().first()
        
        if not wallet:
            logger.error(f"Wallet {payment_tx.wallet_id} associated with transaction not found.")
            return

        # 1. Update Payment Transaction to PAID
        payment_tx.status = PaymentStatus.PAID
        if not payment_tx.provider_reference_id:
            payment_tx.provider_reference_id = session_id

        # 2. Update wallet balance
        balance_before = wallet.balance
        wallet.balance += payment_tx.amount
        balance_after = wallet.balance

        # 3. Create wallet transaction flow record
        wallet_tx = WalletTransaction(
            wallet_id=wallet.id,
            type=TransactionType.TOP_UP,
            transaction_flow=TransactionFlow.IN,
            amount=payment_tx.amount,
            balance_before=balance_before,
            balance_after=balance_after,
            payment_transaction_id=payment_tx.id,
            description="Wallet top up via Xendit",
            status=WalletTransactionStatus.SUCCESS
        )

        await self.repo.create_wallet_transaction(wallet_tx)
        await self.db.commit()
        await self.db.refresh(payment_tx)
        
        # Trigger Firebase Push Notification & Persist Notification
        try:
            from app.modules.notifications.service import NotificationService
            formatted_amount = f"Rp {int(payment_tx.amount):,}".replace(",", ".")
            await NotificationService.create_notification(
                db=self.db,
                user_id=wallet.owner_id,
                title="Top Up Berhasil",
                body=f"Top up sebesar {formatted_amount} berhasil masuk ke dompet Anda.",
                data={"type": "TOP_UP", "transaction_id": str(payment_tx.id)}
            )
        except Exception as push_err:
            logger.error(f"Failed to trigger Topup push notification: {push_err}")
        
        logger.info(
            f"Successfully credited top-up of IDR {payment_tx.amount} to wallet {wallet.id}. "
            f"Balance updated from {balance_before} to {balance_after}."
        )

    async def search_recipient_by_nik(self, current_user_id: UUID, recipient_nik: str) -> dict:
        from app.modules.users.models import BuyerProfile
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        stmt = select(BuyerProfile).options(selectinload(BuyerProfile.user)).filter(BuyerProfile.nik_snapshot == recipient_nik)
        res = await self.db.execute(stmt)
        profile = res.scalars().first()
        
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Penerima dengan NIK tersebut tidak ditemukan."
            )
            
        if profile.user_id == current_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Anda tidak dapat mentransfer saldo ke diri sendiri."
            )
            
        nik = profile.nik_snapshot
        nik_masked = f"{nik[:4]}****{nik[-4:]}" if len(nik) >= 8 else nik
        
        return {
            "name": profile.user.name,
            "nik_masked": nik_masked,
            "recipient_user_id": profile.user_id
        }

    async def execute_wallet_transfer(self, sender_user_id: UUID, request: Any) -> dict:
        from app.modules.users.models import BuyerProfile, User
        from app.core.security import verify_password
        from sqlalchemy import select

        # 1. Search for verified recipient
        recipient_info = await self.search_recipient_by_nik(sender_user_id, request.recipient_nik)
        recipient_user_id = recipient_info["recipient_user_id"]
        recipient_name = recipient_info["name"]

        # 2. Check Sender's profile and active PIN status
        stmt = select(BuyerProfile).filter(BuyerProfile.user_id == sender_user_id)
        res = await self.db.execute(stmt)
        sender_profile = res.scalars().first()
        
        if not sender_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profil pengirim tidak ditemukan."
            )

        if sender_profile.is_pin_active:
            if not request.pin:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="PIN transaksi diperlukan."
                )
            if not verify_password(request.pin, sender_profile.pin_hash):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="PIN transaksi salah."
                )

        # 3. Retrieve Wallets and check balances
        sender_wallet = await self.wallet_service.get_or_create_user_wallet(sender_user_id)
        recipient_wallet = await self.wallet_service.get_or_create_user_wallet(recipient_user_id)

        if sender_wallet.balance < request.amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Saldo Anda tidak mencukupi untuk melakukan transfer."
            )

        # 4. Atomic balance adjustments
        sender_before = sender_wallet.balance
        sender_wallet.balance -= request.amount
        sender_after = sender_wallet.balance

        recipient_before = recipient_wallet.balance
        recipient_wallet.balance += request.amount
        recipient_after = recipient_wallet.balance

        # 5. Create transaction log records
        sender_tx = WalletTransaction(
            wallet_id=sender_wallet.id,
            type=TransactionType.TRANSFER,
            transaction_flow=TransactionFlow.OUT,
            amount=request.amount,
            balance_before=sender_before,
            balance_after=sender_after,
            counterparty_wallet_id=recipient_wallet.id,
            description=f"Transfer ke {recipient_name}",
            status=WalletTransactionStatus.SUCCESS
        )

        stmt_sender = select(User).filter(User.id == sender_user_id)
        res_sender = await self.db.execute(stmt_sender)
        sender_user = res_sender.scalars().first()
        sender_name = sender_user.name if sender_user else "Pengirim"

        recipient_tx = WalletTransaction(
            wallet_id=recipient_wallet.id,
            type=TransactionType.TRANSFER,
            transaction_flow=TransactionFlow.IN,
            amount=request.amount,
            balance_before=recipient_before,
            balance_after=recipient_after,
            counterparty_wallet_id=sender_wallet.id,
            description=f"Transfer dari {sender_name}",
            status=WalletTransactionStatus.SUCCESS
        )

        await self.repo.create_wallet_transaction(sender_tx)
        await self.repo.create_wallet_transaction(recipient_tx)
        await self.db.commit()

        # Trigger Firebase Push Notifications & Persist Notifications
        try:
            from app.modules.notifications.service import NotificationService
            formatted_amount = f"Rp {int(request.amount):,}".replace(",", ".")
            
            # 1. Notify Sender
            await NotificationService.create_notification(
                db=self.db,
                user_id=sender_user.id,
                title="Transfer Berhasil",
                body=f"Anda berhasil mengirimkan {formatted_amount} ke {recipient_name}.",
                data={"type": "TRANSFER_OUT", "transaction_id": str(sender_tx.id)}
            )
                
            # 2. Notify Recipient
            await NotificationService.create_notification(
                db=self.db,
                user_id=recipient_wallet.owner_id,
                title="Saldo Masuk",
                body=f"Anda menerima transfer sebesar {formatted_amount} dari {sender_name}.",
                data={"type": "TRANSFER_IN", "transaction_id": str(recipient_tx.id)}
            )
        except Exception as push_err:
            logger.error(f"Failed to trigger transfer push notification: {push_err}")

        return {
            "message": "Transfer berhasil dilakukan.",
            "amount": float(request.amount),
            "recipient_name": recipient_name
        }

