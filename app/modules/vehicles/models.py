import enum
from datetime import datetime
from uuid_extensions import uuid7
from sqlalchemy import BigInteger, Column, String, DateTime, Enum, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base

class VehicleOwnerType(str, enum.Enum):
    BUYER_PROFILE = "BUYER_PROFILE"
    COMPANY = "COMPANY"


class VehicleUsageType(str, enum.Enum):
    PERSONAL = "PERSONAL"
    OJOL = "OJOL"
    UMKM = "UMKM"
    COMPANY_OPERATIONAL = "COMPANY_OPERATIONAL"


class VehicleQuotaMode(str, enum.Enum):
    OWNER_PERSONAL_QUOTA = "OWNER_PERSONAL_QUOTA"
    DEDICATED_VEHICLE_QUOTA = "DEDICATED_VEHICLE_QUOTA"


class VehicleOwnershipStatus(str, enum.Enum):
    PERSONAL = "PERSONAL"
    COMPANY = "COMPANY"


class VehicleOwnershipDocumentType(str, enum.Enum):
    STNK_PHOTO = "STNK_PHOTO"
    VEHICLE_PHOTO = "VEHICLE_PHOTO"
    PRODUCTIVE_BUSINESS_PROOF = "PRODUCTIVE_BUSINESS_PROOF"


class VehicleOwnershipRequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class VehicleOwnership(Base):
    __tablename__ = "vehicle_ownerships"
    __table_args__ = (
        Index("ix_vehicle_ownerships_owner_type_owner_id", "owner_type", "owner_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    owner_type = Column(Enum(VehicleOwnerType, name="vehicle_owner_type_enum"), nullable=False)
    owner_id = Column(UUID(as_uuid=True), nullable=False)

    vehicle_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    ownership_status = Column(Enum(VehicleOwnershipStatus, name="vehicle_ownership_status_enum"), nullable=False)
    usage_type = Column(
        Enum(VehicleUsageType, name="vehicle_usage_type_enum"),
        nullable=False,
        index=True,
    )
    quota_mode = Column(
        Enum(VehicleQuotaMode, name="vehicle_quota_mode_enum"),
        nullable=False,
        index=True,
    )

    plate_number_snapshot = Column(String, nullable=False)
    # Scanner resolves the current operational owner from this NFC snapshot.
    ktp_nfc_id_snapshot = Column(String, nullable=False, index=True)

    assigned_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True) # Added based on user request

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    fuel_transactions = relationship("FuelTransaction", back_populates="vehicle_ownership")
    assigned_user = relationship("User", back_populates="assigned_vehicles")
    documents = relationship(
        "VehicleOwnershipDocument",
        back_populates="vehicle_ownership",
        cascade="all, delete-orphan",
    )


class VehicleOwnershipDocument(Base):
    __tablename__ = "vehicle_ownership_documents"
    __table_args__ = (
        UniqueConstraint(
            "vehicle_ownership_id",
            "document_type",
            name="uq_vehicle_ownership_document_type",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    vehicle_ownership_id = Column(
        UUID(as_uuid=True),
        ForeignKey("vehicle_ownerships.id"),
        nullable=False,
    )
    document_type = Column(
        Enum(VehicleOwnershipDocumentType, name="vehicle_ownership_document_type_enum"),
        nullable=False,
    )
    storage_key = Column(String, nullable=False)
    original_filename = Column(String, nullable=True)
    mime_type = Column(String, nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    checksum_sha256 = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    vehicle_ownership = relationship("VehicleOwnership", back_populates="documents")


class VehicleOwnershipRequest(Base):
    __tablename__ = "vehicle_ownership_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    buyer_profile_id = Column(UUID(as_uuid=True), ForeignKey("buyer_profiles.id"), nullable=False, index=True)
    vehicle_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    ownership_status = Column(Enum(VehicleOwnershipStatus, name="vehicle_ownership_status_enum", create_type=False), nullable=False)
    usage_type = Column(
        Enum(VehicleUsageType, name="vehicle_usage_type_enum", create_type=False),
        nullable=False,
        index=True,
    )
    quota_mode = Column(
        Enum(VehicleQuotaMode, name="vehicle_quota_mode_enum", create_type=False),
        nullable=False,
    )
    plate_number_snapshot = Column(String, nullable=False)
    ktp_nfc_id_snapshot = Column(String, nullable=False)
    status = Column(
        Enum(VehicleOwnershipRequestStatus, name="vehicle_ownership_request_status_enum"),
        nullable=False,
        default=VehicleOwnershipRequestStatus.PENDING,
        index=True,
    )
    review_note = Column(String, nullable=True)
    reviewed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_vehicle_ownership_id = Column(UUID(as_uuid=True), ForeignKey("vehicle_ownerships.id"), nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    buyer_profile = relationship("BuyerProfile")
    reviewed_by_user = relationship("User", foreign_keys=[reviewed_by_user_id])
    approved_vehicle_ownership = relationship("VehicleOwnership", foreign_keys=[approved_vehicle_ownership_id])
    documents = relationship(
        "VehicleOwnershipRequestDocument",
        back_populates="vehicle_ownership_request",
        cascade="all, delete-orphan",
    )


class VehicleOwnershipRequestDocument(Base):
    __tablename__ = "vehicle_ownership_request_documents"
    __table_args__ = (
        UniqueConstraint(
            "vehicle_ownership_request_id",
            "document_type",
            name="uq_vehicle_ownership_request_document_type",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    vehicle_ownership_request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("vehicle_ownership_requests.id"),
        nullable=False,
    )
    document_type = Column(
        Enum(VehicleOwnershipDocumentType, name="vehicle_ownership_document_type_enum", create_type=False),
        nullable=False,
    )
    storage_key = Column(String, nullable=False)
    original_filename = Column(String, nullable=True)
    mime_type = Column(String, nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    checksum_sha256 = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    vehicle_ownership_request = relationship("VehicleOwnershipRequest", back_populates="documents")
