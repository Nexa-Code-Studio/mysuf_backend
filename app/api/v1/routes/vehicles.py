from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.modules.users.models import User, UserRole
from app.modules.vehicles.models import (
    VehicleOwnerType,
    VehicleOwnershipStatus,
    VehicleQuotaMode,
    VehicleUsageType,
)
from app.modules.vehicles.schemas import (
    BuyerVehicleSubmissionResponse,
    BuyerVehicleDetailResponse,
    BuyerVehicleListResponse,
    BuyerPendingVehicleRequestDetailResponse,
    BuyerPendingVehicleRequestListResponse,
    PublicVehicleOwnershipRequestAccept,
    PublicVehicleOwnershipRequestAcceptResponse,
    VehicleOwnershipListResponse,
    VehicleOwnershipResponse,
    VehicleOwnershipRequestStatusResponse,
    VehicleOwnershipUpdate,
)
from app.modules.vehicles.service import VehicleService


router = APIRouter()


@router.post("/submissions", response_model=BuyerVehicleSubmissionResponse, status_code=status.HTTP_201_CREATED)
async def submit_buyer_vehicle(
    registration_number: str = Form(...),
    usage_type: VehicleUsageType = Form(...),
    stnk_photo: UploadFile = File(...),
    vehicle_photo: UploadFile = File(...),
    productive_business_proof: UploadFile | None = File(None),
    current_user: User = Depends(require_roles([UserRole.BUYER])),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = VehicleService(db)
    return await service.submit_buyer_vehicle(
        current_user=current_user,
        registration_number=registration_number,
        usage_type=usage_type,
        stnk_photo=stnk_photo,
        vehicle_photo=vehicle_photo,
        productive_business_proof=productive_business_proof,
    )


@router.get("/me", response_model=BuyerVehicleListResponse)
async def read_current_buyer_vehicles(
    current_user: User = Depends(require_roles([UserRole.BUYER])),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = VehicleService(db)
    return await service.get_buyer_vehicle_ownerships(current_user=current_user)


@router.get("/submissions/me", response_model=BuyerPendingVehicleRequestListResponse)
async def read_current_buyer_vehicle_submissions(
    current_user: User = Depends(require_roles([UserRole.BUYER])),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = VehicleService(db)
    return await service.get_buyer_pending_vehicle_requests(current_user=current_user)


@router.get("/submissions/{request_id}", response_model=VehicleOwnershipRequestStatusResponse)
async def read_buyer_vehicle_submission(
    request_id: str,
    current_user: User = Depends(require_roles([UserRole.BUYER])),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = VehicleService(db)
    return await service.get_vehicle_ownership_request_for_buyer(current_user=current_user, request_id=request_id)


@router.get("/submissions/{request_id}/detail", response_model=BuyerPendingVehicleRequestDetailResponse)
async def read_buyer_vehicle_submission_detail(
    request_id: str,
    current_user: User = Depends(require_roles([UserRole.BUYER])),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = VehicleService(db)
    return await service.get_buyer_pending_vehicle_request_detail(
        current_user=current_user,
        request_id=request_id,
    )


@router.post(
    "/submissions/{request_id}/accept",
    response_model=PublicVehicleOwnershipRequestAcceptResponse,
)
async def approve_vehicle_ownership_request_public(
    request_id: str,
    payload: PublicVehicleOwnershipRequestAccept | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Temporary PUBLIC approval endpoint for docs/domain testing only.
    SECURITY NOTE: This must be protected by admin auth/authorization before production use.
    """
    service = VehicleService(db)
    return await service.approve_vehicle_ownership_request_public(
        request_id=request_id,
        review_note=payload.review_note if payload else None,
    )


@router.get("/submissions/{request_id}/documents/{document_id}")
async def read_buyer_vehicle_submission_document(
    request_id: str,
    document_id: str,
    current_user: User = Depends(require_roles([UserRole.BUYER])),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = VehicleService(db)
    return await service.stream_vehicle_ownership_request_document(
        current_user=current_user,
        request_id=request_id,
        document_id=document_id,
    )


@router.get("/{ownership_id}/detail", response_model=BuyerVehicleDetailResponse)
async def read_current_buyer_vehicle_detail(
    ownership_id: str,
    current_user: User = Depends(require_roles([UserRole.BUYER])),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = VehicleService(db)
    return await service.get_buyer_vehicle_ownership_detail(current_user=current_user, ownership_id=ownership_id)


@router.get("/{ownership_id}/documents/{document_id}")
async def read_current_buyer_vehicle_document(
    ownership_id: str,
    document_id: str,
    current_user: User = Depends(require_roles([UserRole.BUYER])),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = VehicleService(db)
    return await service.stream_vehicle_ownership_document(
        current_user=current_user,
        ownership_id=ownership_id,
        document_id=document_id,
    )


@router.post("/", response_model=VehicleOwnershipResponse, status_code=status.HTTP_201_CREATED)
async def create_vehicle_ownership(
    owner_type: VehicleOwnerType = Form(...),
    owner_id: str = Form(...),
    vehicle_id: str = Form(...),
    ownership_status: VehicleOwnershipStatus = Form(...),
    usage_type: VehicleUsageType = Form(...),
    quota_mode: VehicleQuotaMode = Form(...),
    plate_number_snapshot: str = Form(...),
    ktp_nfc_id_snapshot: str = Form(...),
    stnk_photo: UploadFile = File(...),
    vehicle_photo: UploadFile = File(...),
    productive_business_proof: UploadFile | None = File(None),
    assigned_user_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = VehicleService(db)
    return await service.create_vehicle_ownership(
        owner_type=owner_type,
        owner_id=owner_id,
        vehicle_id=vehicle_id,
        ownership_status=ownership_status,
        usage_type=usage_type,
        quota_mode=quota_mode,
        plate_number_snapshot=plate_number_snapshot,
        ktp_nfc_id_snapshot=ktp_nfc_id_snapshot,
        stnk_photo=stnk_photo,
        vehicle_photo=vehicle_photo,
        productive_business_proof=productive_business_proof,
        assigned_user_id=assigned_user_id,
    )


@router.get("/", response_model=VehicleOwnershipListResponse)
async def read_vehicle_ownerships(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = VehicleService(db)
    return await service.get_vehicle_ownerships(page=page, page_size=page_size)


@router.get("/{ownership_id}", response_model=VehicleOwnershipResponse)
async def read_vehicle_ownership(
    ownership_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = VehicleService(db)
    return await service.get_vehicle_ownership(ownership_id)


@router.put("/{ownership_id}", response_model=VehicleOwnershipResponse)
async def update_vehicle_ownership(
    ownership_id: str,
    ownership_in: VehicleOwnershipUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = VehicleService(db)
    return await service.update_vehicle_ownership(ownership_id, ownership_in)
