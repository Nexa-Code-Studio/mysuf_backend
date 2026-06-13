from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from app.modules.spbu_activities.models import SpbuActivityCategory

class SpbuActivityLogBase(BaseModel):
    category: SpbuActivityCategory
    detail: str

class SpbuActivityLogCreate(SpbuActivityLogBase):
    gas_station_id: UUID
    user_id: UUID | None = None

class SpbuActivityLogResponse(SpbuActivityLogBase):
    id: UUID
    gas_station_id: UUID
    user_id: UUID | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class SpbuActivityLogListResponse(BaseModel):
    items: list[SpbuActivityLogResponse]
    total: int
