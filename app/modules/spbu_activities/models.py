import enum
from datetime import datetime
from uuid_extensions import uuid7
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base

class SpbuActivityCategory(str, enum.Enum):
    Sistem = "Sistem"
    Penjualan = "Penjualan"
    Keamanan = "Keamanan"

class SpbuActivityLog(Base):
    __tablename__ = "spbu_activity_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    gas_station_id = Column(UUID(as_uuid=True), ForeignKey("gas_stations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    category = Column(Enum(SpbuActivityCategory, name="spbu_activity_category_enum"), nullable=False)
    detail = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    gas_station = relationship("GasStation")
    user = relationship("User")
