from typing import List, Any
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api.deps import get_db
from app.modules.fuels.models import FuelType, SubsidyType
from app.modules.fuels.schemas import FuelTypeResponse

router = APIRouter()

@router.get("", response_model=List[FuelTypeResponse])
async def read_all_fuels(
    db: AsyncSession = Depends(get_db),
) -> Any:
    result = await db.execute(
        select(FuelType).order_by(FuelType.name.asc())
    )
    return result.scalars().all()

@router.get("/subsidized", response_model=List[FuelTypeResponse])
async def read_subsidized_fuels(
    db: AsyncSession = Depends(get_db),
) -> Any:
    result = await db.execute(
        select(FuelType)
        .filter(FuelType.subsidy_type == SubsidyType.SUBSIDIZED)
        .order_by(FuelType.name.asc())
    )
    return result.scalars().all()
