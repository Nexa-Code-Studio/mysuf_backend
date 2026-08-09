import enum
from datetime import datetime
from uuid_extensions import uuid7
from sqlalchemy import Column, String, DateTime, Enum, Numeric, Boolean, ForeignKey, Index, Text, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
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
    XENDIT = "XENDIT"

class FuelTransactionStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class CashierScanMethod(str, enum.Enum):
    NFC = "NFC"
    NIK = "NIK"
    QR = "QR"


class CashierScanResult(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    wallet_id = Column(UUID(as_uuid=True), ForeignKey("wallets.id"), nullable=False)
    fuel_transaction_id = Column(UUID(as_uuid=True), ForeignKey("fuel_transactions.id"), nullable=True)

    provider = Column(Enum(PaymentProvider, name="payment_provider_enum"), nullable=False)
    external_id = Column(String, nullable=False)
    provider_reference_id = Column(String, nullable=True)
    payment_link_url = Column(String, nullable=True)
    qr_string = Column(String, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    amount = Column(Numeric(18, 2), nullable=False)
    status = Column(Enum(PaymentStatus, name="payment_status_enum"), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    wallet = relationship("Wallet", back_populates="payment_transactions")
    wallet_transactions = relationship("WalletTransaction", back_populates="payment_transaction")
    fuel_transaction = relationship("FuelTransaction", back_populates="payment_transactions")

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
    vehicle_nfc_id_snapshot = Column(String, nullable=True)

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
    payment_transactions = relationship("PaymentTransaction", back_populates="fuel_transaction")
    verified_by = relationship("User", foreign_keys=[verified_by_user_id])



class CashierScanEvent(Base):
    __tablename__ = "cashier_scan_events"
    __table_args__ = (
        Index("ix_cashier_scan_events_cashier_created_at", "cashier_user_id", "created_at", "id"),
        Index("ix_cashier_scan_events_gas_station_created_at", "gas_station_id", "created_at", "id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    cashier_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    gas_station_id = Column(UUID(as_uuid=True), ForeignKey("gas_stations.id"), nullable=True)
    lookup_method = Column(Enum(CashierScanMethod, name="cashier_scan_method_enum"), nullable=False)
    lookup_value = Column(String, nullable=False)
    result = Column(Enum(CashierScanResult, name="cashier_scan_result_enum"), nullable=False)
    buyer_profile_id = Column(UUID(as_uuid=True), ForeignKey("buyer_profiles.id"), nullable=True)
    vehicle_ownership_id = Column(UUID(as_uuid=True), ForeignKey("vehicle_ownerships.id"), nullable=True)
    fuel_transaction_id = Column(UUID(as_uuid=True), ForeignKey("fuel_transactions.id"), nullable=True)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    cashier_user = relationship("User")
    gas_station = relationship("GasStation")
    buyer_profile = relationship("BuyerProfile")
    vehicle_ownership = relationship("VehicleOwnership")
    fuel_transaction = relationship("FuelTransaction")


class WebhookAuditLog(Base):
    __tablename__ = "webhook_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    provider = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    payload = Column(String, nullable=False)  # Raw JSON payload
    created_at = Column(DateTime, default=datetime.utcnow)


class FraudRiskLevel(str, enum.Enum):
    SAFE = "SAFE"
    SUSPICIOUS = "SUSPICIOUS"
    HIGH_RISK = "HIGH_RISK"
    CRITICAL = "CRITICAL"


class FraudActionTaken(str, enum.Enum):
    ALLOW_TRANSACTION = "ALLOW_TRANSACTION"
    WARNING = "WARNING"
    FREEZE_ACCOUNT = "FREEZE_ACCOUNT"
    BLOCK_ACCOUNT = "BLOCK_ACCOUNT"


class FraudCaseStatus(str, enum.Enum):
    PENDING = "PENDING"
    FLAGGED = "FLAGGED"
    RESOLVED = "RESOLVED"


class FraudLog(Base):
    __tablename__ = "fraud_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    case_id = Column(String(20), nullable=False, unique=True, index=True)
    
    # Foreign Keys
    fuel_transaction_id = Column(UUID(as_uuid=True), ForeignKey("fuel_transactions.id"), nullable=True)
    gas_station_id = Column(UUID(as_uuid=True), ForeignKey("gas_stations.id"), nullable=False)
    buyer_profile_id = Column(UUID(as_uuid=True), ForeignKey("buyer_profiles.id"), nullable=True)
    vehicle_ownership_id = Column(UUID(as_uuid=True), ForeignKey("vehicle_ownerships.id"), nullable=True)
    
    # Snapshots (Integritas Data Historis)
    plate_number_snapshot = Column(String(50), nullable=False)
    nik_snapshot = Column(String(50), nullable=True)
    
    # AI Engine Results
    risk_score = Column(Integer, nullable=False, default=0)
    risk_level = Column(Enum(FraudRiskLevel, name="fraud_risk_level_enum"), nullable=False, default=FraudRiskLevel.SAFE)
    action_taken = Column(Enum(FraudActionTaken, name="fraud_action_taken_enum"), nullable=False, default=FraudActionTaken.ALLOW_TRANSACTION)
    detected_frauds = Column(JSONB, nullable=False, default=list) # Menyimpan detail pelanggaran spesifik
    
    # Workflow Status
    status = Column(Enum(FraudCaseStatus, name="fraud_case_status_enum"), nullable=False, default=FraudCaseStatus.PENDING)
    resolution_notes = Column(Text, nullable=True)
    resolved_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    fuel_transaction = relationship("FuelTransaction", foreign_keys=[fuel_transaction_id])
    gas_station = relationship("GasStation", foreign_keys=[gas_station_id])
    buyer_profile = relationship("BuyerProfile", foreign_keys=[buyer_profile_id])
    vehicle_ownership = relationship("VehicleOwnership", foreign_keys=[vehicle_ownership_id])
    resolved_by = relationship("User", foreign_keys=[resolved_by_user_id])
