from datetime import datetime
from uuid_extensions import uuid7
from sqlalchemy import Column, String, DateTime, Numeric, Integer, ForeignKey, Index
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

    # Relationships
    kk = relationship("KK")
    buyer_registration_attempts = relationship(
        "BuyerRegistrationAttempt",
        back_populates="registry_citizen",
        foreign_keys="BuyerRegistrationAttempt.registry_citizen_id",
    )


class VehicleRegistryMockup(Base):
    __tablename__ = "vehicle_registry_mockup"
    __table_args__ = (
        Index("ix_vehicle_registry_mockup_plate_number", "plate_number"),
        Index("ix_vehicle_registry_mockup_registration_number", "registration_number"),
        Index("ix_vehicle_registry_mockup_owner_nik", "owner_nik"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    plate_number = Column(String, nullable=False)
    registration_number = Column(String, nullable=False) # Nomor STNK

    brand = Column(String, nullable=False)               # Merk Kendaraan
    vehicle_type = Column(String, nullable=False)        # Tipe Kendaraan

    manufacture_year = Column(Integer, nullable=False)   # Tahun Kendaraan

    color = Column(String, nullable=False)               # Warna Kendaraan

    engine_capacity_cc = Column(Integer, nullable=False) # Kapasitas Mesin (CC)

    pkb = Column(Numeric(18, 2), nullable=False)         # Pajak Kendaraan Bermotor
    njkb = Column(Numeric(18, 2), nullable=False)        # Nilai Jual Kendaraan Bermotor

    owner_name = Column(String, nullable=True)
    owner_nik = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
