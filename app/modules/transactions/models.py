import enum
from datetime import datetime
from uuid_extensions import uuid7
from sqlalchemy import Column, String, DateTime, Enum, Numeric, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base

class PaymentProvider(str, enum.Enum):
    XENDIT = "XENDIT"
    MOCK = "MOCK"
    MANUAL = "MANUAL"

class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"

class TransactionType(str, enum.Enum):
    TOP_UP = "TOP_UP"
    FUEL_PURCHASE = "FUEL_PURCHASE"
    PAYMENT = "PAYMENT"
    WITHDRAWAL = "WITHDRAWAL"
    REFUND = "REFUND"
    TRANSFER = "TRANSFER"
    ADMIN_ADJUSTMENT = "ADMIN_ADJUSTMENT"

class TransactionFlow(str, enum.Enum):
    IN = "IN"
    OUT = "OUT"

class WalletTransactionStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

class BuyerType(str, enum.Enum):
    PERSONAL = "PERSONAL"
    COMPANY = "COMPANY"

class PaymentMethod(str, enum.Enum):
    WALLET = "WALLET"
    CASH = "CASH"
    EDC = "EDC"
    QRIS = "QRIS"

class FuelTransactionStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"

class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    wallet_id = Column(UUID(as_uuid=True), ForeignKey("wallets.id"), nullable=False)

    provider = Column(Enum(PaymentProvider, name="payment_provider_enum"), nullable=False)
    external_id = Column(String, nullable=False)
    provider_reference_id = Column(String, nullable=True)
    payment_link_url = Column(String, nullable=True)

    amount = Column(Numeric(18, 2), nullable=False)
    status = Column(Enum(PaymentStatus, name="payment_status_enum"), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    wallet = relationship("Wallet", back_populates="payment_transactions")
    wallet_transactions = relationship("WalletTransaction", back_populates="payment_transaction")

class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    wallet_id = Column(UUID(as_uuid=True), ForeignKey("wallets.id"), nullable=False)

    type = Column(Enum(TransactionType, name="transaction_type_enum"), nullable=False)
    transaction_flow = Column(Enum(TransactionFlow, name="transaction_flow_enum"), nullable=False)

    amount = Column(Numeric(18, 2), nullable=False)
    balance_before = Column(Numeric(18, 2), nullable=False)
    balance_after = Column(Numeric(18, 2), nullable=False)

    counterparty_wallet_id = Column(UUID(as_uuid=True), ForeignKey("wallets.id"), nullable=True)
    payment_transaction_id = Column(UUID(as_uuid=True), ForeignKey("payment_transactions.id"), nullable=True)

    description = Column(String, nullable=True)
    status = Column(Enum(WalletTransactionStatus, name="wallet_transaction_status_enum"), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    wallet = relationship("Wallet", foreign_keys=[wallet_id], back_populates="wallet_transactions")
    counterparty_wallet = relationship("Wallet", foreign_keys=[counterparty_wallet_id])
    payment_transaction = relationship("PaymentTransaction", back_populates="wallet_transactions")
    fuel_transactions = relationship("FuelTransaction", back_populates="wallet_transaction")

class FuelTransaction(Base):
    __tablename__ = "fuel_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    buyer_type = Column(Enum(BuyerType, name="buyer_type_enum"), nullable=False)
    buyer_profile_id = Column(UUID(as_uuid=True), ForeignKey("buyer_profiles.id"), nullable=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True)
    vehicle_ownership_id = Column(UUID(as_uuid=True), ForeignKey("vehicle_ownerships.id"), nullable=True)

    gas_station_id = Column(UUID(as_uuid=True), ForeignKey("gas_stations.id"), nullable=False)
    fuel_type_id = Column(UUID(as_uuid=True), ForeignKey("fuel_types.id"), nullable=False)

    liters = Column(Numeric(10, 2), nullable=False)

    subsidy_quota_id = Column(UUID(as_uuid=True), ForeignKey("subsidy_quotas.id"), nullable=True)
    kk_subsidy_eligibility_id = Column(UUID(as_uuid=True), ForeignKey("kk_subsidy_eligibilities.id"), nullable=True)

    is_subsidized = Column(Boolean, nullable=False)
    subsidized_liters = Column(Numeric(10, 2), nullable=False, default=0)
    non_subsidized_liters = Column(Numeric(10, 2), nullable=False, default=0)

    market_price_per_liter = Column(Numeric(18, 2), nullable=False)
    subsidized_price_per_liter = Column(Numeric(18, 2), nullable=True)

    total_amount = Column(Numeric(18, 2), nullable=False)

    payment_method = Column(Enum(PaymentMethod, name="payment_method_enum"), nullable=False)
    wallet_transaction_id = Column(UUID(as_uuid=True), ForeignKey("wallet_transactions.id"), nullable=True)
    
    transaction_status = Column(Enum(FuelTransactionStatus, name="fuel_transaction_status_enum"), nullable=False)

    verified_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    plate_number_snapshot = Column(String, nullable=False)
    nik_snapshot = Column(String, nullable=True)
    company_name_snapshot = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    buyer_profile = relationship("BuyerProfile", back_populates="fuel_transactions")
    company = relationship("Company", back_populates="fuel_transactions")
    vehicle_ownership = relationship("VehicleOwnership", back_populates="fuel_transactions")
    gas_station = relationship("GasStation", back_populates="fuel_transactions")
    fuel_type = relationship("FuelType", back_populates="fuel_transactions")
    subsidy_quota = relationship("SubsidyQuota", back_populates="fuel_transactions")
    kk_subsidy_eligibility = relationship("KKSubsidyEligibility", back_populates="fuel_transactions")
    wallet_transaction = relationship("WalletTransaction", back_populates="fuel_transactions")


class WebhookAuditLog(Base):
    __tablename__ = "webhook_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    provider = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    payload = Column(String, nullable=False)  # Raw JSON payload
    created_at = Column(DateTime, default=datetime.utcnow)
