import enum
from datetime import datetime
from uuid_extensions import uuid7
from sqlalchemy import Column, String, DateTime, Enum, Numeric, Boolean, Integer, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.modules.vehicles.models import VehicleUsageType

class EligibilityStatus(str, enum.Enum):
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"

class SubsidyOwnerType(str, enum.Enum):
    BUYER_PROFILE = "BUYER_PROFILE"
    VEHICLE = "VEHICLE"

class SubsidyPolicy(Base):
    __tablename__ = "subsidy_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    name = Column(String, nullable=False)
    usage_type = Column(
        Enum(VehicleUsageType, name="vehicle_usage_type_enum", create_type=False),
        nullable=False,
        unique=True,
    )
    monthly_quota_liters = Column(Numeric(10, 2), nullable=False)
    max_allowed_njkb = Column(Numeric(18, 2), nullable=False)

    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    kk_subsidy_eligibilities = relationship("KKSubsidyEligibility", back_populates="subsidy_policy")
    subsidy_quotas = relationship("SubsidyQuota", back_populates="subsidy_policy")

class KKSubsidyEligibility(Base):
    __tablename__ = "kk_subsidy_eligibilities"
    __table_args__ = (
        Index("ix_kk_subsidy_eligibilities_kk_id", "kk_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    kk_id = Column(UUID(as_uuid=True), ForeignKey("kk.id"), nullable=False)
    subsidy_policy_id = Column(UUID(as_uuid=True), ForeignKey("subsidy_policies.id"), nullable=False)

    total_njkb = Column(Numeric(18, 2), nullable=False)

    eligibility_status = Column(Enum(EligibilityStatus, name="eligibility_status_enum"), nullable=False)
    eligibility_reason = Column(String, nullable=True)

    checked_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    kk = relationship("KK", back_populates="kk_subsidy_eligibilities")
    subsidy_policy = relationship("SubsidyPolicy", back_populates="kk_subsidy_eligibilities")
    subsidy_quotas = relationship("SubsidyQuota", back_populates="kk_subsidy_eligibility")
    fuel_transactions = relationship("FuelTransaction", back_populates="kk_subsidy_eligibility")


class SubsidyQuota(Base):
    __tablename__ = "subsidy_quotas"
    __table_args__ = (
        UniqueConstraint("owner_type", "owner_id", "month", "year", name="uq_subsidy_quotas_owner_month"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    owner_type = Column(Enum(SubsidyOwnerType, name="subsidy_owner_type_enum"), nullable=False)
    owner_id = Column(UUID(as_uuid=True), nullable=False)

    subsidy_policy_id = Column(UUID(as_uuid=True), ForeignKey("subsidy_policies.id"), nullable=True)
    kk_subsidy_eligibility_id = Column(UUID(as_uuid=True), ForeignKey("kk_subsidy_eligibilities.id"), nullable=True)

    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)

    quota_liters = Column(Numeric(10, 2), nullable=False)
    used_liters = Column(Numeric(10, 2), nullable=False, default=0)

    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    subsidy_policy = relationship("SubsidyPolicy", back_populates="subsidy_quotas")
    kk_subsidy_eligibility = relationship("KKSubsidyEligibility", back_populates="subsidy_quotas")
    fuel_transactions = relationship("FuelTransaction", back_populates="subsidy_quota")
