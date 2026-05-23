from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel

from app.modules.vehicles.models import VehicleUsageType


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class SubsidyPolicyUpdate(BaseModel):
    name: Optional[str] = None
    monthly_quota_liters: Optional[Decimal] = None
    max_allowed_njkb: Optional[Decimal] = None


class SubsidyPolicyResponse(BaseModel):
    id: UUID
    name: str
    usage_type: VehicleUsageType
    monthly_quota_liters: Decimal
    max_allowed_njkb: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SubsidyPolicyListResponse(BaseModel):
    items: List[SubsidyPolicyResponse]
    pagination: PaginationMeta
