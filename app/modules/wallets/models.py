import enum
from datetime import datetime
from uuid_extensions import uuid7
from sqlalchemy import Column, DateTime, Enum, Numeric, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base

class OwnerType(str, enum.Enum):
    USER = "USER"
    GAS_STATION = "GAS_STATION"
    COMPANY = "COMPANY"

class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    owner_type = Column(Enum(OwnerType, name="owner_type_enum"), nullable=False)
    owner_id = Column(UUID(as_uuid=True), nullable=False) # Polymorphic reference

    balance = Column(Numeric(18, 2), default=0.0, nullable=False)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    payment_transactions = relationship("PaymentTransaction", back_populates="wallet")
    wallet_transactions = relationship("WalletTransaction", back_populates="wallet", foreign_keys="[WalletTransaction.wallet_id]")
