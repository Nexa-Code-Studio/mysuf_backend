from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.modules.fuels.models import FuelType
from app.modules.gas_stations.models import GasStation
from app.modules.transactions.models import FuelTransaction
from app.modules.transactions.models import PaymentTransaction, WalletTransaction, WebhookAuditLog

class TransactionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_payment_transaction(self, transaction: PaymentTransaction) -> PaymentTransaction:
        self.db.add(transaction)
        await self.db.commit()
        await self.db.refresh(transaction)
        return transaction

    async def get_payment_transaction_by_id(self, tx_id: UUID | str) -> PaymentTransaction | None:
        if isinstance(tx_id, str):
            tx_id = UUID(tx_id)
        result = await self.db.execute(
            select(PaymentTransaction).filter(PaymentTransaction.id == tx_id)
        )
        return result.scalars().first()

    async def get_payment_transaction_by_ref(self, ref_id: str) -> PaymentTransaction | None:
        result = await self.db.execute(
            select(PaymentTransaction).filter(PaymentTransaction.external_id == ref_id)
        )
        return result.scalars().first()

    async def get_payment_transaction_by_provider_ref(self, session_id: str) -> PaymentTransaction | None:
        result = await self.db.execute(
            select(PaymentTransaction).filter(PaymentTransaction.provider_reference_id == session_id)
        )
        return result.scalars().first()

    async def create_wallet_transaction(self, wallet_tx: WalletTransaction) -> WalletTransaction:
        self.db.add(wallet_tx)
        await self.db.commit()
        await self.db.refresh(wallet_tx)
        return wallet_tx

    async def create_webhook_audit_log(self, audit_log: WebhookAuditLog) -> WebhookAuditLog:
        self.db.add(audit_log)
        await self.db.commit()
        await self.db.refresh(audit_log)
        return audit_log

    async def get_wallet_transactions_paginated(
        self, wallet_id: UUID, offset: int, limit: int
    ) -> list[WalletTransaction]:
        result = await self.db.execute(
            select(WalletTransaction)
            .options(
                selectinload(WalletTransaction.fuel_transactions).selectinload(FuelTransaction.gas_station),
                selectinload(WalletTransaction.fuel_transactions).selectinload(FuelTransaction.fuel_type),
            )
            .filter(WalletTransaction.wallet_id == wallet_id)
            .order_by(WalletTransaction.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_wallet_transaction_by_id(self, tx_id: UUID | str) -> WalletTransaction | None:
        if isinstance(tx_id, str):
            tx_id = UUID(tx_id)
        result = await self.db.execute(
            select(WalletTransaction)
            .options(
                selectinload(WalletTransaction.fuel_transactions).selectinload(FuelTransaction.gas_station),
                selectinload(WalletTransaction.fuel_transactions).selectinload(FuelTransaction.fuel_type),
            )
            .filter(WalletTransaction.id == tx_id)
        )
        return result.scalars().first()

    async def count_wallet_transactions(self, wallet_id: UUID) -> int:
        from sqlalchemy import func
        result = await self.db.execute(
            select(func.count(WalletTransaction.id)).filter(
                WalletTransaction.wallet_id == wallet_id
            )
        )
        return result.scalar() or 0
