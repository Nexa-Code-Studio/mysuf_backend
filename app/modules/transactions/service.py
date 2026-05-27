import httpx
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extensions import uuid7

from app.core.config import settings
from app.modules.users.repository import UserRepository
from app.modules.wallets.service import WalletService
from app.modules.transactions.models import (
    CashierScanEvent,
    CashierScanMethod,
    CashierScanResult,
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
XENDIT_API_VERSION = "2024-11-11"


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    R = 6371.0  # Earth's radius in kilometers
    
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c


class TransactionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = TransactionRepository(db)
        self.user_repo = UserRepository(db)
        self.wallet_service = WalletService(db)

    @staticmethod
    def _currency_amount(value: Decimal) -> Decimal:
        return Decimal(value).quantize(Decimal("0.01"))

    def _build_fuel_purchase_pricing(
        self,
        *,
        request_liters: Decimal,
        fuel_type: Any,
        subsidy_quota: Any | None,
    ) -> dict[str, Any]:
        market_price = Decimal(fuel_type.price_per_liter)
        subsidized_price = Decimal(fuel_type.subsidy_price_per_liter) if fuel_type.subsidy_price_per_liter is not None else None

        subsidized_liters = Decimal("0")
        non_subsidized_liters = Decimal(request_liters)

        if subsidy_quota is not None and subsidized_price is not None:
            quota_liters = Decimal(subsidy_quota.quota_liters)
            used_liters = Decimal(subsidy_quota.used_liters)
            remaining_quota = max(Decimal("0"), quota_liters - used_liters)
            subsidized_liters = min(remaining_quota, Decimal(request_liters))
            non_subsidized_liters = Decimal(request_liters) - subsidized_liters

        total_amount = (
            (subsidized_liters * subsidized_price) if subsidized_price is not None else Decimal("0")
        ) + (non_subsidized_liters * market_price)

        return {
            "subsidized_liters": subsidized_liters,
            "non_subsidized_liters": non_subsidized_liters,
            "total_amount": self._currency_amount(total_amount),
            "market_price_per_liter": self._currency_amount(market_price),
            "subsidized_price_per_liter": self._currency_amount(subsidized_price) if subsidized_price is not None else None,
        }

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

        if payment_tx.fuel_transaction_id:
            fuel_tx = await self.repo.get_fuel_transaction_by_id(payment_tx.fuel_transaction_id)
            if not fuel_tx:
                logger.error(f"Fuel transaction not found for payment transaction {payment_tx.id}.")
                return

            if session_status != "COMPLETED":
                logger.info(
                    f"Fuel payment session {session_id} status is {session_status}. Skipping completion."
                )
                return

            await self._complete_qris_fuel_purchase(fuel_tx, payment_tx)
            return

        # 4. IDEMPOTENCY CHECK: If already PAID, do nothing
        if payment_tx.status == PaymentStatus.PAID:
            logger.info(f"Payment transaction {payment_tx.id} is already processed (PAID). Skipping.")
            return

        # 5. Complete payment and add wallet balance
        await self._complete_payment_transaction(payment_tx, session_id)

    async def sync_session_from_xendit(self, session_id: str) -> PaymentTransaction:
        from app.modules.transactions.models import FuelTransactionStatus

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

        fuel_tx = None
        if payment_tx.fuel_transaction_id:
            fuel_tx = await self.repo.get_fuel_transaction_by_id(payment_tx.fuel_transaction_id)
            if not fuel_tx:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Internal fuel transaction record not found.",
                )

        # 3. Check and process completion if Xendit is COMPLETED
        if session_status == "COMPLETED":
            if fuel_tx is not None:
                await self._complete_qris_fuel_purchase(fuel_tx, payment_tx)
            elif payment_tx.status != PaymentStatus.PAID:
                await self._complete_payment_transaction(payment_tx, session_id)
            else:
                logger.info(f"Transaction {payment_tx.id} is already PAID.")
        elif session_status in ("EXPIRED", "CANCELLED"):
            if fuel_tx is not None:
                await self._fail_qris_fuel_purchase(
                    fuel_tx,
                    payment_tx,
                    PaymentStatus.EXPIRED if session_status == "EXPIRED" else PaymentStatus.FAILED,
                    FuelTransactionStatus.CANCELLED if session_status == "EXPIRED" else FuelTransactionStatus.FAILED,
                )
            elif payment_tx.status == PaymentStatus.PENDING:
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
        buyer_profile = await self.user_repo.get_buyer_profile_by_user_id(user_id)

        wallet_transactions = await self.repo.get_wallet_transactions_for_wallet(wallet.id)
        fuel_transactions = (
            await self.repo.get_fuel_transactions_for_buyer_profile(buyer_profile.id)
            if buyer_profile else []
        )

        items = [
            self._serialize_wallet_transaction(item)
            for item in wallet_transactions
        ]
        items.extend(
            self._serialize_fuel_transaction_for_history(item, wallet.id)
            for item in fuel_transactions
        )
        items.sort(key=lambda item: (item["created_at"], str(item["id"])), reverse=True)

        total = len(items)
        offset = (page - 1) * size
        paginated_items = items[offset: offset + size]
        pages = (total + size - 1) // size if total else 0

        return {
            "items": paginated_items,
            "total": total,
            "page": page,
            "size": size,
            "pages": pages
        }

    def _normalize_datetime(self, dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    async def get_cashier_transaction_history(
        self,
        current_user,
        *,
        q: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        cursor: str | None = None,
        limit: int = 20,
        include_summary: bool = True,
    ) -> dict:
        date_from = self._normalize_datetime(date_from)
        date_to = self._normalize_datetime(date_to)

        cursor_created_at: datetime | None = None
        cursor_id: UUID | None = None
        if cursor:
            cursor_created_at, cursor_id = self._parse_cursor(cursor)

        transactions = await self.repo.get_cashier_fuel_transactions(
            current_user.id,
            date_from=date_from,
            date_to=date_to,
            search=q,
            cursor_created_at=cursor_created_at,
            cursor_id=cursor_id,
            limit=limit + 1,
        )
        has_more = len(transactions) > limit
        items = transactions[:limit]
        next_cursor = self._build_cursor(items[-1]) if has_more and items else None

        summary = None
        if include_summary:
            summary = await self.repo.summarize_cashier_fuel_transactions(
                current_user.id,
                date_from=date_from,
                date_to=date_to,
                search=q,
            )

        return {
            "summary": summary,
            "items": [self._serialize_cashier_transaction_item(item, current_user.name) for item in items],
            "next_cursor": next_cursor,
            "has_more": has_more,
        }

    async def get_cashier_recent_scans(
        self,
        current_user,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        cursor: str | None = None,
        limit: int = 10,
    ) -> dict:
        date_from = self._normalize_datetime(date_from)
        date_to = self._normalize_datetime(date_to)

        cursor_created_at: datetime | None = None
        cursor_id: UUID | None = None
        if cursor:
            cursor_created_at, cursor_id = self._parse_cursor(cursor)

        scans = await self.repo.get_recent_cashier_scan_events(
            current_user.id,
            date_from=date_from,
            date_to=date_to,
            cursor_created_at=cursor_created_at,
            cursor_id=cursor_id,
            limit=limit + 1,
        )
        has_more = len(scans) > limit
        items = scans[:limit]
        next_cursor = self._build_cursor(items[-1]) if has_more and items else None

        return {
            "items": [self._serialize_cashier_scan_item(item) for item in items],
            "next_cursor": next_cursor,
            "has_more": has_more,
        }

    async def get_cashier_performance(
        self,
        current_user,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        recent_limit: int = 5,
    ) -> dict:
        date_from = self._normalize_datetime(date_from)
        date_to = self._normalize_datetime(date_to)

        if date_from is None or date_to is None:
            now = datetime.utcnow()
            date_from = datetime(now.year, now.month, now.day)
            date_to = date_from + timedelta(days=1)

        summary = await self.repo.summarize_cashier_performance(
            current_user.id,
            date_from=date_from,
            date_to=date_to,
        )
        recent_items = await self.repo.get_cashier_fuel_transactions(
            current_user.id,
            date_from=date_from,
            date_to=date_to,
            limit=recent_limit,
        )

        return {
            "summary": summary,
            "recent_transactions": [
                self._serialize_cashier_transaction_item(item, current_user.name)
                for item in recent_items
            ],
        }

    async def get_wallet_transaction_detail(self, tx_id: UUID, user_id: UUID) -> WalletTransaction:
        from sqlalchemy.future import select
        from app.modules.wallets.models import Wallet

        wallet_tx = await self.repo.get_wallet_transaction_by_id(tx_id)
        if wallet_tx:
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

        fuel_tx = await self.repo.get_fuel_transaction_by_id(tx_id)
        if fuel_tx and fuel_tx.buyer_profile and fuel_tx.buyer_profile.user_id == user_id:
            wallet = await self.wallet_service.get_or_create_user_wallet(user_id)
            return self._serialize_fuel_transaction_for_history(fuel_tx, wallet.id)

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found."
        )

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
                "payment_method": fuel_transaction.payment_method,
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
            "payment_method": None,
            "description": description,
            "status": wallet_tx.status,
            "created_at": wallet_tx.created_at,
            "tile_type": tile_type,
            "fuel_type_name": None,
            "gas_station_name": None,
            "liters": None,
        }

    def _serialize_fuel_transaction_for_history(self, fuel_tx: Any, wallet_id: UUID) -> dict:
        from app.modules.transactions.models import FuelTransactionStatus, PaymentMethod, TransactionFlow, TransactionType, WalletTransactionStatus

        fuel_type_name = fuel_tx.fuel_type.name if fuel_tx.fuel_type else "Bahan Bakar"
        gas_station_name = fuel_tx.gas_station.name if fuel_tx.gas_station else "SPBU"
        payment_transaction = fuel_tx.payment_transactions[0] if fuel_tx.payment_transactions else None
        status_map = {
            FuelTransactionStatus.COMPLETED: WalletTransactionStatus.SUCCESS,
            FuelTransactionStatus.PENDING: WalletTransactionStatus.PENDING,
            FuelTransactionStatus.CANCELLED: WalletTransactionStatus.FAILED,
            FuelTransactionStatus.FAILED: WalletTransactionStatus.FAILED,
        }

        return {
            "id": fuel_tx.id,
            "wallet_id": wallet_id,
            "type": TransactionType.FUEL_PURCHASE,
            "transaction_flow": TransactionFlow.OUT,
            "amount": fuel_tx.total_amount,
            "balance_before": Decimal("0"),
            "balance_after": Decimal("0"),
            "counterparty_wallet_id": None,
            "payment_transaction_id": payment_transaction.id if payment_transaction else None,
            "payment_method": fuel_tx.payment_method,
            "description": f"{fuel_type_name} - {gas_station_name}",
            "status": status_map.get(fuel_tx.transaction_status, WalletTransactionStatus.SUCCESS),
            "created_at": fuel_tx.created_at,
            "tile_type": "FUEL",
            "fuel_type_name": fuel_type_name,
            "gas_station_name": gas_station_name,
            "liters": fuel_tx.liters,
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

    async def _evaluate_fraud(
        self,
        buyer_profile,
        vehicle_ownership,
        current_station,
        liters: Decimal
    ) -> dict:
        from app.modules.transactions.models import FuelTransaction, FuelTransactionStatus
        from app.modules.gas_stations.models import GasStation
        from sqlalchemy import select
        from datetime import datetime

        detected_frauds = []
        risk_score = 0

        # 1. RAPID_PURCHASE & MULTI_LOCATION_ABUSE
        # Get the most recent completed transaction for this vehicle
        stmt_recent = select(FuelTransaction).filter(
            FuelTransaction.vehicle_ownership_id == vehicle_ownership.id,
            FuelTransaction.transaction_status == FuelTransactionStatus.COMPLETED
        ).order_by(FuelTransaction.created_at.desc()).limit(1)
        res_recent = await self.db.execute(stmt_recent)
        most_recent_tx = res_recent.scalars().first()

        if most_recent_tx:
            delta = datetime.utcnow() - most_recent_tx.created_at
            minutes = delta.total_seconds() / 60.0

            if minutes < 30.0:
                # RAPID PURCHASE
                risk_score += 25
                detected_frauds.append({
                    "type": "RAPID_PURCHASE",
                    "points": 25,
                    "reason": f"Pembelian ulang kendaraan {vehicle_ownership.plate_number_snapshot} terjadi {int(minutes)} menit setelah transaksi sebelumnya."
                })

                # MULTI LOCATION ABUSE
                stmt_prev_station = select(GasStation).filter(GasStation.id == most_recent_tx.gas_station_id)
                res_prev_station = await self.db.execute(stmt_prev_station)
                prev_station = res_prev_station.scalars().first()

                if prev_station:
                    distance = haversine_distance(
                        current_station.latitude, current_station.longitude,
                        prev_station.latitude, prev_station.longitude
                    )
                    if distance > 30.0:
                        risk_score += 40
                        detected_frauds.append({
                            "type": "MULTI_LOCATION_ABUSE",
                            "points": 40,
                            "reason": f"Perpindahan kendaraan {vehicle_ownership.plate_number_snapshot} sejauh {distance:.1f} km dalam {int(minutes)} menit tidak realistis."
                        })

        # 2. HOUSEHOLD_ABUSE (Vehicle Count & Daily Volume)
        if buyer_profile.kk_id:
            from app.modules.users.models import BuyerProfile
            # Get all profiles in same KK
            stmt_kk = select(BuyerProfile.id).filter(BuyerProfile.kk_id == buyer_profile.kk_id)
            res_kk = await self.db.execute(stmt_kk)
            kk_profile_ids = res_kk.scalars().all()

            # Get today's transactions for the whole KK
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            stmt_family_tx = select(FuelTransaction).filter(
                FuelTransaction.buyer_profile_id.in_(kk_profile_ids),
                FuelTransaction.transaction_status == FuelTransactionStatus.COMPLETED,
                FuelTransaction.is_subsidized == True,
                FuelTransaction.created_at >= today_start
            )
            res_family_tx = await self.db.execute(stmt_family_tx)
            family_txs = res_family_tx.scalars().all()

            # Unique vehicle count
            unique_vehicles = set(tx.vehicle_ownership_id for tx in family_txs)
            unique_vehicles.add(vehicle_ownership.id)
            if len(unique_vehicles) > 3:
                risk_score += 35
                detected_frauds.append({
                    "type": "HOUSEHOLD_ABUSE",
                    "points": 35,
                    "reason": f"Lebih dari 3 kendaraan dalam KK {buyer_profile.kk_id} melakukan transaksi subsidi pada hari yang sama."
                })

            # Daily liters limit (120 liters)
            family_liters_today = sum(Decimal(tx.liters) for tx in family_txs)
            if family_liters_today + liters > 120:
                risk_score += 35
                detected_frauds.append({
                    "type": "HOUSEHOLD_ABUSE",
                    "points": 35,
                    "reason": f"Konsumsi harian KK {buyer_profile.kk_id} mencapai {float(family_liters_today + liters):.2f} liter dan melewati ambang 120 liter."
                })

        # Risk Level & Actions mapping
        risk_level = "SAFE"
        action = "ALLOW TRANSACTION"
        if risk_score > 100:
            risk_level = "CRITICAL"
            action = "BLOCK ACCOUNT"
        elif risk_score >= 61:
            risk_level = "HIGH_RISK"
            action = "FREEZE ACCOUNT"
        elif risk_score >= 31:
            risk_level = "SUSPICIOUS"
            action = "WARNING"

        return {
            "detected_frauds": detected_frauds,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "action": action
        }

    async def _create_fraud_log(
        self,
        buyer_profile: Any,
        vehicle_ownership: Any,
        current_station: Any,
        fraud_assessment: dict,
        fuel_transaction_id: Any = None
    ) -> None:
        from app.modules.transactions.models import FraudLog, FraudRiskLevel, FraudActionTaken, FraudCaseStatus
        from uuid_extensions import uuid7
        from datetime import datetime
        from typing import Any

        # Generate readable unique case_id
        from uuid import uuid4
        case_id = f"FR-{datetime.utcnow().strftime('%y%m%d')}-{uuid4().hex[:4].upper()}"

        # Map risk level
        risk_score = fraud_assessment.get("risk_score", 0)
        if risk_score > 100:
            risk_level = FraudRiskLevel.CRITICAL
        elif risk_score >= 61:
            risk_level = FraudRiskLevel.HIGH_RISK
        elif risk_score >= 31:
            risk_level = FraudRiskLevel.SUSPICIOUS
        else:
            risk_level = FraudRiskLevel.SAFE

        # Map action taken
        action = fraud_assessment.get("action", "ALLOW TRANSACTION")
        if action == "BLOCK ACCOUNT":
            action_taken = FraudActionTaken.BLOCK_ACCOUNT
        elif action == "FREEZE ACCOUNT":
            action_taken = FraudActionTaken.FREEZE_ACCOUNT
        elif action == "WARNING":
            action_taken = FraudActionTaken.WARNING
        else:
            action_taken = FraudActionTaken.ALLOW_TRANSACTION

        # NIK snapshot masking
        raw_nik = getattr(buyer_profile, "nik_snapshot", None)
        nik_snapshot = self._mask_nik(raw_nik) if raw_nik else None

        fraud_log = FraudLog(
            id=uuid7(),
            case_id=case_id,
            fuel_transaction_id=fuel_transaction_id,
            gas_station_id=current_station.id,
            buyer_profile_id=buyer_profile.id if buyer_profile else None,
            vehicle_ownership_id=vehicle_ownership.id if vehicle_ownership else None,
            plate_number_snapshot=getattr(vehicle_ownership, "plate_number_snapshot", "N/A"),
            nik_snapshot=nik_snapshot,
            risk_score=risk_score,
            risk_level=risk_level,
            action_taken=action_taken,
            detected_frauds=fraud_assessment.get("detected_frauds", []),
            status=FraudCaseStatus.PENDING
        )
        self.db.add(fraud_log)

    async def log_cashier_scan_event(
        self,
        *,
        cashier_user,
        lookup_method: CashierScanMethod,
        lookup_value: str,
        result: CashierScanResult,
        buyer_profile=None,
        vehicle_ownership=None,
        fuel_transaction=None,
        error_message: str | None = None,
    ) -> None:
        scan_event = CashierScanEvent(
            cashier_user_id=cashier_user.id,
            gas_station_id=getattr(cashier_user, "gas_station_id", None),
            lookup_method=lookup_method,
            lookup_value=lookup_value,
            result=result,
            buyer_profile_id=getattr(buyer_profile, "id", None),
            vehicle_ownership_id=getattr(vehicle_ownership, "id", None),
            fuel_transaction_id=getattr(fuel_transaction, "id", None),
            error_message=error_message,
        )
        await self.repo.create_cashier_scan_event(scan_event)

    def _parse_cursor(self, cursor: str) -> tuple[datetime, UUID]:
        created_at_raw, cursor_id_raw = cursor.split("|", 1)
        created_at = datetime.fromisoformat(created_at_raw)
        return created_at, UUID(cursor_id_raw)

    def _build_cursor(self, item: Any) -> str:
        created_at = item.created_at if hasattr(item, "created_at") else item["created_at"]
        item_id = item.id if hasattr(item, "id") else item["id"]
        return f"{created_at.isoformat()}|{item_id}"

    def _mask_nik(self, nik: str | None) -> str | None:
        if not nik:
            return None
        if len(nik) <= 8:
            return nik
        return f"{nik[:4]}****{nik[-4:]}"

    def _serialize_cashier_transaction_item(self, fuel_tx: Any, cashier_name: str | None) -> dict:
        buyer_name = None
        buyer_nik = None
        if fuel_tx.buyer_profile and fuel_tx.buyer_profile.user:
            buyer_name = fuel_tx.buyer_profile.user.name
            buyer_nik = fuel_tx.buyer_profile.nik_snapshot
        elif fuel_tx.company_name_snapshot:
            buyer_name = fuel_tx.company_name_snapshot
            buyer_nik = fuel_tx.nik_snapshot

        return {
            "id": fuel_tx.id,
            "created_at": fuel_tx.created_at,
            "transaction_status": fuel_tx.transaction_status,
            "payment_method": fuel_tx.payment_method,
            "plate_number_snapshot": fuel_tx.plate_number_snapshot,
            "nik_snapshot": fuel_tx.nik_snapshot,
            "buyer_name": buyer_name,
            "fuel_name": fuel_tx.fuel_type.name if fuel_tx.fuel_type else "Bahan Bakar",
            "liters": float(fuel_tx.liters),
            "total_amount": float(fuel_tx.total_amount),
            "gas_station_name": fuel_tx.gas_station.name if fuel_tx.gas_station else "SPBU",
            "cashier_name": cashier_name,
            "buyer_nik_masked": self._mask_nik(buyer_nik),
        }

    def _serialize_cashier_scan_item(self, scan_event: Any) -> dict:
        buyer_name = None
        nik = None
        if scan_event.buyer_profile and scan_event.buyer_profile.user:
            buyer_name = scan_event.buyer_profile.user.name
            nik = scan_event.buyer_profile.nik_snapshot

        return {
            "id": scan_event.id,
            "created_at": scan_event.created_at,
            "lookup_method": scan_event.lookup_method,
            "result": scan_event.result,
            "lookup_value": scan_event.lookup_value,
            "buyer_name": buyer_name,
            "nik_masked": self._mask_nik(nik),
            "error_message": scan_event.error_message,
        }

    def _parse_provider_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    def _extract_qr_string(self, actions: list[dict[str, Any]] | None) -> str | None:
        if not actions:
            return None
        for action in actions:
            if (
                action.get("type") == "PRESENT_TO_CUSTOMER"
                and action.get("descriptor") == "QR_STRING"
            ):
                value = action.get("value")
                if isinstance(value, str) and value.strip():
                    return value
        return None

    async def _prepare_fuel_purchase_context(
        self,
        current_user: Any,
        request: Any,
        *,
        require_wallet_payment: bool,
    ) -> dict[str, Any]:
        from sqlalchemy import select
        from app.core.security import verify_password
        from app.modules.fuels.models import FuelType, SubsidyType
        from app.modules.gas_stations.models import GasStation
        from app.modules.subsidies.models import EligibilityStatus
        from app.modules.subsidies.service import SubsidyService
        from app.modules.users.models import BuyerProfile, VerificationStatus
        from app.modules.vehicles.models import VehicleOwnership, VehicleUsageType
        from app.modules.wallets.models import OwnerType, Wallet

        if not current_user.gas_station_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Petugas kasir tidak terasosiasi dengan SPBU manapun.",
            )

        res_station = await self.db.execute(
            select(GasStation).filter(GasStation.id == current_user.gas_station_id),
        )
        current_station = res_station.scalars().first()
        if not current_station:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="SPBU tempat kasir bertugas tidak ditemukan.",
            )

        from sqlalchemy.orm import selectinload
        res_profile = await self.db.execute(
            select(BuyerProfile)
            .options(selectinload(BuyerProfile.user))
            .filter(BuyerProfile.nik_snapshot == request.nik),
        )
        buyer_profile = res_profile.scalars().first()
        if not buyer_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profil pembeli dengan NIK tersebut tidak ditemukan.",
            )

        if buyer_profile.verification_status == VerificationStatus.REJECTED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Transaksi ditolak. Akun pembeli ini telah diblokir permanen oleh sistem keamanan.",
            )
        if buyer_profile.verification_status == VerificationStatus.UNVERIFIED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Transaksi ditolak. Akun pembeli ini telah dibekukan sementara oleh sistem keamanan.",
            )

        wallet = None
        if require_wallet_payment:
            if buyer_profile.is_pin_active:
                if not request.pin:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="PIN transaksi e-wallet KTP diperlukan.",
                    )
                if not verify_password(request.pin, buyer_profile.pin_hash):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="PIN transaksi e-wallet KTP salah.",
                    )

            res_wallet = await self.db.execute(
                select(Wallet).filter(
                    Wallet.owner_id == buyer_profile.user_id,
                    Wallet.owner_type == OwnerType.USER,
                ),
            )
            wallet = res_wallet.scalars().first()
            if not wallet or not wallet.is_active:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="E-Wallet pembeli tidak ditemukan atau tidak aktif.",
                )
        else:
            wallet = await self.wallet_service.get_or_create_user_wallet(buyer_profile.user_id)

        res_vehicle = await self.db.execute(
            select(VehicleOwnership).filter(
                VehicleOwnership.plate_number_snapshot == request.plate_number,
                VehicleOwnership.owner_id == buyer_profile.id,
            ),
        )
        vehicle_ownership = res_vehicle.scalars().first()
        if not vehicle_ownership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Kepemilikan kendaraan dengan nomor plat tersebut tidak ditemukan pada profil pembeli.",
            )

        res_fuel = await self.db.execute(
            select(FuelType).filter(FuelType.id == request.fuel_type_id),
        )
        fuel_type = res_fuel.scalars().first()
        if not fuel_type:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tipe bahan bakar tidak ditemukan.",
            )

        fraud_assessment = await self._evaluate_fraud(
            buyer_profile=buyer_profile,
            vehicle_ownership=vehicle_ownership,
            current_station=current_station,
            liters=request.liters,
        )

        if fraud_assessment["action"] in {"FREEZE ACCOUNT", "BLOCK ACCOUNT"}:
            if fraud_assessment["action"] == "BLOCK ACCOUNT":
                buyer_profile.verification_status = VerificationStatus.REJECTED
                detail_msg = "Transaksi dibatalkan & akun diblokir permanen karena terdeteksi pola kecurangan kritikal."
            else:
                buyer_profile.verification_status = VerificationStatus.UNVERIFIED
                detail_msg = "Transaksi dibatalkan & akun dibekukan karena terdeteksi aktivitas mencurigakan berisiko tinggi."

            # Automatically log the fraud incident before blocking
            await self._create_fraud_log(
                buyer_profile=buyer_profile,
                vehicle_ownership=vehicle_ownership,
                current_station=current_station,
                fraud_assessment=fraud_assessment,
            )

            await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{detail_msg} Alasan: {', '.join(f['reason'] for f in fraud_assessment['detected_frauds'])}",
            )

        subsidy_quota = None
        kk_eligibility_id = None
        subsidized_liters = Decimal("0")
        non_subsidized_liters = Decimal(request.liters)
        total_amount = self._currency_amount(Decimal(fuel_type.price_per_liter) * Decimal(request.liters))
        market_price_per_liter = self._currency_amount(Decimal(fuel_type.price_per_liter))
        subsidized_price_per_liter = None

        if fuel_type.subsidy_type == SubsidyType.SUBSIDIZED:
            subsidy_service = SubsidyService(self.db)
            now = datetime.utcnow()
            month = now.month
            year = now.year

            if vehicle_ownership.usage_type == VehicleUsageType.PERSONAL:
                policy = await subsidy_service.repo.get_subsidy_policy_by_usage_type(VehicleUsageType.PERSONAL)
                if policy:
                    latest_eligibility = await subsidy_service.repo.get_latest_kk_subsidy_eligibility(
                        kk_id=buyer_profile.kk_id,
                        subsidy_policy_id=policy.id,
                    )
                    if latest_eligibility and latest_eligibility.eligibility_status == EligibilityStatus.ELIGIBLE:
                        kk_eligibility_id = latest_eligibility.id
                        subsidy_quota = await subsidy_service.get_or_create_subsidy_quota(
                            vehicle_ownership=vehicle_ownership,
                            month=month,
                            year=year,
                            kk_subsidy_eligibility_id=kk_eligibility_id,
                        )
            else:
                policy = await subsidy_service.repo.get_subsidy_policy_by_usage_type(vehicle_ownership.usage_type)
                if policy:
                    subsidy_quota = await subsidy_service.get_or_create_subsidy_quota(
                        vehicle_ownership=vehicle_ownership,
                        month=month,
                        year=year,
                    )

            pricing = self._build_fuel_purchase_pricing(
                request_liters=request.liters,
                fuel_type=fuel_type,
                subsidy_quota=subsidy_quota,
            )
            subsidized_liters = pricing["subsidized_liters"]
            non_subsidized_liters = pricing["non_subsidized_liters"]
            total_amount = pricing["total_amount"]
            market_price_per_liter = pricing["market_price_per_liter"]
            subsidized_price_per_liter = pricing["subsidized_price_per_liter"]

            if subsidized_liters > 0 and subsidy_quota is not None:
                subsidy_quota.used_liters += subsidized_liters

        if require_wallet_payment and wallet.balance < total_amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Saldo E-Wallet KTP tidak mencukupi untuk melakukan transaksi.",
            )

        if fraud_assessment["risk_score"] > 0:
            buyer_profile.risk_score = min(
                Decimal("100.00"),
                buyer_profile.risk_score + Decimal(str(fraud_assessment["risk_score"])),
            )
            from app.modules.users.service import UserService
            if buyer_profile.user:
                UserService.update_user_fraud_status(buyer_profile.user, float(buyer_profile.risk_score))

            # Automatically log suspicious but allowed transactions
            if fraud_assessment["risk_score"] > 30:
                await self._create_fraud_log(
                    buyer_profile=buyer_profile,
                    vehicle_ownership=vehicle_ownership,
                    current_station=current_station,
                    fraud_assessment=fraud_assessment,
                )

        return {
            "buyer_profile": buyer_profile,
            "wallet": wallet,
            "vehicle_ownership": vehicle_ownership,
            "fuel_type": fuel_type,
            "current_station": current_station,
            "fraud_assessment": fraud_assessment,
            "is_subsidized_purchase": subsidized_liters > 0,
            "subsidy_quota": subsidy_quota,
            "kk_eligibility_id": kk_eligibility_id,
            "subsidized_liters": subsidized_liters,
            "non_subsidized_liters": non_subsidized_liters,
            "total_amount": total_amount,
            "market_price_per_liter": market_price_per_liter,
            "subsidized_price_per_liter": subsidized_price_per_liter,
        }

    def _serialize_qris_status(self, fuel_tx: Any, payment_tx: PaymentTransaction) -> dict[str, Any]:
        fuel_name = fuel_tx.fuel_type.name if fuel_tx.fuel_type else "Bahan Bakar"
        return {
            "transaction_id": fuel_tx.id,
            "provider_reference_id": payment_tx.provider_reference_id,
            "status": payment_tx.status.value,
            "payment_status": payment_tx.status,
            "total_amount": fuel_tx.total_amount,
            "fuel_name": fuel_name,
            "liters": fuel_tx.liters,
            "plate_number": fuel_tx.plate_number_snapshot,
            "expires_at": payment_tx.expires_at,
        }

    def _serialize_xendit_fuel_status(self, fuel_tx: Any, payment_tx: PaymentTransaction) -> dict[str, Any]:
        fuel_name = fuel_tx.fuel_type.name if fuel_tx.fuel_type else "Bahan Bakar"
        return {
            "transaction_id": fuel_tx.id,
            "provider_reference_id": payment_tx.provider_reference_id,
            "payment_link_url": payment_tx.payment_link_url,
            "status": payment_tx.status.value,
            "payment_status": payment_tx.status,
            "total_amount": fuel_tx.total_amount,
            "fuel_name": fuel_name,
            "liters": fuel_tx.liters,
            "plate_number": fuel_tx.plate_number_snapshot,
            "expires_at": payment_tx.expires_at,
        }

    async def _release_reserved_quota(self, fuel_tx: Any) -> None:
        if not fuel_tx.is_subsidized or fuel_tx.subsidy_quota is None:
            return
        fuel_tx.subsidy_quota.used_liters = max(
            Decimal("0"),
            Decimal(fuel_tx.subsidy_quota.used_liters) - Decimal(fuel_tx.subsidized_liters),
        )

    async def _complete_qris_fuel_purchase(self, fuel_tx: Any, payment_tx: PaymentTransaction) -> None:
        from app.modules.transactions.models import FuelTransactionStatus

        if payment_tx.status == PaymentStatus.PAID and fuel_tx.transaction_status == FuelTransactionStatus.COMPLETED:
            return

        payment_tx.status = PaymentStatus.PAID
        fuel_tx.transaction_status = FuelTransactionStatus.COMPLETED
        await self.db.commit()
        await self.db.refresh(fuel_tx)
        await self.db.refresh(payment_tx)

        try:
            from app.modules.notifications.service import NotificationService

            formatted_amount = f"Rp {int(payment_tx.amount):,}".replace(",", ".")
            fuel_name = fuel_tx.fuel_type.name if fuel_tx.fuel_type else "BBM"
            buyer_user_id = fuel_tx.buyer_profile.user_id if fuel_tx.buyer_profile else None
            if buyer_user_id:
                await NotificationService.create_notification(
                    db=self.db,
                    user_id=buyer_user_id,
                    title="Pembayaran Sukses",
                    body=f"Pembelian {fuel_name} sebesar {formatted_amount} berhasil dibayar melalui Xendit.",
                    data={"type": "FUEL_PURCHASE", "transaction_id": str(fuel_tx.id)},
                )
        except Exception as push_err:
            logger.error(f"Failed to trigger Xendit fuel purchase push notification: {push_err}")

    async def _fail_qris_fuel_purchase(
        self,
        fuel_tx: Any,
        payment_tx: PaymentTransaction,
        payment_status: PaymentStatus,
        fuel_status: Any,
    ) -> None:
        from app.modules.transactions.models import FuelTransactionStatus

        if fuel_tx.transaction_status != FuelTransactionStatus.PENDING:
            payment_tx.status = payment_status
            await self.db.commit()
            await self.db.refresh(fuel_tx)
            await self.db.refresh(payment_tx)
            return

        await self._release_reserved_quota(fuel_tx)
        payment_tx.status = payment_status
        fuel_tx.transaction_status = fuel_status
        await self.db.commit()
        await self.db.refresh(fuel_tx)
        await self.db.refresh(payment_tx)

    async def _fetch_qris_payment_request(self, payment_request_id: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.xendit.co/v3/payment_requests/{payment_request_id}",
                    auth=(settings.XENDIT_SECRET_KEY, ""),
                    headers={"api-version": XENDIT_API_VERSION},
                    timeout=15.0,
                )
                if response.status_code != 200:
                    logger.error(f"Failed to fetch QRIS payment request from Xendit: {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail="Failed to retrieve QRIS payment status from Xendit.",
                    )
                return response.json()
        except httpx.RequestError as e:
            logger.exception(f"HTTP request to sync QRIS payment failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Connection to payment gateway failed.",
            )

    async def _sync_qris_payment_from_xendit(
        self,
        fuel_tx: Any,
        payment_tx: PaymentTransaction,
    ) -> dict[str, Any]:
        from app.modules.transactions.models import FuelTransactionStatus

        payload = await self._fetch_qris_payment_request(payment_tx.provider_reference_id)
        provider_status = (payload.get("status") or "").upper()

        payment_tx.expires_at = self._parse_provider_datetime(
            payload.get("channel_properties", {}).get("expires_at") or payload.get("expires_at"),
        )
        latest_qr_string = self._extract_qr_string(payload.get("actions"))
        if latest_qr_string:
            payment_tx.qr_string = latest_qr_string

        if provider_status in {"REQUIRES_ACTION", "PENDING", "ACCEPTING_PAYMENTS", "AUTHORIZED"}:
            payment_tx.status = PaymentStatus.PENDING
            await self.db.commit()
            await self.db.refresh(payment_tx)
        elif provider_status == "SUCCEEDED":
            await self._complete_qris_fuel_purchase(fuel_tx, payment_tx)
        elif provider_status == "EXPIRED":
            await self._fail_qris_fuel_purchase(
                fuel_tx,
                payment_tx,
                PaymentStatus.EXPIRED,
                FuelTransactionStatus.CANCELLED,
            )
        else:
            await self._fail_qris_fuel_purchase(
                fuel_tx,
                payment_tx,
                PaymentStatus.FAILED,
                FuelTransactionStatus.FAILED,
            )

        return self._serialize_qris_status(fuel_tx, payment_tx)

    async def create_xendit_fuel_purchase(self, current_user: Any, request: Any) -> dict:
        from app.modules.transactions.models import BuyerType, FuelTransaction, FuelTransactionStatus, PaymentMethod

        context = await self._prepare_fuel_purchase_context(
            current_user,
            request,
            require_wallet_payment=False,
        )

        buyer_profile = context["buyer_profile"]
        wallet = context["wallet"]
        vehicle_ownership = context["vehicle_ownership"]
        fuel_type = context["fuel_type"]
        current_station = context["current_station"]
        fraud_assessment = context["fraud_assessment"]
        is_subsidized_purchase = context["is_subsidized_purchase"]
        subsidy_quota = context["subsidy_quota"]
        kk_eligibility_id = context["kk_eligibility_id"]
        subsidized_liters = context["subsidized_liters"]
        non_subsidized_liters = context["non_subsidized_liters"]
        total_amount = context["total_amount"]
        market_price_per_liter = context["market_price_per_liter"]
        subsidized_price_per_liter = context["subsidized_price_per_liter"]

        reference_id = f"fuel_xendit_{uuid7().hex}"
        fuel_tx = FuelTransaction(
            buyer_type=BuyerType.PERSONAL,
            buyer_profile_id=buyer_profile.id,
            vehicle_ownership_id=vehicle_ownership.id,
            gas_station_id=current_station.id,
            fuel_type_id=fuel_type.id,
            liters=request.liters,
            subsidy_quota_id=subsidy_quota.id if is_subsidized_purchase else None,
            kk_subsidy_eligibility_id=kk_eligibility_id if is_subsidized_purchase else None,
            is_subsidized=is_subsidized_purchase,
            subsidized_liters=subsidized_liters,
            non_subsidized_liters=non_subsidized_liters,
            market_price_per_liter=market_price_per_liter,
            subsidized_price_per_liter=subsidized_price_per_liter if is_subsidized_purchase else None,
            total_amount=total_amount,
            payment_method=PaymentMethod.XENDIT,
            wallet_transaction_id=None,
            transaction_status=FuelTransactionStatus.PENDING,
            verified_by_user_id=current_user.id,
            plate_number_snapshot=request.plate_number,
            nik_snapshot=request.nik,
        )
        self.db.add(fuel_tx)
        await self.db.flush()

        payment_tx = PaymentTransaction(
            wallet_id=wallet.id,
            fuel_transaction_id=fuel_tx.id,
            provider=PaymentProvider.XENDIT,
            external_id=reference_id,
            amount=total_amount,
            status=PaymentStatus.PENDING,
        )
        self.db.add(payment_tx)
        await self.db.flush()

        xendit_payload = {
            "reference_id": reference_id,
            "session_type": "PAY",
            "mode": "PAYMENT_LINK",
            "amount": float(total_amount),
            "currency": "IDR",
            "country": "ID",
            "success_return_url": settings.XENDIT_SUCCESS_URL,
            "cancel_return_url": settings.XENDIT_CANCEL_URL,
            "description": f"Fuel purchase {fuel_type.name} - {request.plate_number}",
            "metadata": {
                "fuel_transaction_id": str(fuel_tx.id),
                "gas_station_id": str(current_station.id),
                "buyer_nik": request.nik,
            },
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.xendit.co/sessions",
                    json=xendit_payload,
                    auth=(settings.XENDIT_SECRET_KEY, ""),
                    timeout=15.0,
                )
        except httpx.RequestError as e:
            await self.db.rollback()
            logger.exception(f"HTTP request to Xendit session failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Connection to payment gateway timed out or failed.",
            )

        if response.status_code not in (200, 201):
            await self.db.rollback()
            logger.error(f"Xendit session creation failed: {response.text}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to initiate payment session with Xendit.",
            )

        data = response.json()
        provider_reference_id = data.get("payment_session_id") or data.get("id")
        payment_link_url = data.get("payment_link_url")
        if not provider_reference_id or not payment_link_url:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Xendit session response is missing required payment link data.",
            )

        payment_tx.provider_reference_id = provider_reference_id
        payment_tx.payment_link_url = payment_link_url
        payment_tx.expires_at = self._parse_provider_datetime(data.get("expires_at"))
        await self.db.commit()
        await self.db.refresh(fuel_tx)
        await self.db.refresh(payment_tx)

        return {
            "transaction_id": fuel_tx.id,
            "provider_reference_id": payment_tx.provider_reference_id,
            "external_id": payment_tx.external_id,
            "payment_link_url": payment_tx.payment_link_url,
            "total_amount": fuel_tx.total_amount,
            "fuel_name": fuel_type.name,
            "liters": fuel_tx.liters,
            "plate_number": fuel_tx.plate_number_snapshot,
            "status": payment_tx.status.value,
            "expires_at": payment_tx.expires_at,
            "detected_frauds": fraud_assessment["detected_frauds"],
            "risk_score": fraud_assessment["risk_score"],
            "risk_level": fraud_assessment["risk_level"],
            "action_taken": fraud_assessment["action"],
        }

    async def get_xendit_fuel_purchase_status(self, current_user: Any, transaction_id: UUID) -> dict:
        from app.modules.transactions.models import FuelTransactionStatus

        fuel_tx = await self.repo.get_fuel_transaction_by_id(transaction_id)
        if not fuel_tx:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transaksi non-tunai tidak ditemukan.",
            )
        if fuel_tx.gas_station_id != current_user.gas_station_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Anda tidak memiliki akses ke transaksi ini.",
            )

        payment_tx = await self.repo.get_payment_transaction_by_fuel_transaction_id(fuel_tx.id)
        if not payment_tx or not payment_tx.provider_reference_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Data pembayaran tidak ditemukan.",
            )

        if fuel_tx.transaction_status == FuelTransactionStatus.PENDING:
            try:
                await self.sync_session_from_xendit(payment_tx.provider_reference_id)
            except Exception as exc:
                logger.warning(f"Auto-sync during xendit status check failed: {exc}")

        return self._serialize_xendit_fuel_status(fuel_tx, payment_tx)

    async def execute_fuel_purchase(self, current_user: Any, request: Any) -> dict:
        from app.modules.transactions.models import FuelTransaction, FuelTransactionStatus, BuyerType, PaymentMethod, WalletTransactionStatus, TransactionFlow, TransactionType
        payment_method = getattr(request, "payment_method", PaymentMethod.WALLET)
        context = await self._prepare_fuel_purchase_context(
            current_user,
            request,
            require_wallet_payment=payment_method == PaymentMethod.WALLET,
        )

        buyer_profile = context["buyer_profile"]
        wallet = context["wallet"]
        vehicle_ownership = context["vehicle_ownership"]
        fuel_type = context["fuel_type"]
        current_station = context["current_station"]
        fraud_assessment = context["fraud_assessment"]
        is_subsidized_purchase = context["is_subsidized_purchase"]
        subsidy_quota = context["subsidy_quota"]
        kk_eligibility_id = context["kk_eligibility_id"]
        subsidized_liters = context["subsidized_liters"]
        non_subsidized_liters = context["non_subsidized_liters"]
        total_amount = context["total_amount"]
        market_price_per_liter = context["market_price_per_liter"]
        subsidized_price_per_liter = context["subsidized_price_per_liter"]

        if payment_method == PaymentMethod.CASH:
            if request.amount_paid is None or Decimal(request.amount_paid) < total_amount:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Nominal uang diterima tidak boleh kurang dari total harga.",
                )

        wallet_tx = None
        if payment_method == PaymentMethod.WALLET and wallet is not None:
            balance_before = wallet.balance
            wallet.balance -= total_amount
            balance_after = wallet.balance
            wallet_tx = WalletTransaction(
                wallet_id=wallet.id,
                type=TransactionType.FUEL_PURCHASE,
                transaction_flow=TransactionFlow.OUT,
                amount=total_amount,
                balance_before=balance_before,
                balance_after=balance_after,
                description=f"Pembelian {fuel_type.name} - {request.plate_number}",
                status=WalletTransactionStatus.SUCCESS,
            )
            self.db.add(wallet_tx)
            await self.db.flush()

        fuel_tx = FuelTransaction(
            buyer_type=BuyerType.PERSONAL,
            buyer_profile_id=buyer_profile.id,
            vehicle_ownership_id=vehicle_ownership.id,
            gas_station_id=current_station.id,
            fuel_type_id=fuel_type.id,
            liters=request.liters,
            subsidy_quota_id=subsidy_quota.id if is_subsidized_purchase else None,
            kk_subsidy_eligibility_id=kk_eligibility_id if is_subsidized_purchase else None,
            is_subsidized=is_subsidized_purchase,
            subsidized_liters=subsidized_liters,
            non_subsidized_liters=non_subsidized_liters,
            market_price_per_liter=market_price_per_liter,
            subsidized_price_per_liter=subsidized_price_per_liter if is_subsidized_purchase else None,
            total_amount=total_amount,
            payment_method=payment_method,
            wallet_transaction_id=wallet_tx.id if wallet_tx else None,
            transaction_status=FuelTransactionStatus.COMPLETED,
            verified_by_user_id=current_user.id,
            plate_number_snapshot=request.plate_number,
            nik_snapshot=request.nik,
        )
        self.db.add(fuel_tx)

        await self.db.commit()
        await self.db.refresh(fuel_tx)

        try:
            from app.modules.notifications.service import NotificationService
            formatted_amount = f"Rp {int(total_amount):,}".replace(",", ".")
            warning_msg = ""
            if fraud_assessment["risk_score"] > 0:
                warning_msg = f" Peringatan: Aktivitas transaksi terdeteksi anomali (Skor Risiko: {fraud_assessment['risk_score']})."

            await NotificationService.create_notification(
                db=self.db,
                user_id=buyer_profile.user_id,
                title="Pembayaran Sukses",
                body=f"Pembelian {fuel_type.name} sebesar {formatted_amount} berhasil dibayar menggunakan {'E-Wallet KTP' if payment_method == PaymentMethod.WALLET else 'Tunai / Cash'}.{warning_msg}",
                data={"type": "FUEL_PURCHASE", "transaction_id": str(fuel_tx.id)},
            )
        except Exception as push_err:
            logger.error(f"Failed to trigger fuel purchase push notification: {push_err}")

        return {
            "transaction_id": fuel_tx.id,
            "wallet_transaction_id": wallet_tx.id if wallet_tx else None,
            "plate_number": fuel_tx.plate_number_snapshot,
            "fuel_name": fuel_type.name,
            "liters": fuel_tx.liters,
            "total_amount": fuel_tx.total_amount,
            "status": "COMPLETED",
            "created_at": fuel_tx.created_at,
            "detected_frauds": fraud_assessment["detected_frauds"],
            "risk_score": fraud_assessment["risk_score"],
            "risk_level": fraud_assessment["risk_level"],
            "action_taken": fraud_assessment["action"],
        }

    async def create_qris_fuel_purchase(self, current_user: Any, request: Any) -> dict:
        from app.modules.transactions.models import BuyerType, FuelTransaction, FuelTransactionStatus, PaymentMethod

        context = await self._prepare_fuel_purchase_context(
            current_user,
            request,
            require_wallet_payment=False,
        )

        buyer_profile = context["buyer_profile"]
        wallet = context["wallet"]
        vehicle_ownership = context["vehicle_ownership"]
        fuel_type = context["fuel_type"]
        current_station = context["current_station"]
        fraud_assessment = context["fraud_assessment"]
        is_subsidized_purchase = context["is_subsidized_purchase"]
        subsidy_quota = context["subsidy_quota"]
        kk_eligibility_id = context["kk_eligibility_id"]
        subsidized_liters = context["subsidized_liters"]
        non_subsidized_liters = context["non_subsidized_liters"]
        total_amount = context["total_amount"]
        market_price_per_liter = context["market_price_per_liter"]
        subsidized_price_per_liter = context["subsidized_price_per_liter"]

        reference_id = f"fuel_qris_{uuid7().hex}"
        fuel_tx = FuelTransaction(
            buyer_type=BuyerType.PERSONAL,
            buyer_profile_id=buyer_profile.id,
            vehicle_ownership_id=vehicle_ownership.id,
            gas_station_id=current_station.id,
            fuel_type_id=fuel_type.id,
            liters=request.liters,
            subsidy_quota_id=subsidy_quota.id if is_subsidized_purchase else None,
            kk_subsidy_eligibility_id=kk_eligibility_id if is_subsidized_purchase else None,
            is_subsidized=is_subsidized_purchase,
            subsidized_liters=subsidized_liters,
            non_subsidized_liters=non_subsidized_liters,
            market_price_per_liter=market_price_per_liter,
            subsidized_price_per_liter=subsidized_price_per_liter if is_subsidized_purchase else None,
            total_amount=total_amount,
            payment_method=PaymentMethod.QRIS,
            wallet_transaction_id=None,
            transaction_status=FuelTransactionStatus.PENDING,
            verified_by_user_id=current_user.id,
            plate_number_snapshot=request.plate_number,
            nik_snapshot=request.nik,
        )
        self.db.add(fuel_tx)
        await self.db.flush()

        payment_tx = PaymentTransaction(
            wallet_id=wallet.id,
            fuel_transaction_id=fuel_tx.id,
            provider=PaymentProvider.XENDIT,
            external_id=reference_id,
            amount=total_amount,
            status=PaymentStatus.PENDING,
        )
        self.db.add(payment_tx)
        await self.db.flush()

        xendit_payload = {
            "reference_id": reference_id,
            "type": "PAY",
            "country": "ID",
            "currency": "IDR",
            "request_amount": float(total_amount),
            "capture_method": "AUTOMATIC",
            "channel_code": "QRIS",
            "channel_properties": {
                "qr_string_type": "DYNAMIC",
            },
            "description": f"Fuel purchase {fuel_type.name} - {request.plate_number}",
            "metadata": {
                "fuel_transaction_id": str(fuel_tx.id),
                "gas_station_id": str(current_station.id),
                "buyer_nik": request.nik,
            },
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.xendit.co/v3/payment_requests",
                    json=xendit_payload,
                    auth=(settings.XENDIT_SECRET_KEY, ""),
                    headers={"api-version": XENDIT_API_VERSION},
                    timeout=15.0,
                )
        except httpx.RequestError as e:
            await self.db.rollback()
            logger.exception(f"HTTP request to Xendit QRIS failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Connection to payment gateway timed out or failed.",
            )

        if response.status_code not in (200, 201):
            await self.db.rollback()
            logger.error(f"Xendit QRIS creation failed: {response.text}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to create QRIS payment request with Xendit.",
            )

        data = response.json()
        qr_string = self._extract_qr_string(data.get("actions"))
        provider_reference_id = data.get("payment_request_id") or data.get("id")
        if not provider_reference_id or not qr_string:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Xendit QRIS response is missing required QR data.",
            )

        payment_tx.provider_reference_id = provider_reference_id
        payment_tx.qr_string = qr_string
        payment_tx.expires_at = self._parse_provider_datetime(
            data.get("channel_properties", {}).get("expires_at") or data.get("expires_at"),
        )
        await self.db.commit()
        await self.db.refresh(fuel_tx)
        await self.db.refresh(payment_tx)

        return {
            "transaction_id": fuel_tx.id,
            "provider_reference_id": payment_tx.provider_reference_id,
            "external_id": payment_tx.external_id,
            "qr_string": payment_tx.qr_string,
            "total_amount": fuel_tx.total_amount,
            "fuel_name": fuel_type.name,
            "liters": fuel_tx.liters,
            "plate_number": fuel_tx.plate_number_snapshot,
            "status": payment_tx.status.value,
            "expires_at": payment_tx.expires_at,
            "detected_frauds": fraud_assessment["detected_frauds"],
            "risk_score": fraud_assessment["risk_score"],
            "risk_level": fraud_assessment["risk_level"],
            "action_taken": fraud_assessment["action"],
        }

    async def get_qris_fuel_purchase_status(self, current_user: Any, transaction_id: UUID) -> dict:
        from app.modules.transactions.models import FuelTransactionStatus

        fuel_tx = await self.repo.get_fuel_transaction_by_id(transaction_id)
        if not fuel_tx:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transaksi QRIS tidak ditemukan.",
            )
        if fuel_tx.gas_station_id != current_user.gas_station_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Anda tidak memiliki akses ke transaksi QRIS ini.",
            )

        payment_tx = await self.repo.get_payment_transaction_by_fuel_transaction_id(fuel_tx.id)
        if not payment_tx or not payment_tx.provider_reference_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Data pembayaran QRIS tidak ditemukan.",
            )

        if fuel_tx.transaction_status == FuelTransactionStatus.PENDING:
            return await self._sync_qris_payment_from_xendit(fuel_tx, payment_tx)
        return self._serialize_qris_status(fuel_tx, payment_tx)

    async def get_fraud_logs(
        self,
        current_user: Any,
        *,
        gas_station_id: UUID | None = None,
        risk_level: str | None = None,
        status_filter: str | None = None,
        search: str | None = None,
        limit: int = 20,
        offset: int = 0
    ) -> dict:
        from sqlalchemy import select, func, or_
        from sqlalchemy.orm import selectinload
        from app.modules.transactions.models import FraudLog, FraudRiskLevel, FraudCaseStatus
        from app.modules.users.models import User, UserRole, BuyerProfile
        from app.modules.gas_stations.models import GasStation
        from datetime import datetime

        # 1. Scope query based on user roles
        base_stmt = select(FraudLog)
        is_spbu_role = any(r in current_user.role for r in [UserRole.SPBU_ADMIN, UserRole.SALES_OFFICER])

        if is_spbu_role:
            if not current_user.gas_station_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Pengguna SPBU tidak terasosiasi dengan stasiun SPBU manapun."
                )
            base_stmt = base_stmt.filter(FraudLog.gas_station_id == current_user.gas_station_id)
        elif gas_station_id:
            base_stmt = base_stmt.filter(FraudLog.gas_station_id == gas_station_id)

        # 2. Query stats in current scope
        stats_stmt = select(
            func.count(FraudLog.id).label("total"),
            func.count(func.nullif(FraudLog.risk_level == FraudRiskLevel.SUSPICIOUS, False)).label("suspicious"),
            func.count(func.nullif(FraudLog.risk_level == FraudRiskLevel.HIGH_RISK, False)).label("high_risk"),
            func.count(func.nullif(FraudLog.risk_level == FraudRiskLevel.CRITICAL, False)).label("critical")
        )
        if is_spbu_role:
            stats_stmt = stats_stmt.filter(FraudLog.gas_station_id == current_user.gas_station_id)
        elif gas_station_id:
            stats_stmt = stats_stmt.filter(FraudLog.gas_station_id == gas_station_id)

        stats_res = await self.db.execute(stats_stmt)
        stats_row = stats_res.first()
        stats = {
            "total": stats_row.total or 0,
            "suspicious": stats_row.suspicious or 0,
            "high_risk": stats_row.high_risk or 0,
            "critical": stats_row.critical or 0
        }

        # 3. Apply filters to base query
        stmt = base_stmt.options(
            selectinload(FraudLog.gas_station),
            selectinload(FraudLog.buyer_profile).selectinload(BuyerProfile.user),
            selectinload(FraudLog.resolved_by)
        )

        if risk_level:
            try:
                stmt = stmt.filter(FraudLog.risk_level == FraudRiskLevel(risk_level.upper()))
            except ValueError:
                pass
        if status_filter:
            try:
                stmt = stmt.filter(FraudLog.status == FraudCaseStatus(status_filter.upper()))
            except ValueError:
                pass
        if search:
            search_clause = or_(
                FraudLog.case_id.ilike(f"%{search}%"),
                FraudLog.plate_number_snapshot.ilike(f"%{search}%"),
                FraudLog.nik_snapshot.ilike(f"%{search}%"),
            )
            stmt = stmt.outerjoin(BuyerProfile, FraudLog.buyer_profile_id == BuyerProfile.id)\
                       .outerjoin(User, BuyerProfile.user_id == User.id)\
                       .filter(or_(search_clause, User.name.ilike(f"%{search}%")))

        # Get total count matching active filters
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_count_res = await self.db.execute(count_stmt)
        total_count = total_count_res.scalar() or 0

        # Paginate results ordered by most recent first
        stmt = stmt.order_by(FraudLog.created_at.desc()).offset(offset).limit(limit)
        res = await self.db.execute(stmt)
        logs = res.scalars().all()

        items = []
        for log in logs:
            buyer_name = log.buyer_profile.user.name if log.buyer_profile and log.buyer_profile.user else None
            resolved_by_name = log.resolved_by.name if log.resolved_by else None
            items.append({
                "id": log.id,
                "case_id": log.case_id,
                "fuel_transaction_id": log.fuel_transaction_id,
                "gas_station_id": log.gas_station_id,
                "gas_station_name": log.gas_station.name if log.gas_station else "Stasiun SPBU",
                "buyer_profile_id": log.buyer_profile_id,
                "buyer_name": buyer_name,
                "vehicle_ownership_id": log.vehicle_ownership_id,
                "plate_number_snapshot": log.plate_number_snapshot,
                "nik_snapshot": log.nik_snapshot,
                "risk_score": log.risk_score,
                "risk_level": log.risk_level.value,
                "action_taken": log.action_taken.value,
                "detected_frauds": log.detected_frauds,
                "status": log.status.value,
                "resolution_notes": log.resolution_notes,
                "resolved_by_name": resolved_by_name,
                "resolved_at": log.resolved_at,
                "created_at": log.created_at
            })

        return {
            "stats": stats,
            "items": items,
            "total_count": total_count
        }

    async def update_fraud_log_status(
        self,
        current_user: Any,
        log_id: UUID,
        status_value: str,
        resolution_notes: str | None = None
    ) -> dict:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from app.modules.transactions.models import FraudLog, FraudCaseStatus
        from app.modules.users.models import User, UserRole, BuyerProfile
        from datetime import datetime

        stmt = select(FraudLog).options(
            selectinload(FraudLog.gas_station),
            selectinload(FraudLog.buyer_profile).selectinload(BuyerProfile.user),
            selectinload(FraudLog.resolved_by)
        ).filter(FraudLog.id == log_id)

        res = await self.db.execute(stmt)
        log = res.scalars().first()
        if not log:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Kasus fraud log tidak ditemukan."
            )

        # Check permissions: SPBU roles can only edit logs from their own station
        is_spbu_role = any(r in current_user.role for r in [UserRole.SPBU_ADMIN, UserRole.SALES_OFFICER])
        if is_spbu_role:
            if log.gas_station_id != current_user.gas_station_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Anda tidak memiliki akses untuk mengubah status kasus dari SPBU lain."
                )

        # Validate status enum
        try:
            new_status = FraudCaseStatus(status_value.upper())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Status '{status_value}' tidak valid. Gunakan PENDING, FLAGGED, atau RESOLVED."
            )

        log.status = new_status
        log.resolution_notes = resolution_notes
        log.resolved_by_user_id = current_user.id
        log.resolved_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(log)

        buyer_name = log.buyer_profile.user.name if log.buyer_profile and log.buyer_profile.user else None
        resolved_by_name = current_user.name

        return {
            "id": log.id,
            "case_id": log.case_id,
            "fuel_transaction_id": log.fuel_transaction_id,
            "gas_station_id": log.gas_station_id,
            "gas_station_name": log.gas_station.name if log.gas_station else "Stasiun SPBU",
            "buyer_profile_id": log.buyer_profile_id,
            "buyer_name": buyer_name,
            "vehicle_ownership_id": log.vehicle_ownership_id,
            "plate_number_snapshot": log.plate_number_snapshot,
            "nik_snapshot": log.nik_snapshot,
            "risk_score": log.risk_score,
            "risk_level": log.risk_level.value,
            "action_taken": log.action_taken.value,
            "detected_frauds": log.detected_frauds,
            "status": log.status.value,
            "resolution_notes": log.resolution_notes,
            "resolved_by_name": resolved_by_name,
            "resolved_at": log.resolved_at,
            "created_at": log.created_at
        }

    async def get_spbu_dashboard_summary(
        self,
        current_user: Any,
        *,
        gas_station_id: UUID | None = None
    ) -> dict:
        from sqlalchemy import select, func
        from app.modules.transactions.models import FuelTransaction, FuelTransactionStatus, FraudLog, FraudRiskLevel
        from app.modules.users.models import UserRole
        from app.modules.gas_stations.models import GasStation
        from datetime import datetime

        # 1. Determine target gas station ID
        target_station_id = gas_station_id
        is_spbu_role = any(r in current_user.role for r in [UserRole.SPBU_ADMIN, UserRole.SALES_OFFICER])

        if is_spbu_role:
            if not current_user.gas_station_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Pengguna SPBU tidak terasosiasi dengan stasiun SPBU manapun."
                )
            target_station_id = current_user.gas_station_id
        elif not target_station_id:
            station_stmt = select(GasStation.id).limit(1)
            station_res = await self.db.execute(station_stmt)
            target_station_id = station_res.scalar()

        if not target_station_id:
            return {
                "gas_station_id": None,
                "gas_station_name": "Stasiun SPBU",
                "stats": [
                    { "label": "Total Transactions", "value": "0", "trend": "0%", "trendDirection": "up", "trendSubtext": "dari kemarin" },
                    { "label": "Fuel Distributed", "value": "0 L", "trendSubtext": "Hari ini" },
                    { "label": "Rejected Transactions", "value": "0", "trend": "0", "trendDirection": "up", "trendSubtext": "dari kemarin" },
                    { "label": "High-Risk Vehicles", "value": "0", "trendSubtext": "Perlu review" }
                ],
                "peakHours": [
                    { "hour": "00:00", "volume": 0 },
                    { "hour": "03:00", "volume": 0 },
                    { "hour": "06:00", "volume": 0 },
                    { "hour": "09:00", "volume": 0 },
                    { "hour": "12:00", "volume": 0 },
                    { "hour": "15:00", "volume": 0 },
                    { "hour": "18:00", "volume": 0 },
                    { "hour": "21:00", "volume": 0 }
                ],
                "fuelTypes": [
                    { "name": "Subsidi", "value": 0, "color": "#e31837" },
                    { "name": "Komersial", "value": 0, "color": "#64748b" }
                ],
                "fraudAlerts": []
            }

        # 2. Get active station name
        station_name_stmt = select(GasStation.name).filter(GasStation.id == target_station_id)
        station_name_res = await self.db.execute(station_name_stmt)
        station_name = station_name_res.scalar() or "Stasiun SPBU"

        # 3. Calculate basic counts/sums
        total_tx_stmt = select(func.count(FuelTransaction.id)).filter(FuelTransaction.gas_station_id == target_station_id)
        total_tx_res = await self.db.execute(total_tx_stmt)
        total_tx = total_tx_res.scalar() or 0

        fuel_dist_stmt = select(func.sum(FuelTransaction.liters)).filter(
            FuelTransaction.gas_station_id == target_station_id,
            FuelTransaction.transaction_status == FuelTransactionStatus.COMPLETED
        )
        fuel_dist_res = await self.db.execute(fuel_dist_stmt)
        fuel_dist = float(fuel_dist_res.scalar() or 0.0)

        failed_tx_stmt = select(func.count(FuelTransaction.id)).filter(
            FuelTransaction.gas_station_id == target_station_id,
            FuelTransaction.transaction_status == FuelTransactionStatus.FAILED
        )
        failed_tx_res = await self.db.execute(failed_tx_stmt)
        failed_tx = failed_tx_res.scalar() or 0

        high_risk_stmt = select(func.count(FraudLog.id)).filter(
            FraudLog.gas_station_id == target_station_id,
            FraudLog.risk_level.in_([
                FraudRiskLevel.HIGH_RISK,
                FraudRiskLevel.CRITICAL,
                "HIGH_RISK",
                "CRITICAL"
            ])
        )
        high_risk_res = await self.db.execute(high_risk_stmt)
        high_risk = high_risk_res.scalar() or 0

        # 4. Hourly fuel consumption (dialect-independent Python processing)
        hourly_stmt = select(
            FuelTransaction.created_at,
            FuelTransaction.liters
        ).filter(
            FuelTransaction.gas_station_id == target_station_id,
            FuelTransaction.transaction_status == FuelTransactionStatus.COMPLETED
        )
        hourly_res = await self.db.execute(hourly_stmt)
        hourly_rows = hourly_res.all()

        peak_hours_map = {h: 0.0 for h in [0, 3, 6, 9, 12, 15, 18, 21]}
        for row in hourly_rows:
            dt = row.created_at
            if dt:
                hr = dt.hour
                closest_block = (hr // 3) * 3
                if closest_block in peak_hours_map:
                    peak_hours_map[closest_block] += float(row.liters or 0.0)

        peak_hours = [
            { "hour": f"{h:02d}:00", "volume": round(vol, 1) }
            for h, vol in sorted(peak_hours_map.items())
        ]

        # 5. Subsidi vs Komersial (safe index access)
        subsidy_stmt = select(
            func.sum(FuelTransaction.subsidized_liters),
            func.sum(FuelTransaction.non_subsidized_liters)
        ).filter(
            FuelTransaction.gas_station_id == target_station_id,
            FuelTransaction.transaction_status == FuelTransactionStatus.COMPLETED
        )
        subsidy_res = await self.db.execute(subsidy_stmt)
        subsidy_row = subsidy_res.first()
        subsidy_val = 0.0
        commercial_val = 0.0
        if subsidy_row:
            subsidy_val = float(subsidy_row[0] or 0.0)
            commercial_val = float(subsidy_row[1] or 0.0)

        fuel_types = [
            { "name": "Subsidi", "value": round(subsidy_val, 1), "color": "#e31837" },
            { "name": "Komersial", "value": round(commercial_val, 1), "color": "#64748b" }
        ]

        # 6. Real-time Fraud Alerts (top 5 recent)
        alerts_stmt = select(FraudLog).filter(
            FraudLog.gas_station_id == target_station_id
        ).order_by(FraudLog.created_at.desc()).limit(5)
        alerts_res = await self.db.execute(alerts_stmt)
        alerts_list = alerts_res.scalars().all()

        fraud_alerts = []
        for log in alerts_list:
            reason = log.detected_frauds[0].get("reason", "Anomali terdeteksi") if log.detected_frauds else "Analisis anomali"
            risk_val = getattr(log.risk_level, "value", str(log.risk_level)) if log.risk_level else "UNKNOWN"
            risk_label = "HIGH RISK" if risk_val == "HIGH_RISK" else risk_val.replace("_", " ")
            fraud_alerts.append({
                "time": log.created_at.strftime("%H:%M") if log.created_at else "--:--",
                "vehicle": log.plate_number_snapshot,
                "account": f"NIK {log.nik_snapshot[:4]}..." if log.nik_snapshot else "NIK -",
                "reason": reason,
                "risk": risk_label
            })

        stats = [
            {
                "label": "Total Transactions",
                "value": f"{total_tx:,}",
                "trend": "+12%",
                "trendDirection": "up",
                "trendSubtext": "dari kemarin",
            },
            {
                "label": "Fuel Distributed",
                "value": f"{fuel_dist:,.1f} L" if fuel_dist > 0 else "0 L",
                "trendSubtext": "Hari ini",
            },
            {
                "label": "Rejected Transactions",
                "value": f"{failed_tx}",
                "trend": f"+{failed_tx}" if failed_tx > 0 else "0",
                "trendDirection": "down" if failed_tx > 0 else "up",
                "trendSubtext": "dari kemarin",
            },
            {
                "label": "High-Risk Vehicles",
                "value": f"{high_risk}",
                "trendSubtext": "Perlu review",
            }
        ]

        return {
            "gas_station_id": target_station_id,
            "gas_station_name": station_name,
            "stats": stats,
            "peakHours": peak_hours,
            "fuelTypes": fuel_types,
            "fraudAlerts": fraud_alerts
        }

    async def get_spbu_transactions(
        self,
        current_user: Any,
        *,
        page: int = 1,
        size: int = 10,
        fuel_type: str | None = None,
        status: str | None = None,
        search: str | None = None,
        gas_station_id: UUID | None = None
    ) -> dict:
        from sqlalchemy import select, func, or_, and_, cast, String
        from sqlalchemy.orm import selectinload
        from app.modules.transactions.models import FuelTransaction, FuelTransactionStatus
        from app.modules.users.models import UserRole, User
        from app.modules.gas_stations.models import GasStation
        from app.modules.fuels.models import FuelType

        # 1. Determine target gas station ID
        target_station_id = gas_station_id
        is_spbu_role = any(r in current_user.role for r in [UserRole.SPBU_ADMIN, UserRole.SALES_OFFICER])

        if is_spbu_role:
            if not current_user.gas_station_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Pengguna SPBU tidak terasosiasi dengan stasiun SPBU manapun."
                )
            target_station_id = current_user.gas_station_id
        elif not target_station_id:
            station_stmt = select(GasStation.id).limit(1)
            station_res = await self.db.execute(station_stmt)
            target_station_id = station_res.scalar()

        if not target_station_id:
            return {
                "items": [],
                "total": 0,
                "page": page,
                "size": size,
                "pages": 0,
                "summary": {
                    "total_active_transactions": 0,
                    "total_volume": 0.0,
                    "total_revenue": 0.0
                }
            }

        # 2. Construct base statement
        stmt = (
            select(FuelTransaction)
            .options(
                selectinload(FuelTransaction.fuel_type),
                selectinload(FuelTransaction.verified_by)
            )
            .filter(FuelTransaction.gas_station_id == target_station_id)
        )

        # 3. Apply Filters
        # Fuel Type filter
        if fuel_type and fuel_type != "Semua":
            term = f"%{fuel_type.strip().lower()}%"
            stmt = stmt.join(FuelTransaction.fuel_type).filter(
                func.lower(FuelType.name).like(term)
            )

        # Status filter
        if status and status != "Semua":
            if status == "Success":
                stmt = stmt.filter(FuelTransaction.transaction_status == FuelTransactionStatus.COMPLETED)
            elif status == "Review":
                stmt = stmt.filter(FuelTransaction.transaction_status == FuelTransactionStatus.PENDING)
            elif status == "Rejected":
                stmt = stmt.filter(
                    FuelTransaction.transaction_status.in_(
                        [FuelTransactionStatus.CANCELLED, FuelTransactionStatus.FAILED]
                    )
                )

        # Search term filter
        if search:
            term = f"%{search.strip().lower()}%"
            stmt = stmt.outerjoin(FuelTransaction.verified_by)
            stmt = stmt.outerjoin(FuelTransaction.fuel_type)
            stmt = stmt.filter(
                or_(
                    func.lower(cast(FuelTransaction.id, String)).like(term),
                    func.lower(FuelTransaction.plate_number_snapshot).like(term),
                    func.lower(func.coalesce(FuelTransaction.nik_snapshot, "")).like(term),
                    func.lower(func.coalesce(User.name, "")).like(term)
                )
            )

        # Order by newest
        stmt = stmt.order_by(FuelTransaction.created_at.desc(), FuelTransaction.id.desc())

        # 4. Calculate total count for the filtered query
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_res = await self.db.execute(count_stmt)
        total = count_res.scalar() or 0

        # 5. Calculate summary stats
        # Total revenue of overall COMPLETED transactions at the SPBU
        revenue_stmt = select(func.sum(FuelTransaction.total_amount)).filter(
            FuelTransaction.gas_station_id == target_station_id,
            FuelTransaction.transaction_status == FuelTransactionStatus.COMPLETED
        )
        revenue_res = await self.db.execute(revenue_stmt)
        total_revenue = float(revenue_res.scalar() or 0.0)

        # Volume distributed under current filters
        liters_stmt = select(func.sum(FuelTransaction.liters)).filter(
            FuelTransaction.gas_station_id == target_station_id,
            FuelTransaction.transaction_status == FuelTransactionStatus.COMPLETED
        )
        if fuel_type and fuel_type != "Semua":
            term = f"%{fuel_type.strip().lower()}%"
            liters_stmt = liters_stmt.join(FuelTransaction.fuel_type).filter(
                func.lower(FuelType.name).like(term)
            )
        if search:
            term = f"%{search.strip().lower()}%"
            liters_stmt = liters_stmt.outerjoin(FuelTransaction.verified_by).outerjoin(FuelTransaction.fuel_type).filter(
                or_(
                    func.lower(cast(FuelTransaction.id, String)).like(term),
                    func.lower(FuelTransaction.plate_number_snapshot).like(term),
                    func.lower(func.coalesce(FuelTransaction.nik_snapshot, "")).like(term),
                    func.lower(func.coalesce(User.name, "")).like(term)
                )
            )
        liters_res = await self.db.execute(liters_stmt)
        total_volume = float(liters_res.scalar() or 0.0)

        # 6. Pagination execution
        offset = (page - 1) * size
        stmt = stmt.offset(offset).limit(size)
        res = await self.db.execute(stmt)
        transactions = res.scalars().all()

        # 7. Serialize items
        serialized_items = []
        for tx in transactions:
            fuel_name = tx.fuel_type.name if tx.fuel_type else "BBM"
            cashier_name = tx.verified_by.name if tx.verified_by else "System/Cashier"
            
            status_label = "Success"
            if tx.transaction_status == FuelTransactionStatus.PENDING:
                status_label = "Review"
            elif tx.transaction_status in [FuelTransactionStatus.CANCELLED, FuelTransactionStatus.FAILED]:
                status_label = "Rejected"

            serialized_items.append({
                "id": str(tx.id),
                "plate": tx.plate_number_snapshot,
                "fuel": fuel_name,
                "volume": float(tx.liters),
                "price": float(tx.total_amount),
                "time": tx.created_at.strftime("%H:%M:%S") if tx.created_at else "--:--:--",
                "date": tx.created_at.strftime("%Y-%m-%d") if tx.created_at else "-----",
                "status": status_label,
                "cashier": cashier_name
            })

        pages = (total + size - 1) // size if total else 0

        return {
            "items": serialized_items,
            "total": total,
            "page": page,
            "size": size,
            "pages": pages,
            "summary": {
                "total_active_transactions": total,
                "total_volume": total_volume,
                "total_revenue": total_revenue
            }
        }

    async def get_government_dashboard_summary(
        self,
        current_user: Any
    ) -> dict:
        from sqlalchemy import select, func
        from app.modules.transactions.models import FuelTransaction, FuelTransactionStatus, FraudLog, FraudRiskLevel
        from app.modules.gas_stations.models import GasStation
        from datetime import datetime

        # 1. Total Transactions count
        total_tx_stmt = select(func.count(FuelTransaction.id))
        total_tx_res = await self.db.execute(total_tx_stmt)
        total_transactions = total_tx_res.scalar() or 0

        # 2. Risk level counts from fraud_logs
        safe_count_stmt = select(func.count(FraudLog.id)).filter(FraudLog.risk_level == FraudRiskLevel.SAFE)
        safe_res = await self.db.execute(safe_count_stmt)
        safe_count = safe_res.scalar() or 0

        suspicious_count_stmt = select(func.count(FraudLog.id)).filter(FraudLog.risk_level == FraudRiskLevel.SUSPICIOUS)
        suspicious_res = await self.db.execute(suspicious_count_stmt)
        suspicious_count = suspicious_res.scalar() or 0

        high_risk_stmt = select(func.count(FraudLog.id)).filter(FraudLog.risk_level == FraudRiskLevel.HIGH_RISK)
        high_risk_res = await self.db.execute(high_risk_stmt)
        high_risk_count = high_risk_res.scalar() or 0

        critical_stmt = select(func.count(FraudLog.id)).filter(FraudLog.risk_level == FraudRiskLevel.CRITICAL)
        critical_res = await self.db.execute(critical_stmt)
        critical_count = critical_res.scalar() or 0

        # 3. Total Liters and Average Liters
        liters_stmt = select(
            func.sum(FuelTransaction.liters),
            func.avg(FuelTransaction.liters)
        ).filter(FuelTransaction.transaction_status == FuelTransactionStatus.COMPLETED)
        liters_res = await self.db.execute(liters_stmt)
        liters_row = liters_res.first()
        total_liters = float(liters_row[0] or 0.0) if liters_row else 0.0
        average_liters = float(liters_row[1] or 0.0) if liters_row else 0.0

        # 4. Hourly fuel trend data
        trend_stmt = select(
            FuelTransaction.created_at,
            FuelTransaction.liters
        ).filter(FuelTransaction.transaction_status == FuelTransactionStatus.COMPLETED)
        trend_res = await self.db.execute(trend_stmt)
        trend_rows = trend_res.all()

        trend_map = {}
        for row in trend_rows:
            dt = row.created_at
            if dt:
                period = dt.strftime("%H:%M")
                trend_map[period] = trend_map.get(period, 0.0) + float(row.liters or 0.0)

        fuel_trend_data = [
            {"period": p, "liters": round(vol, 2)}
            for p, vol in sorted(trend_map.items())
        ]

        # 5. Top stations with highest fraud count/score
        station_stmt = select(
            GasStation.name,
            func.coalesce(
                select(func.count(FuelTransaction.id))
                .where(FuelTransaction.gas_station_id == GasStation.id)
                .scalar_subquery(),
                0
            ),
            func.coalesce(
                select(func.count(FraudLog.id))
                .where(FraudLog.gas_station_id == GasStation.id)
                .scalar_subquery(),
                0
            ),
            func.coalesce(
                select(func.sum(FraudLog.risk_score))
                .where(FraudLog.gas_station_id == GasStation.id)
                .scalar_subquery(),
                0
            )
        )
        station_res = await self.db.execute(station_stmt)
        station_rows = station_res.all()

        stations_list = []
        for row in station_rows:
            station_name, tx_count, fraud_cnt, fraud_score = row
            if fraud_cnt > 0:
                stations_list.append({
                    "label": station_name,
                    "transactionCount": int(tx_count),
                    "fraudCount": int(fraud_cnt),
                    "score": int(fraud_score)
                })

        stations_list.sort(key=lambda item: (-item["fraudCount"], -item["score"]))
        stations_with_highest_fraud = stations_list[:5]

        return {
            "totalTransactions": total_transactions,
            "safeCount": safe_count,
            "suspiciousCount": suspicious_count,
            "highRiskCount": high_risk_count,
            "criticalCount": critical_count,
            "totalLiters": round(total_liters, 2),
            "averageLiters": round(average_liters, 2),
            "fuelTrendData": fuel_trend_data,
            "stationsWithHighestFraudCount": stations_with_highest_fraud,
            "topRiskyUsers": [],
            "topRiskyFamilies": []
        }

    @staticmethod
    def get_spbu_region_by_coordinates(name: str, lat: float, lon: float) -> tuple[str, str]:
        """
        Determines the province and island region for a given gas station by its name
        and coordinates (latitude, longitude) using a fast, zero-dependency heuristic.
        Returns a tuple of (province_name, island_name).
        """
        name_lower = name.lower()
        
        # 1. Direct name keyword detection
        if "banten" in name_lower:
            return "Banten", "Jawa"
        if "jakarta" in name_lower or "dki" in name_lower:
            return "DKI Jakarta", "Jawa"
        if "jawa barat" in name_lower or "bandung" in name_lower or "bogor" in name_lower:
            return "Jawa Barat", "Jawa"
        if "jawa tengah" in name_lower or "diy" in name_lower or "yogyakarta" in name_lower or "solo" in name_lower or "semarang" in name_lower:
            return "Jawa Tengah", "Jawa"
        if "jawa timur" in name_lower or "surabaya" in name_lower or "malang" in name_lower:
            return "Jawa Timur", "Jawa"
        if "sumatera utara" in name_lower or "medan" in name_lower:
            return "Sumatera Utara", "Sumatera"
        if "riau" in name_lower:
            return "Riau", "Sumatera"
        if "kalimantan" in name_lower:
            return "Kalimantan Timur", "Kalimantan"
        if "sulawesi" in name_lower or "makassar" in name_lower:
            return "Sulawesi Selatan", "Sulawesi"
            
        # 2. Geographic coordinate heuristic (Bounding Boxes)
        # Jawa: Lon 105.0 to 116.0, Lat -9.0 to -5.0
        if 105.0 <= lon <= 116.0 and -9.0 <= lat <= -5.0:
            if lon < 106.3:
                return "Banten", "Jawa"
            elif lon < 107.0:
                return "DKI Jakarta", "Jawa"
            elif lon < 108.8:
                return "Jawa Barat", "Jawa"
            elif lon < 111.5:
                return "Jawa Tengah", "Jawa"
            else:
                return "Jawa Timur", "Jawa"
                
        # Sumatera: Lon 95.0 to 106.0, Lat -6.0 to 6.0
        if 95.0 <= lon <= 106.0 and -6.0 <= lat <= 6.0:
            if lat > 2.0:
                return "Sumatera Utara", "Sumatera"
            else:
                return "Riau", "Sumatera"
                
        # Kalimantan: Lon 108.0 to 119.0, Lat -5.0 to 5.0
        if 108.0 <= lon <= 119.0 and -5.0 <= lat <= 5.0:
            return "Kalimantan Timur", "Kalimantan"
            
        # Sulawesi: Lon 118.5 to 126.0, Lat -6.0 to 2.0
        if 118.5 <= lon <= 126.0 and -6.0 <= lat <= 2.0:
            return "Sulawesi Selatan", "Sulawesi"
            
        # Default Fallback
        return "DKI Jakarta", "Jawa"

    async def get_government_heatmap_data(self, current_user: Any) -> dict:
        """
        Gathers raw SPBU geographic positions, total volumes, and fraud statistics,
        then structures them as:
        1. GeoJSON Map data for the Heatmap component
        2. Aggregated provincial stats for the breakdown table
        """
        from sqlalchemy import select, func
        from app.modules.gas_stations.models import GasStation
        from app.modules.transactions.models import FuelTransaction, FuelTransactionStatus, FraudLog
        
        # 1. Fetch all gas stations
        stations_stmt = select(GasStation)
        stations_res = await self.db.execute(stations_stmt)
        stations = stations_res.scalars().all()
        
        features = []
        province_aggregates = {}
        
        # We will loop over each station to query its specific volume and fraud logs
        for station in stations:
            # A. Calculate total transaction volume (liters) for completed transactions
            vol_stmt = select(func.sum(FuelTransaction.liters)).filter(
                FuelTransaction.gas_station_id == station.id,
                FuelTransaction.transaction_status == FuelTransactionStatus.COMPLETED
            )
            vol_res = await self.db.execute(vol_stmt)
            total_volume = float(vol_res.scalar() or 0.0)
            
            # B. Get fraud count and average risk score from fraud_logs
            fraud_stmt = select(
                func.count(FraudLog.id),
                func.avg(FraudLog.risk_score)
            ).filter(FraudLog.gas_station_id == station.id)
            fraud_res = await self.db.execute(fraud_stmt)
            fraud_row = fraud_res.first()
            fraud_cases = int(fraud_row[0] or 0) if fraud_row else 0
            avg_risk_score = float(fraud_row[1] or 0.0) if fraud_row else 0.0
            
            # C. Determine geographic region using our heuristic helper
            lat = float(station.latitude)
            lon = float(station.longitude)
            province, island = self.get_spbu_region_by_coordinates(station.name, lat, lon)
            
            # D. Format intensity: risk score mapped between 0.1 and 1.0 (or default to 0.1)
            # Intensity = risk score / 100 capped between 0.1 and 1.0
            intensity = max(0.1, min(1.0, avg_risk_score / 100.0))
            if fraud_cases == 0:
                intensity = 0.1
                
            # E. Append to Map GeoJSON Features
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [lon, lat],
                },
                "properties": {
                    "id": station.name,
                    "intensity": intensity,
                    "fraud_cases": fraud_cases,
                },
            })
            
            # F. Aggregate province statistics for the table
            if province not in province_aggregates:
                province_aggregates[province] = {
                    "id": str(station.id),
                    "province": province,
                    "island": island,
                    "volume": 0.0,
                    "activeSpbu": 0,
                    "fraudScoreSum": 0.0,
                    "fraudStationCount": 0,  # only stations with at least 1 fraud case
                    "fraudCases": 0
                }
            
            province_aggregates[province]["volume"] += total_volume
            province_aggregates[province]["activeSpbu"] += 1
            province_aggregates[province]["fraudCases"] += fraud_cases
            # Only accumulate risk score from stations that actually have fraud
            if fraud_cases > 0:
                province_aggregates[province]["fraudScoreSum"] += avg_risk_score
                province_aggregates[province]["fraudStationCount"] += 1
            
        # 2. Format province aggregates and calculate dynamic load intensity
        provinces_list = []
        for index, (prov_name, data) in enumerate(province_aggregates.items()):
            active_spbu = data["activeSpbu"]
            fraud_station_count = data["fraudStationCount"]
            # Average risk score only across stations that have fraud (not all stations)
            avg_score = round(data["fraudScoreSum"] / fraud_station_count, 2) if fraud_station_count > 0 else 0.0
            
            # Dynamic Intensity Classification based on volume & fraud risk
            # Map average risk score to a readable string
            if avg_score >= 80 or data["volume"] >= 1000:
                intensity_label = "Sangat Tinggi"
            elif avg_score >= 60 or data["volume"] >= 500:
                intensity_label = "Tinggi"
            elif avg_score >= 40 or data["volume"] >= 200:
                intensity_label = "Sedang"
            else:
                intensity_label = "Stabil"
                
            provinces_list.append({
                "id": str(index + 1),
                "province": prov_name,
                "island": data["island"],
                "volume": round(data["volume"], 2),
                "intensity": intensity_label,
                "activeSpbu": active_spbu,
                "fraudScore": int(avg_score)  # 0% if no fraud detected
            })
            
        return {
            "map_data": {
                "type": "FeatureCollection",
                "features": features
            },
            "provinces": provinces_list
        }

