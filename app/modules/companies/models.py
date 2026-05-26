from datetime import datetime
from uuid_extensions import uuid7
from sqlalchemy import Column, String, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base

class Company(Base):
    __tablename__ = "companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    name = Column(String, nullable=False)
    
    # Registration & Legal details
    nib = Column(String(13), unique=True, index=True, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    fleet_size = Column(Integer, nullable=True)
    siup_no = Column(String, nullable=True)
    tdp_no = Column(String, nullable=True)
    npwp_no = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String, default="Belum Verifikasi", nullable=False)
    
    # Supporting Document Files (filepaths or URLs)
    siup_doc = Column(String, nullable=True)
    tdp_doc = Column(String, nullable=True)
    npwp_doc = Column(String, nullable=True)
    nib_doc = Column(String, nullable=True)
    
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Relationships
    fuel_transactions = relationship("FuelTransaction", back_populates="company")
