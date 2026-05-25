from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.subsidies.models import KKSubsidyEligibility, SubsidyPolicy, SubsidyQuota, SubsidyOwnerType
from app.modules.vehicles.models import VehicleUsageType


class SubsidyRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_subsidy_policy_by_id(self, policy_id: str | UUID) -> SubsidyPolicy | None:
        result = await self.db.execute(select(SubsidyPolicy).filter(SubsidyPolicy.id == policy_id))
        return result.scalars().first()

    async def get_subsidy_policy_by_usage_type(self, usage_type: VehicleUsageType) -> SubsidyPolicy | None:
        result = await self.db.execute(
            select(SubsidyPolicy).filter(SubsidyPolicy.usage_type == usage_type)
        )
        return result.scalars().first()

    async def get_subsidy_policies(self, skip: int = 0, limit: int = 100) -> list[SubsidyPolicy]:
        result = await self.db.execute(
            select(SubsidyPolicy).order_by(SubsidyPolicy.usage_type).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def count_subsidy_policies(self) -> int:
        result = await self.db.execute(select(func.count()).select_from(SubsidyPolicy))
        return result.scalar() or 0

    async def update_subsidy_policy(self, policy: SubsidyPolicy) -> SubsidyPolicy:
        await self.db.commit()
        await self.db.refresh(policy)
        return policy

    async def get_subsidy_quota(
        self,
        owner_type: SubsidyOwnerType,
        owner_id: UUID,
        month: int,
        year: int,
    ) -> SubsidyQuota | None:
        result = await self.db.execute(
            select(SubsidyQuota).filter(
                SubsidyQuota.owner_type == owner_type,
                SubsidyQuota.owner_id == owner_id,
                SubsidyQuota.month == month,
                SubsidyQuota.year == year,
            )
        )
        return result.scalars().first()

    async def get_latest_kk_subsidy_eligibility(
        self,
        kk_id: str | UUID,
        subsidy_policy_id: str | UUID,
    ) -> KKSubsidyEligibility | None:
        result = await self.db.execute(
            select(KKSubsidyEligibility)
            .filter(
                KKSubsidyEligibility.kk_id == kk_id,
                KKSubsidyEligibility.subsidy_policy_id == subsidy_policy_id,
            )
            .order_by(
                KKSubsidyEligibility.checked_at.desc().nullslast(),
                KKSubsidyEligibility.updated_at.desc(),
                KKSubsidyEligibility.id.desc(),
            )
            .limit(1)
        )
        return result.scalars().first()

    async def create_subsidy_quota(self, quota: SubsidyQuota) -> SubsidyQuota:
        self.db.add(quota)
        await self.db.commit()
        await self.db.refresh(quota)
        return quota

    async def update_subsidy_quota(self, quota: SubsidyQuota) -> SubsidyQuota:
        await self.db.commit()
        await self.db.refresh(quota)
        return quota
