from typing import Any
from uuid import UUID
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.modules.users.models import User, UserRole
from app.modules.transactions.schemas import FraudLogListResponse, FraudLogResponse, FraudLogStatusUpdateRequest
from app.modules.transactions.service import TransactionService

router = APIRouter()


@router.get("", response_model=FraudLogListResponse)
async def read_fraud_logs(
    gas_station_id: UUID | None = Query(None, description="Filter by gas station ID"),
    risk_level: str | None = Query(None, description="Filter by risk level (SAFE, SUSPICIOUS, HIGH_RISK, CRITICAL)"),
    status: str | None = Query(None, description="Filter by workflow status (PENDING, FLAGGED, RESOLVED)"),
    search: str | None = Query(None, description="Search term for case ID, plate, NIK, or buyer name"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.GOV_ADMIN, UserRole.SPBU_ADMIN, UserRole.SALES_OFFICER])),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = TransactionService(db)
    return await service.get_fraud_logs(
        current_user,
        gas_station_id=gas_station_id,
        risk_level=risk_level,
        status_filter=status,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.patch("/{log_id}/status", response_model=FraudLogResponse)
async def update_fraud_log_status(
    log_id: UUID,
    payload: FraudLogStatusUpdateRequest,
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.GOV_ADMIN, UserRole.SPBU_ADMIN])),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = TransactionService(db)
    return await service.update_fraud_log_status(
        current_user,
        log_id=log_id,
        status_value=payload.status,
        resolution_notes=payload.resolution_notes,
    )
