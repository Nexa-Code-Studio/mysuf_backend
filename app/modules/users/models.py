import enum
from datetime import datetime
from uuid_extensions import uuid7
from sqlalchemy import Column, String, Boolean, DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship

from app.core.database import Base

class UserRole(str, enum.Enum):
    SUPERADMIN = "SUPERADMIN"
    ADMIN_GAS_STATION = "ADMIN_GAS_STATION"
    ADMIN_COMPANY = "ADMIN_COMPANY"
    BUYER = "BUYER"

class VerificationStatus(str, enum.Enum):
    UNVERIFIED = "UNVERIFIED"
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    role = Column(ARRAY(Enum(UserRole, name="user_role_enum", create_type=False)), nullable=False) # We will rely on postgres creating the array
    is_active = Column(Boolean, default=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    employee_id = Column(String, nullable=True)
    gas_station_id = Column(UUID(as_uuid=True), ForeignKey("gas_stations.id"), nullable=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True)

    # Relationships
    buyer_profile = relationship("BuyerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    assigned_vehicles = relationship("VehicleOwnership", back_populates="assigned_user")


class BuyerProfile(Base):
    __tablename__ = "buyer_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    nik_snapshot = Column(String, nullable=False)
    ktp_nfc_id_snapshot = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    kk_id = Column(UUID(as_uuid=True), ForeignKey("kk.id"), nullable=False)

    verification_status = Column(Enum(VerificationStatus, name="verification_status_enum"), default=VerificationStatus.UNVERIFIED, nullable=False)

    # Relationships
    user = relationship("User", back_populates="buyer_profile")
    kk = relationship("KK", back_populates="buyer_profiles")
    fuel_transactions = relationship("FuelTransaction", back_populates="buyer_profile")
    subsidy_quotas = relationship("SubsidyQuota", primaryjoin="and_(foreign(SubsidyQuota.owner_id)==BuyerProfile.id, SubsidyQuota.owner_type=='BUYER_PROFILE')")

