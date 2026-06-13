from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict

class SystemAuditLogResponse(BaseModel):
    id: UUID
    actor_id: UUID | None = None
    actor_name_snapshot: str
    actor_role_snapshot: str
    action: str
    ip_address: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class SystemAuditLogListResponse(BaseModel):
    items: list[SystemAuditLogResponse]
    total: int
