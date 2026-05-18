import enum
from datetime import datetime
from uuid_extensions import uuid7
from sqlalchemy import Column, String, DateTime, Enum, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base

class FuelCategory(str, enum.Enum):
    DIESEL = "DIESEL"
    GASOLINE = "GASOLINE"

class SubsidyType(str, enum.Enum):
    SUBSIDIZED = "SUBSIDIZED"
    NON_SUBSIDIZED = "NON_SUBSIDIZED"

class FuelType(Base):
    __tablename__ = "fuel_types"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    name = Column(String, nullable=False)
    octane = Column(String, nullable=True)

    category = Column(Enum(FuelCategory, name="fuel_category_enum"), nullable=False)

    price_per_liter = Column(Numeric(18, 2), nullable=False)
    subsidy_price_per_liter = Column(Numeric(18, 2), nullable=True)

    subsidy_type = Column(Enum(SubsidyType, name="subsidy_type_enum"), nullable=False)

    timestamp = Column(DateTime, default=datetime.utcnow)

    # Relationships
    fuel_transactions = relationship("FuelTransaction", back_populates="fuel_type")
