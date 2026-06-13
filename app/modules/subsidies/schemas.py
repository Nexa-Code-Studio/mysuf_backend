from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

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

    model_config = ConfigDict(from_attributes=True)


class SubsidyPolicyListResponse(BaseModel):
    items: List[SubsidyPolicyResponse]
    pagination: PaginationMeta


# Government Role Schemas

class KKEligibilityItem(BaseModel):
    id: UUID
    kk_id: UUID
    code: str
    vehicle_count: int
    total_njkb: Decimal
    threshold: Decimal
    eligible: str


class KKEligibilityListResponse(BaseModel):
    items: List[KKEligibilityItem]
    total: int
    page: int
    size: int
    eligible_count: int
    ineligible_count: int
    threshold: Decimal


class ThresholdUpdateRequest(BaseModel):
    threshold: Decimal


class GovernmentQuotaPoliciesResponse(BaseModel):
    warga: Decimal
    motor_komersial: Decimal
    mobil_komersial: Decimal
    truk_komersial: Decimal


class GovernmentQuotaPoliciesUpdate(BaseModel):
    warga: Decimal
    motor_komersial: Decimal
    mobil_komersial: Decimal
    truk_komersial: Decimal


class GovernmentQuotaTransactionItem(BaseModel):
    nikSensor: str
    nama: str
    baseQuota1: str
    baseQuota2: str
    baseQuota3: str
    riskIndex: int
    modifier: str
    finalQuota: str


class GovernmentQuotaTransactionResponse(BaseModel):
    items: List[GovernmentQuotaTransactionItem]
    total: int


class BlacklistItem(BaseModel):
    id: UUID
    accountId: str
    holderName: str
    plate: str
    type: str
    reason: str
    dateAdded: str
    officer: str
    status: str


class BlacklistListResponse(BaseModel):
    items: List[BlacklistItem]
    total: int


class BlacklistCreateRequest(BaseModel):
    accountId: str
    holderName: str
    plate: str
    type: str
    status: str
    reason: str

