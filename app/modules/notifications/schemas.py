from datetime import datetime
from typing import List, Optional, Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict

class NotificationResponse(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    body: str
    is_read: bool
    data: Optional[Any] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class NotificationListResponse(BaseModel):
    items: List[NotificationResponse]
    total: int
