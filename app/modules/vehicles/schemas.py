from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

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

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


class BuyerVehicleSubmissionResponse(BaseModel):
    submission_type: str
    message: str
    ownership: VehicleOwnershipResponse | None = None
    request: VehicleOwnershipRequestStatusResponse | None = None


class BuyerVehicleListItemResponse(BaseModel):
    ownership_id: UUID
    vehicle_id: UUID
    plate_number: str
    type_label: str
    category: str
    is_active: bool
    usage_type: VehicleUsageType
    quota_liters: float | None = None
    used_liters: float | None = None
    remaining_liters: float | None = None


class BuyerVehicleListResponse(BaseModel):
    items: List[BuyerVehicleListItemResponse]


class CashierBuyerByNfcBuyerResponse(BaseModel):
    buyer_profile_id: UUID
    user_id: UUID
    name: str
    nik_snapshot: str
    verification_status: str
    risk_score: float
    is_pin_active: bool = False


class CashierBuyerByNfcVehicleResponse(BaseModel):
    ownership_id: UUID
    vehicle_id: UUID
    plate_number: str
    registration_number: str | None = None
    type_label: str
    category: str
    ownership_status: VehicleOwnershipStatus
    usage_type: VehicleUsageType
    brand: str | None = None
    vehicle_type: str | None = None
    color: str | None = None
    manufacture_year: int | None = None
    is_eligible: Optional[bool] = None
    quota_liters: Optional[float] = None
    used_liters: Optional[float] = None
    remaining_liters: Optional[float] = None


class CashierBuyerByNfcResponse(BaseModel):
    buyer: CashierBuyerByNfcBuyerResponse
    vehicles: List[CashierBuyerByNfcVehicleResponse]


class BuyerVehicleDetailResponse(BaseModel):
    ownership_id: UUID
    vehicle_id: UUID
    plate_number: str
    status_label: str
    category: str
    registration_number: str
    brand: str
    vehicle_type: str
    manufacture_year: int
    color: str
    engine_capacity_cc: int
    pkb: str
    njkb: str
    owner_name: str | None = None
    owner_nik: str | None = None
    ownership_status: VehicleOwnershipStatus
    usage_type: VehicleUsageType
    quota_mode: VehicleQuotaMode
    quota_liters: float | None = None
    used_liters: float | None = None
    remaining_liters: float | None = None
    holders_in_family: List["BuyerFamilyVehicleHolderResponse"]
    documents: List[VehicleOwnershipDocumentResponse]


class BuyerPendingVehicleRequestItemResponse(BaseModel):
    request_id: UUID
    plate_number: str
    registration_number: str
    usage_type: VehicleUsageType
    status: VehicleOwnershipRequestStatus
    submitted_at: datetime
    review_note: str | None = None


class BuyerPendingVehicleRequestListResponse(BaseModel):
    items: List[BuyerPendingVehicleRequestItemResponse]


class BuyerPendingVehicleRequestDetailResponse(BaseModel):
    request_id: UUID
    vehicle_id: UUID
    plate_number: str
    registration_number: str
    brand: str
    vehicle_type: str
    manufacture_year: int
    color: str
    engine_capacity_cc: int
    pkb: str
    njkb: str
    owner_name: str | None = None
    owner_nik: str | None = None
    ownership_status: VehicleOwnershipStatus
    usage_type: VehicleUsageType
    quota_mode: VehicleQuotaMode
    status: VehicleOwnershipRequestStatus
    review_note: str | None = None
    submitted_at: datetime
    reviewed_at: datetime | None = None
    documents: List[VehicleOwnershipDocumentResponse]


class PublicVehicleOwnershipRequestAccept(BaseModel):
    review_note: str | None = None


class PublicVehicleOwnershipRequestAcceptResponse(BaseModel):
    request_id: UUID
    status: VehicleOwnershipRequestStatus
    approved_vehicle_ownership_id: UUID
    message: str


class BuyerFamilyMemberResponse(BaseModel):
    name: str
    role: str
    nik_masked: str
    is_registered_buyer: bool
    is_verified: bool


class BuyerFamilyVehicleHolderResponse(BaseModel):
    buyer_profile_id: UUID
    name: str
    nik_masked: str


class BuyerFamilyVehicleResponse(BaseModel):
    ownership_id: UUID
    vehicle_id: UUID
    plate_number: str
    type_label: str
    usage_type: VehicleUsageType
    category: str
    holders: List[BuyerFamilyVehicleHolderResponse]


class BuyerFamilyOverviewResponse(BaseModel):
    members: List[BuyerFamilyMemberResponse]
    vehicles: List[BuyerFamilyVehicleResponse]
