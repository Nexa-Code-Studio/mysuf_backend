import enum
from datetime import datetime
from uuid_extensions import uuid7
from sqlalchemy import Column, String, DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base

class KKVehicleOwnershipStatus(str, enum.Enum):
    OWNED = "OWNED"
    FAMILY_OWNED = "FAMILY_OWNED"
    COMPANY_OWNED = "COMPANY_OWNED"

class VehicleOwnerType(str, enum.Enum):
    BUYER_PROFILE = "BUYER_PROFILE"
    COMPANY = "COMPANY"

class VehicleOwnershipStatus(str, enum.Enum):
    PERSONAL = "PERSONAL"
    COMPANY = "COMPANY"

class KKVehicle(Base):
    __tablename__ = "kk_vehicles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    kk_id = Column(UUID(as_uuid=True), ForeignKey("kk.id"), nullable=False)
    vehicle_id = Column(UUID(as_uuid=True), nullable=False) # Refers to external vehicle_registry_mockup but kept as UUID without explicit FK to mockup

    ownership_status = Column(Enum(KKVehicleOwnershipStatus, name="kk_vehicle_ownership_status_enum"), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    kk = relationship("KK", back_populates="kk_vehicles")


class VehicleOwnership(Base):
    __tablename__ = "vehicle_ownerships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    owner_type = Column(Enum(VehicleOwnerType, name="vehicle_owner_type_enum"), nullable=False)
    owner_id = Column(UUID(as_uuid=True), nullable=False)

    vehicle_id = Column(UUID(as_uuid=True), nullable=False)

    ownership_status = Column(Enum(VehicleOwnershipStatus, name="vehicle_ownership_status_enum"), nullable=False)

    plate_number_snapshot = Column(String, nullable=False)
    ktp_nfc_id_snapshot = Column(String, nullable=False) # User requested to make it not nullable

    assigned_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True) # Added based on user request

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    fuel_transactions = relationship("FuelTransaction", back_populates="vehicle_ownership")
    assigned_user = relationship("User", back_populates="assigned_vehicles")
