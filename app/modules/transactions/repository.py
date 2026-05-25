from datetime import datetime
from statistics import fmean
from uuid import UUID
from typing import Iterable

from sqlalchemy import and_, or_, func, cast, String, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.modules.fuels.models import FuelType
from app.modules.gas_stations.models import GasStation
from app.modules.transactions.models import (
    CashierScanEvent,
    CashierScanResult,
    FuelTransaction,
    FuelTransactionStatus,
    PaymentTransaction,
    WalletTransaction,
    WebhookAuditLog,
)
from app.modules.users.models import BuyerProfile, User

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

    async def get_payment_transaction_by_fuel_transaction_id(
        self,
        fuel_transaction_id: UUID | str,
    ) -> PaymentTransaction | None:
        if isinstance(fuel_transaction_id, str):
            fuel_transaction_id = UUID(fuel_transaction_id)
        result = await self.db.execute(
            select(PaymentTransaction).filter(
                PaymentTransaction.fuel_transaction_id == fuel_transaction_id,
            )
        )
        return result.scalars().first()

    async def get_fuel_transaction_by_id(self, tx_id: UUID | str) -> FuelTransaction | None:
        if isinstance(tx_id, str):
            tx_id = UUID(tx_id)
        result = await self.db.execute(
            select(FuelTransaction)
            .options(
                selectinload(FuelTransaction.fuel_type),
                selectinload(FuelTransaction.gas_station),
                selectinload(FuelTransaction.vehicle_ownership),
                selectinload(FuelTransaction.buyer_profile),
                selectinload(FuelTransaction.subsidy_quota),
                selectinload(FuelTransaction.payment_transactions),
            )
            .filter(FuelTransaction.id == tx_id)
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

    async def create_cashier_scan_event(self, scan_event: CashierScanEvent) -> CashierScanEvent:
        self.db.add(scan_event)
        await self.db.commit()
        await self.db.refresh(scan_event)
        return scan_event

    def _cashier_transaction_base_query(
        self,
        cashier_user_id: UUID,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        search: str | None = None,
    ):
        stmt = (
            select(FuelTransaction)
            .options(
                selectinload(FuelTransaction.fuel_type),
                selectinload(FuelTransaction.gas_station),
                selectinload(FuelTransaction.vehicle_ownership),
                selectinload(FuelTransaction.buyer_profile).selectinload(BuyerProfile.user),
                selectinload(FuelTransaction.payment_transactions),
            )
            .filter(FuelTransaction.verified_by_user_id == cashier_user_id)
        )

        if date_from is not None:
            stmt = stmt.filter(FuelTransaction.created_at >= date_from)
        if date_to is not None:
            stmt = stmt.filter(FuelTransaction.created_at <= date_to)

        if search:
            term = f"%{search.strip().lower()}%"
            stmt = stmt.outerjoin(FuelTransaction.fuel_type).outerjoin(FuelTransaction.buyer_profile).outerjoin(
                BuyerProfile.user
            )
            stmt = stmt.filter(
                or_(
                    func.lower(cast(FuelTransaction.id, String)).like(term),
                    func.lower(FuelTransaction.plate_number_snapshot).like(term),
                    func.lower(func.coalesce(FuelTransaction.nik_snapshot, "")).like(term),
                    func.lower(func.coalesce(FuelTransaction.company_name_snapshot, "")).like(term),
                    func.lower(func.coalesce(FuelType.name, "")).like(term),
                    func.lower(cast(FuelTransaction.payment_method, String)).like(term),
                    func.lower(cast(FuelTransaction.transaction_status, String)).like(term),
                    func.lower(func.coalesce(User.name, "")).like(term),
                )
            )

        return stmt

    async def get_cashier_fuel_transactions(
        self,
        cashier_user_id: UUID,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        search: str | None = None,
        cursor_created_at: datetime | None = None,
        cursor_id: UUID | None = None,
        limit: int = 20,
    ) -> list[FuelTransaction]:
        stmt = self._cashier_transaction_base_query(
            cashier_user_id,
            date_from=date_from,
            date_to=date_to,
            search=search,
        )

        if cursor_created_at is not None and cursor_id is not None:
            stmt = stmt.filter(
                or_(
                    FuelTransaction.created_at < cursor_created_at,
                    and_(
                        FuelTransaction.created_at == cursor_created_at,
                        FuelTransaction.id < cursor_id,
                    ),
                )
            )

        result = await self.db.execute(
            stmt.order_by(FuelTransaction.created_at.desc(), FuelTransaction.id.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def count_cashier_fuel_transactions(
        self,
        cashier_user_id: UUID,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        search: str | None = None,
    ) -> int:
        stmt = self._cashier_transaction_base_query(
            cashier_user_id,
            date_from=date_from,
            date_to=date_to,
            search=search,
        )
        result = await self.db.execute(select(func.count()).select_from(stmt.subquery()))
        return int(result.scalar() or 0)

    async def summarize_cashier_fuel_transactions(
        self,
        cashier_user_id: UUID,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        search: str | None = None,
    ) -> dict:
        stmt = self._cashier_transaction_base_query(
            cashier_user_id,
            date_from=date_from,
            date_to=date_to,
            search=search,
        ).subquery()

        result = await self.db.execute(
            select(
                func.count(stmt.c.id),
                func.coalesce(func.sum(
                    case((cast(stmt.c.transaction_status, String) == FuelTransactionStatus.COMPLETED.value, 1), else_=0)
                ), 0),
                func.coalesce(func.sum(
                    case((cast(stmt.c.transaction_status, String) == FuelTransactionStatus.FAILED.value, 1), else_=0)
                ), 0),
                func.coalesce(func.sum(
                    case((cast(stmt.c.transaction_status, String) == FuelTransactionStatus.CANCELLED.value, 1), else_=0)
                ), 0),
                func.coalesce(func.sum(
                    case((cast(stmt.c.transaction_status, String) == FuelTransactionStatus.PENDING.value, 1), else_=0)
                ), 0),
                func.coalesce(func.sum(stmt.c.liters), 0),
                func.coalesce(func.sum(stmt.c.total_amount), 0),
            )
        )
        row = result.one()
        return {
            "total_transactions": int(row[0] or 0),
            "completed_transactions": int(row[1] or 0),
            "failed_transactions": int(row[2] or 0),
            "cancelled_transactions": int(row[3] or 0),
            "pending_transactions": int(row[4] or 0),
            "total_liters": float(row[5] or 0),
            "total_revenue": float(row[6] or 0),
        }

    async def summarize_cashier_performance(
        self,
        cashier_user_id: UUID,
        *,
        date_from: datetime,
        date_to: datetime,
    ) -> dict:
        stmt = self._cashier_transaction_base_query(
            cashier_user_id,
            date_from=date_from,
            date_to=date_to,
        ).subquery()

        result = await self.db.execute(
            select(
                func.count(stmt.c.id),
                func.coalesce(func.sum(
                    case((cast(stmt.c.transaction_status, String) == FuelTransactionStatus.COMPLETED.value, 1), else_=0)
                ), 0),
                func.coalesce(func.sum(
                    case((cast(stmt.c.transaction_status, String) == FuelTransactionStatus.FAILED.value, 1), else_=0)
                ), 0),
                func.coalesce(func.sum(
                    case((cast(stmt.c.transaction_status, String) == FuelTransactionStatus.CANCELLED.value, 1), else_=0)
                ), 0),
                func.coalesce(func.sum(
                    case((cast(stmt.c.transaction_status, String) == FuelTransactionStatus.PENDING.value, 1), else_=0)
                ), 0),
                func.count(func.distinct(stmt.c.plate_number_snapshot)),
                func.coalesce(func.sum(stmt.c.liters), 0),
                func.coalesce(func.sum(
                    case((cast(stmt.c.transaction_status, String) == FuelTransactionStatus.COMPLETED.value, stmt.c.total_amount), else_=0)
                ), 0),
            )
        )
        row = result.one()
        created_at_rows = await self.db.execute(
            select(stmt.c.created_at).order_by(stmt.c.created_at.asc(), stmt.c.id.asc())
        )
        created_at_values = [value for value in created_at_rows.scalars().all() if value is not None]

        average_transaction_minutes = None
        if len(created_at_values) >= 2:
            intervals_in_minutes = [
                (current - previous).total_seconds() / 60
                for previous, current in zip(created_at_values, created_at_values[1:])
            ]
            average_transaction_minutes = fmean(intervals_in_minutes)

        return {
            "total_transactions": int(row[0] or 0),
            "completed_transactions": int(row[1] or 0),
            "failed_transactions": int(row[2] or 0),
            "cancelled_transactions": int(row[3] or 0),
            "pending_transactions": int(row[4] or 0),
            "served_vehicles": int(row[5] or 0),
            "total_liters": float(row[6] or 0),
            "total_revenue": float(row[7] or 0),
            "average_transaction_minutes": average_transaction_minutes,
        }

    async def get_recent_cashier_scan_events(
        self,
        cashier_user_id: UUID,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        cursor_created_at: datetime | None = None,
        cursor_id: UUID | None = None,
        limit: int = 10,
    ) -> list[CashierScanEvent]:
        stmt = (
            select(CashierScanEvent)
            .options(
                selectinload(CashierScanEvent.buyer_profile).selectinload(BuyerProfile.user),
                selectinload(CashierScanEvent.gas_station),
            )
            .filter(CashierScanEvent.cashier_user_id == cashier_user_id)
        )
        if date_from is not None:
            stmt = stmt.filter(CashierScanEvent.created_at >= date_from)
        if date_to is not None:
            stmt = stmt.filter(CashierScanEvent.created_at <= date_to)
        if cursor_created_at is not None and cursor_id is not None:
            stmt = stmt.filter(
                or_(
                    CashierScanEvent.created_at < cursor_created_at,
                    and_(
                        CashierScanEvent.created_at == cursor_created_at,
                        CashierScanEvent.id < cursor_id,
                    ),
                )
            )

        result = await self.db.execute(
            stmt.order_by(CashierScanEvent.created_at.desc(), CashierScanEvent.id.desc()).limit(limit)
        )
        return list(result.scalars().all())

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

    async def get_wallet_transactions_for_wallet(self, wallet_id: UUID) -> list[WalletTransaction]:
        result = await self.db.execute(
            select(WalletTransaction)
            .options(
                selectinload(WalletTransaction.fuel_transactions).selectinload(FuelTransaction.gas_station),
                selectinload(WalletTransaction.fuel_transactions).selectinload(FuelTransaction.fuel_type),
            )
            .filter(WalletTransaction.wallet_id == wallet_id)
            .order_by(WalletTransaction.created_at.desc(), WalletTransaction.id.desc())
        )
        return list(result.scalars().all())

    async def get_fuel_transactions_for_buyer_profile(self, buyer_profile_id: UUID) -> list[FuelTransaction]:
        result = await self.db.execute(
            select(FuelTransaction)
            .options(
                selectinload(FuelTransaction.gas_station),
                selectinload(FuelTransaction.fuel_type),
                selectinload(FuelTransaction.payment_transactions),
            )
            .filter(FuelTransaction.buyer_profile_id == buyer_profile_id)
            .order_by(FuelTransaction.created_at.desc(), FuelTransaction.id.desc())
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
