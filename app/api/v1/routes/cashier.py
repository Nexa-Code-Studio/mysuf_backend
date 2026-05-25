from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.modules.transactions.schemas import CashierPerformanceResponse, CashierRecentScanListResponse, CashierTransactionListResponse
from app.modules.transactions.service import TransactionService
from app.modules.users.models import User, UserRole


router = APIRouter()


@router.get("/transactions", response_model=CashierTransactionListResponse)
async def read_cashier_transactions(
    q: str | None = Query(None, description="Search by buyer, NIK, plate, fuel, payment method, status, or transaction id"),
    date_from: datetime | None = Query(None, description="Start datetime in ISO UTC"),
    date_to: datetime | None = Query(None, description="End datetime in ISO UTC"),
    cursor: str | None = Query(None, description="Cursor from previous page"),
    limit: int = Query(20, ge=1, le=100),
    include_summary: bool = Query(True),
    current_user: User = Depends(require_roles([UserRole.SALES_OFFICER])),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = TransactionService(db)
    return await service.get_cashier_transaction_history(
        current_user,
        q=q,
        date_from=date_from,
        date_to=date_to,
        cursor=cursor,
        limit=limit,
        include_summary=include_summary,
    )


@router.get("/recent-scans", response_model=CashierRecentScanListResponse)
async def read_cashier_recent_scans(
    date_from: datetime | None = Query(None, description="Start datetime in ISO UTC"),
    date_to: datetime | None = Query(None, description="End datetime in ISO UTC"),
    cursor: str | None = Query(None, description="Cursor from previous page"),
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(require_roles([UserRole.SALES_OFFICER])),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = TransactionService(db)
    return await service.get_cashier_recent_scans(
        current_user,
        date_from=date_from,
        date_to=date_to,
        cursor=cursor,
        limit=limit,
    )


@router.get("/performance", response_model=CashierPerformanceResponse)
async def read_cashier_performance(
    date_from: datetime | None = Query(None, description="Start datetime in ISO UTC"),
    date_to: datetime | None = Query(None, description="End datetime in ISO UTC"),
    recent_limit: int = Query(5, ge=1, le=20),
    current_user: User = Depends(require_roles([UserRole.SALES_OFFICER])),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = TransactionService(db)
    return await service.get_cashier_performance(
        current_user,
        date_from=date_from,
        date_to=date_to,
        recent_limit=recent_limit,
    )
