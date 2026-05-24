from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.modules.subsidies.schemas import (
    SubsidyPolicyListResponse,
    SubsidyPolicyResponse,
    SubsidyPolicyUpdate,
)
from app.modules.subsidies.service import SubsidyService


router = APIRouter()


@router.get("/policies", response_model=SubsidyPolicyListResponse)
async def read_subsidy_policies(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = SubsidyService(db)
    return await service.get_subsidy_policies(page=page, page_size=page_size)


@router.get("/policies/{policy_id}", response_model=SubsidyPolicyResponse)
async def read_subsidy_policy(
    policy_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = SubsidyService(db)
    return await service.get_subsidy_policy(policy_id)


@router.put("/policies/{policy_id}", response_model=SubsidyPolicyResponse)
async def update_subsidy_policy(
    policy_id: str,
    policy_in: SubsidyPolicyUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = SubsidyService(db)
    return await service.update_subsidy_policy(policy_id, policy_in)
