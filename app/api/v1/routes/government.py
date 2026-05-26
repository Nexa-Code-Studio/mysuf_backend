from typing import Any
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.modules.users.models import User, UserRole
from app.modules.transactions.service import TransactionService

router = APIRouter()


@router.get("/summary")
async def get_government_dashboard_summary(
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.GOV_ADMIN])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    service = TransactionService(db)
    return await service.get_government_dashboard_summary(current_user)


@router.get("/heatmap")
async def get_government_heatmap(
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.GOV_ADMIN])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    service = TransactionService(db)
    return await service.get_government_heatmap_data(current_user)

