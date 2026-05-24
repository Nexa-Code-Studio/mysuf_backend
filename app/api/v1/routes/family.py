from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.modules.users.models import User, UserRole
from app.modules.vehicles.schemas import BuyerFamilyOverviewResponse
from app.modules.vehicles.service import VehicleService


router = APIRouter()


@router.get("/me", response_model=BuyerFamilyOverviewResponse)
async def read_current_buyer_family_overview(
    current_user: User = Depends(require_roles([UserRole.BUYER])),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = VehicleService(db)
    return await service.get_buyer_family_overview(current_user=current_user)
