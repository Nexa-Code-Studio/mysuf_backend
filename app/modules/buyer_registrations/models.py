import enum
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Enum, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from uuid_extensions import uuid7

from app.core.database import Base


class BuyerRegistrationStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    FAILED = "FAILED"
    VERIFIED = "VERIFIED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    COMPLETED = "COMPLETED"


class BuyerDocumentType(str, enum.Enum):
    KTP_PHOTO = "KTP_PHOTO"
    SELFIE_PHOTO = "SELFIE_PHOTO"


class BuyerRegistrationAttempt(Base):
    __tablename__ = "buyer_registration_attempts"
    __table_args__ = (
        Index("ix_buyer_registration_attempts_nik_input", "nik_input"),
        Index("ix_buyer_registration_attempts_email", "email"),
        Index("ix_buyer_registration_attempts_status", "status"),
        Index("ix_buyer_registration_attempts_registry_citizen_id", "registry_citizen_id"),
        Index("ix_buyer_registration_attempts_created_user_id", "created_user_id"),
        Index(
            "uq_buyer_registration_attempts_active_nik_input",
            "nik_input",
            unique=True,
            postgresql_where=text(
                "status IN ('PENDING', 'PROCESSING', 'REVIEW_REQUIRED', 'VERIFIED')"
            ),
        ),
        Index(
            "uq_buyer_registration_attempts_active_email",
            "email",
            unique=True,
            postgresql_where=text(
                "status IN ('PENDING', 'PROCESSING', 'REVIEW_REQUIRED', 'VERIFIED')"
            ),
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    nik_input = Column(String, nullable=False)
    email = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    status = Column(
        Enum(BuyerRegistrationStatus, name="buyer_registration_status_enum"),
        default=BuyerRegistrationStatus.PENDING,
        nullable=False,
    )

    nik_ocr = Column(String, nullable=True)
    is_nik_match = Column(Boolean, nullable=True)

    registry_citizen_id = Column(UUID(as_uuid=True), ForeignKey("citizen_registry_mockup.id"), nullable=True)
    registry_name_snapshot = Column(String, nullable=True)
    registry_kk_id_snapshot = Column(UUID(as_uuid=True), ForeignKey("kk.id"), nullable=True)
    registry_ktp_nfc_id_snapshot = Column(String, nullable=True)

    face_match_score = Column(Numeric(5, 4), nullable=True)
    is_face_match = Column(Boolean, nullable=True)
    ocr_raw_text = Column(Text, nullable=True)
    verification_detail = Column(Text, nullable=True)

    failure_reason = Column(String, nullable=True)
    failure_detail = Column(Text, nullable=True)

    created_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_buyer_profile_id = Column(UUID(as_uuid=True), ForeignKey("buyer_profiles.id"), nullable=True)

    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    verification_started_at = Column(DateTime, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    registry_citizen = relationship(
        "CitizenRegistryMockup",
        back_populates="buyer_registration_attempts",
        foreign_keys=[registry_citizen_id],
    )
    registry_kk = relationship(
        "KK",
        back_populates="buyer_registration_attempts",
        foreign_keys=[registry_kk_id_snapshot],
    )
    created_user = relationship(
        "User",
        back_populates="completed_registration_attempts",
        foreign_keys=[created_user_id],
    )
    created_buyer_profile = relationship(
        "BuyerProfile",
        back_populates="registration_attempts",
        foreign_keys=[created_buyer_profile_id],
    )
    documents = relationship(
        "BuyerRegistrationDocument",
        back_populates="registration_attempt",
        cascade="all, delete-orphan",
    )


class BuyerRegistrationDocument(Base):
    __tablename__ = "buyer_registration_documents"
    __table_args__ = (
        UniqueConstraint("registration_attempt_id", "document_type", name="uq_buyer_registration_document_attempt_type"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    registration_attempt_id = Column(UUID(as_uuid=True), ForeignKey("buyer_registration_attempts.id"), nullable=False)
    document_type = Column(Enum(BuyerDocumentType, name="buyer_document_type_enum"), nullable=False)
    storage_key = Column(String, nullable=False)
    original_filename = Column(String, nullable=True)
    mime_type = Column(String, nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    checksum_sha256 = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    registration_attempt = relationship("BuyerRegistrationAttempt", back_populates="documents")
    profile_documents = relationship(
        "BuyerProfileDocument",
        back_populates="source_registration_document",
    )


class BuyerProfileDocument(Base):
    __tablename__ = "buyer_profile_documents"
    __table_args__ = (
        UniqueConstraint("buyer_profile_id", "document_type", name="uq_buyer_profile_document_profile_type"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    buyer_profile_id = Column(UUID(as_uuid=True), ForeignKey("buyer_profiles.id"), nullable=False)
    document_type = Column(Enum(BuyerDocumentType, name="buyer_document_type_enum", create_type=False), nullable=False)
    storage_key = Column(String, nullable=False)
    original_filename = Column(String, nullable=True)
    mime_type = Column(String, nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    checksum_sha256 = Column(String, nullable=True)
    source_registration_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("buyer_registration_documents.id"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    buyer_profile = relationship("BuyerProfile", back_populates="documents")
    source_registration_document = relationship(
        "BuyerRegistrationDocument",
        back_populates="profile_documents",
    )
