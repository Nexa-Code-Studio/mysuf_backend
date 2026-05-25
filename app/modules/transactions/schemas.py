from datetime import datetime
from decimal import Decimal
from typing import List
from uuid import UUID
from pydantic import BaseModel, field_validator, ConfigDict
from app.core.config import settings
from app.modules.transactions.models import (
    CashierScanMethod,
    CashierScanResult,
    FuelTransactionStatus,
    PaymentStatus,
    PaymentProvider,
    PaymentMethod,
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

    model_config = ConfigDict(from_attributes=True)


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
    payment_method: PaymentMethod | None = None
    description: str | None = None
    status: WalletTransactionStatus
    created_at: datetime
    tile_type: str | None = None
    fuel_type_name: str | None = None
    gas_station_name: str | None = None
    liters: Decimal | None = None

    model_config = ConfigDict(from_attributes=True)


class PaginatedWalletTransactionsResponse(BaseModel):
    items: List[WalletTransactionResponse]
    total: int
    page: int
    size: int
    pages: int

class SearchRecipientResponse(BaseModel):
    name: str
    nik_masked: str
    recipient_user_id: UUID

class TransferRequest(BaseModel):
    recipient_nik: str
    amount: Decimal
    pin: str | None = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        if v < Decimal("10000"):
            raise ValueError("Minimal nominal transfer adalah Rp 10.000")
        return v


class FuelPurchaseRequest(BaseModel):
    nik: str
    plate_number: str
    fuel_type_id: UUID
    liters: Decimal
    total_amount: Decimal
    payment_method: PaymentMethod
    amount_paid: Decimal | None = None
    pin: str | None = None

    @field_validator("liters")
    @classmethod
    def validate_liters(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Volume pembelian harus lebih besar dari 0 liter.")
        return v

    @field_validator("total_amount")
    @classmethod
    def validate_total_amount(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Total harga pembelian harus lebih besar dari Rp 0.")
        return v

    @field_validator("amount_paid")
    @classmethod
    def validate_amount_paid(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v <= 0:
            raise ValueError("Nominal uang diterima harus lebih besar dari Rp 0.")
        return v

    @field_validator("pin")
    @classmethod
    def validate_pin_if_provided(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("PIN tidak boleh kosong.")
        return v

    @field_validator("payment_method")
    @classmethod
    def validate_payment_method(cls, v: PaymentMethod) -> PaymentMethod:
        if v not in {PaymentMethod.WALLET, PaymentMethod.CASH}:
            raise ValueError("Metode pembayaran tidak didukung untuk transaksi kasir.")
        return v

    @field_validator("amount_paid", mode="after")
    @classmethod
    def validate_cash_paid_amount(cls, v: Decimal | None, info):
        payment_method = info.data.get("payment_method")
        total_amount = info.data.get("total_amount")

        if payment_method == PaymentMethod.CASH:
            if v is None:
                raise ValueError("Nominal uang diterima wajib diisi untuk pembayaran tunai.")
            if total_amount is not None and v < total_amount:
                raise ValueError("Nominal uang diterima tidak boleh kurang dari total harga.")
        return v


class FuelPurchaseResponse(BaseModel):
    transaction_id: UUID
    wallet_transaction_id: UUID | None = None
    plate_number: str
    fuel_name: str
    liters: Decimal
    total_amount: Decimal
    status: str
    created_at: datetime
    detected_frauds: List[dict] = []
    risk_score: int = 0
    risk_level: str = "SAFE"
    action_taken: str = "ALLOW TRANSACTION"

    model_config = ConfigDict(from_attributes=True)


class QrisFuelPurchaseRequest(BaseModel):
    nik: str
    plate_number: str
    fuel_type_id: UUID
    liters: Decimal
    total_amount: Decimal

    @field_validator("liters")
    @classmethod
    def validate_liters(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Volume pembelian harus lebih besar dari 0 liter.")
        return v

    @field_validator("total_amount")
    @classmethod
    def validate_total_amount(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Total harga pembelian harus lebih besar dari Rp 0.")
        return v


class QrisFuelPurchaseResponse(BaseModel):
    transaction_id: UUID
    provider_reference_id: str
    external_id: str
    qr_string: str
    total_amount: Decimal
    fuel_name: str
    liters: Decimal
    plate_number: str
    status: str
    expires_at: datetime | None = None
    detected_frauds: List[dict] = []
    risk_score: int = 0
    risk_level: str = "SAFE"
    action_taken: str = "ALLOW TRANSACTION"


class QrisFuelPurchaseStatusResponse(BaseModel):
    transaction_id: UUID
    provider_reference_id: str
    status: str
    payment_status: PaymentStatus
    total_amount: Decimal
    fuel_name: str
    liters: Decimal
    plate_number: str
    expires_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class XenditFuelPurchaseRequest(BaseModel):
    nik: str
    plate_number: str
    fuel_type_id: UUID
    liters: Decimal
    total_amount: Decimal

    @field_validator("liters")
    @classmethod
    def validate_liters(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Volume pembelian harus lebih besar dari 0 liter.")
        return v

    @field_validator("total_amount")
    @classmethod
    def validate_total_amount(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Total harga pembelian harus lebih besar dari Rp 0.")
        return v


class XenditFuelPurchaseResponse(BaseModel):
    transaction_id: UUID
    provider_reference_id: str
    external_id: str
    payment_link_url: str
    total_amount: Decimal
    fuel_name: str
    liters: Decimal
    plate_number: str
    status: str
    expires_at: datetime | None = None
    detected_frauds: List[dict] = []
    risk_score: int = 0
    risk_level: str = "SAFE"
    action_taken: str = "ALLOW TRANSACTION"


class XenditFuelPurchaseStatusResponse(BaseModel):
    transaction_id: UUID
    provider_reference_id: str
    payment_link_url: str | None = None
    status: str
    payment_status: PaymentStatus
    total_amount: Decimal
    fuel_name: str
    liters: Decimal
    plate_number: str
    expires_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class CashierTransactionSummaryResponse(BaseModel):
    total_transactions: int
    completed_transactions: int
    failed_transactions: int
    cancelled_transactions: int = 0
    pending_transactions: int
    total_liters: float
    total_revenue: float


class CashierTransactionListItemResponse(BaseModel):
    id: UUID
    created_at: datetime
    transaction_status: FuelTransactionStatus
    payment_method: PaymentMethod
    plate_number_snapshot: str
    nik_snapshot: str | None = None
    buyer_name: str | None = None
    fuel_name: str
    liters: float
    total_amount: float
    gas_station_name: str
    cashier_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CashierTransactionListResponse(BaseModel):
    summary: CashierTransactionSummaryResponse | None = None
    items: list[CashierTransactionListItemResponse]
    next_cursor: str | None = None
    has_more: bool = False


class CashierRecentScanItemResponse(BaseModel):
    id: UUID
    created_at: datetime
    lookup_method: CashierScanMethod
    result: CashierScanResult
    lookup_value: str
    buyer_name: str | None = None
    nik_masked: str | None = None
    error_message: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CashierRecentScanListResponse(BaseModel):
    items: list[CashierRecentScanItemResponse]
    next_cursor: str | None = None
    has_more: bool = False


class CashierPerformanceSummaryResponse(BaseModel):
    total_transactions: int
    completed_transactions: int
    failed_transactions: int
    cancelled_transactions: int
    pending_transactions: int
    served_vehicles: int
    total_liters: float
    total_revenue: float
    average_transaction_minutes: float | None = None


class CashierPerformanceResponse(BaseModel):
    summary: CashierPerformanceSummaryResponse
    recent_transactions: list[CashierTransactionListItemResponse]
