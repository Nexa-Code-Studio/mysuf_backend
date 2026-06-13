from datetime import datetime
from uuid_extensions import uuid7
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base

class SystemAuditLog(Base):
    __tablename__ = "system_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_name_snapshot = Column(String, nullable=False)
    actor_role_snapshot = Column(String, nullable=False)
    action = Column(String, nullable=False)
    ip_address = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    actor = relationship("User")
