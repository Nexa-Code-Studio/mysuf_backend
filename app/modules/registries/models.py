import enum
from datetime import datetime
from uuid_extensions import uuid7
from sqlalchemy import Column, String, DateTime, Numeric, Integer, ForeignKey, Index, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base

class KK(Base):
    __tablename__ = "kk"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    code = Column(String, nullable=False, unique=True)

    # Relationships
    buyer_profiles = relationship("BuyerProfile", back_populates="kk")
    buyer_registration_attempts = relationship(
        "BuyerRegistrationAttempt",
        back_populates="registry_kk",
        foreign_keys="BuyerRegistrationAttempt.registry_kk_id_snapshot",
    )
    kk_subsidy_eligibilities = relationship("KKSubsidyEligibility", back_populates="kk")


class CitizenRegistryMockup(Base):
    __tablename__ = "citizen_registry_mockup"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    nik = Column(String, nullable=False, unique=True)
    nama = Column(String, nullable=False)
    ktp_nfc_id = Column(String, nullable=False, unique=True)
    
    kk_id = Column(UUID(as_uuid=True), ForeignKey("kk.id"), nullable=False)
    
    pekerjaan = Column(String, nullable=True)
    penghasilan = Column(Numeric(18, 2), nullable=True)

    # Relationships
    kk = relationship("KK")
    buyer_registration_attempts = relationship(
        "BuyerRegistrationAttempt",
        back_populates="registry_citizen",
        foreign_keys="BuyerRegistrationAttempt.registry_citizen_id",
    )


class VehicleClass(str, enum.Enum):
    MOTORCYCLE = "MOTORCYCLE"
    CAR = "CAR"
    TRUCK = "TRUCK"


class VehicleRegistryMockup(Base):
    __tablename__ = "vehicle_registry_mockup"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    plate_number = Column(String, nullable=True)
    registration_number = Column(String, nullable=True)
    brand = Column(String, nullable=True)
    vehicle_type = Column(String, nullable=True)
    manufacture_year = Column(Integer, nullable=True)
    color = Column(String, nullable=True)
    engine_capacity_cc = Column(Integer, nullable=True)
    pkb = Column(Numeric(18, 2), nullable=True)
    njkb = Column(Numeric(18, 2), nullable=True)
    owner_name = Column(String, nullable=True)
    owner_nik = Column(String, nullable=True)
    jenis = Column(Enum(VehicleClass, name="vehicle_class_enum"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


