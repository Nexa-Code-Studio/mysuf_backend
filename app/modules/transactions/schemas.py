from datetime import datetime
from decimal import Decimal
from typing import List
from uuid import UUID
from pydantic import BaseModel, field_validator
from app.core.config import settings
from app.modules.transactions.models import (
    PaymentStatus,
    PaymentProvider,
    TransactionType,
    TransactionFlow,
    WalletTransactionStatus
)

class TopUpRequest(BaseModel):
    amount: Decimal

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be greater than zero")
        min_amount = Decimal(str(settings.MIN_TOPUP_AMOUNT))
        if v < min_amount:
            raise ValueError(f"Amount must be at least IDR {min_amount:,.2f}")
        return v

class TopUpResponse(BaseModel):
    id: UUID
    wallet_id: UUID
    provider: PaymentProvider
    external_id: str
    provider_reference_id: str | None = None
    payment_link_url: str | None = None
    amount: Decimal
    status: PaymentStatus
    created_at: datetime

    class Config:
        from_attributes = True


class WalletTransactionResponse(BaseModel):
    id: UUID
    wallet_id: UUID
    type: TransactionType
    transaction_flow: TransactionFlow
    amount: Decimal
    balance_before: Decimal
    balance_after: Decimal
    counterparty_wallet_id: UUID | None = None
    payment_transaction_id: UUID | None = None
    description: str | None = None
    status: WalletTransactionStatus
    created_at: datetime
    tile_type: str | None = None
    fuel_type_name: str | None = None
    gas_station_name: str | None = None
    liters: Decimal | None = None

    class Config:
        from_attributes = True


class PaginatedWalletTransactionsResponse(BaseModel):
    items: List[WalletTransactionResponse]
    total: int
    page: int
    size: int
    pages: int
