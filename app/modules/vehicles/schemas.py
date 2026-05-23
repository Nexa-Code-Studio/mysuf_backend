from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel

from app.modules.vehicles.models import (
    VehicleOwnershipDocumentType,
    VehicleOwnershipRequestStatus,
    VehicleOwnerType,
    VehicleOwnershipStatus,
    VehicleQuotaMode,
    VehicleUsageType,
)


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class VehicleOwnershipUpdate(BaseModel):
    ownership_status: Optional[VehicleOwnershipStatus] = None
    usage_type: Optional[VehicleUsageType] = None
    quota_mode: Optional[VehicleQuotaMode] = None
    plate_number_snapshot: Optional[str] = None
    ktp_nfc_id_snapshot: Optional[str] = None
    assigned_user_id: Optional[UUID] = None


class VehicleOwnershipDocumentResponse(BaseModel):
    id: UUID
    document_type: VehicleOwnershipDocumentType
    storage_key: str
    original_filename: str | None = None
    mime_type: str | None = None
    file_size_bytes: int | None = None
    checksum_sha256: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VehicleOwnershipResponse(BaseModel):
    id: UUID
    owner_type: VehicleOwnerType
    owner_id: UUID
    vehicle_id: UUID
    ownership_status: VehicleOwnershipStatus
    usage_type: VehicleUsageType
    quota_mode: VehicleQuotaMode
    plate_number_snapshot: str
    ktp_nfc_id_snapshot: str
    assigned_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    documents: List[VehicleOwnershipDocumentResponse]

    class Config:
        from_attributes = True


class VehicleOwnershipListResponse(BaseModel):
    items: List[VehicleOwnershipResponse]
    pagination: PaginationMeta


class VehicleOwnershipRequestStatusResponse(BaseModel):
    id: UUID
    status: VehicleOwnershipRequestStatus
    review_note: str | None = None
    approved_vehicle_ownership_id: UUID | None = None
    submitted_at: datetime
    reviewed_at: datetime | None = None

    class Config:
        from_attributes = True


class BuyerVehicleSubmissionResponse(BaseModel):
    submission_type: str
    message: str
    ownership: VehicleOwnershipResponse | None = None
    request: VehicleOwnershipRequestStatusResponse | None = None
