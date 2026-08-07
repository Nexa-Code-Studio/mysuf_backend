from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.subsidies.models import SubsidyOwnerType, SubsidyPolicy, SubsidyQuota
from app.modules.subsidies.repository import SubsidyRepository
from app.modules.subsidies.schemas import SubsidyPolicyUpdate
from app.modules.users.models import BuyerProfile
from app.modules.vehicles.models import (
    VehicleOwnerType,
    VehicleOwnership,
    VehicleQuotaMode,
    VehicleUsageType,
)


class SubsidyService:
    def __init__(self, db: AsyncSession):
        self.repo = SubsidyRepository(db)

    async def get_subsidy_policies(self, page: int = 1, page_size: int = 20) -> dict:
        skip = (page - 1) * page_size
        limit = page_size

        items = await self.repo.get_subsidy_policies(skip=skip, limit=limit)
        total = await self.repo.count_subsidy_policies()
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0

        return {
            "items": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
            },
        }

    async def get_subsidy_policy(self, policy_id: str) -> SubsidyPolicy:
        policy = await self.repo.get_subsidy_policy_by_id(policy_id)
        if not policy:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subsidy policy not found")
        return policy

    async def update_subsidy_policy(self, policy_id: str, policy_in: SubsidyPolicyUpdate) -> SubsidyPolicy:
        policy = await self.get_subsidy_policy(policy_id)

        update_data = policy_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(policy, field, value)

        return await self.repo.update_subsidy_policy(policy)

    async def get_or_create_subsidy_quota(
        self,
        vehicle_ownership: VehicleOwnership,
        month: int,
        year: int,
        kk_subsidy_eligibility_id=None,
    ) -> SubsidyQuota:
        owner_type, owner_id = self._resolve_quota_owner(vehicle_ownership)
        policy = await self.repo.get_subsidy_policy_by_usage_type(vehicle_ownership.usage_type)
        if not policy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Subsidy policy for usage type {vehicle_ownership.usage_type.value} not found",
            )

        quota = await self.repo.get_subsidy_quota(owner_type, owner_id, month, year)
        if quota:
            if quota.subsidy_policy_id is None:
                quota.subsidy_policy_id = policy.id
                quota = await self.repo.update_subsidy_quota(quota)
            return quota

        quota = SubsidyQuota(
            owner_type=owner_type,
            owner_id=owner_id,
            subsidy_policy_id=policy.id,
            kk_subsidy_eligibility_id=kk_subsidy_eligibility_id,
            month=month,
            year=year,
            quota_liters=policy.monthly_quota_liters,
            used_liters=0,
            is_active=True,
        )
        return await self.repo.create_subsidy_quota(quota)

    async def get_or_sync_personal_quota(self, buyer_profile: BuyerProfile, month: int | None = None, year: int | None = None) -> SubsidyQuota:
        current_time = datetime.utcnow()
        target_month = month or current_time.month
        target_year = year or current_time.year

        # 1. Look up the citizen in the mockup registry
        from app.modules.registries.models import CitizenRegistryMockup
        from sqlalchemy import select
        
        stmt = select(CitizenRegistryMockup).filter(CitizenRegistryMockup.nik == buyer_profile.nik_snapshot)
        citizen = (await self.repo.db.execute(stmt)).scalars().first()
        
        # 2. Fetch the subsidy setting
        from app.modules.subsidies.models import SubsidySetting
        setting_stmt = select(SubsidySetting)
        setting = (await self.repo.db.execute(setting_stmt)).scalars().first()
        
        # Set default values if setting not found (fallback)
        income_threshold = Decimal("5000000.00")
        default_quota = Decimal("100.00")
        bonuses = {"OJOL": Decimal("50.00"), "NELAYAN": Decimal("100.00"), "UMKM": Decimal("50.00")}
        
        if setting:
            income_threshold = Decimal(setting.income_threshold)
            default_quota = Decimal(setting.default_quota_liters)
            bonuses = {k: Decimal(str(v)) for k, v in setting.occupation_bonuses.items()}
            
        # 3. Calculate base quota based on income and job
        is_eligible = False
        base_quota = Decimal("0.00")
        reason = ""
        
        if citizen:
            income = Decimal(citizen.penghasilan or 0)
            job = citizen.pekerjaan or "LAINNYA"
            if income <= income_threshold:
                is_eligible = True
                bonus = bonuses.get(job, Decimal("0.00"))
                base_quota = default_quota + bonus
                reason = f"Penghasilan Rp {income:,.2f} di bawah batas Rp {income_threshold:,.2f}. Pekerjaan: {job} (Tambahan: {bonus}L)."
            else:
                reason = f"Penghasilan Rp {income:,.2f} di atas batas Rp {income_threshold:,.2f}."
        else:
            reason = "Data kependudukan tidak ditemukan."
            
        # 4. Apply risk score trust factor
        computed_quota = self._compute_personal_quota_liters(
            monthly_quota_liters=base_quota,
            risk_score=Decimal(buyer_profile.risk_score),
        )
        
        # 5. Fetch or create SubsidyQuota record in the database
        quota = await self.repo.get_subsidy_quota(
            SubsidyOwnerType.BUYER_PROFILE,
            buyer_profile.id,
            target_month,
            target_year,
        )
        if quota:
            if Decimal(quota.quota_liters) != computed_quota:
                quota.quota_liters = computed_quota
                quota = await self.repo.update_subsidy_quota(quota)
            return quota

        quota = SubsidyQuota(
            owner_type=SubsidyOwnerType.BUYER_PROFILE,
            owner_id=buyer_profile.id,
            month=target_month,
            year=target_year,
            quota_liters=computed_quota,
            used_liters=0,
            is_active=is_eligible,
        )
        return await self.repo.create_subsidy_quota(quota)

    def _compute_personal_quota_liters(self, monthly_quota_liters: Decimal, risk_score: Decimal) -> Decimal:
        trust_factor = Decimal("1") - (risk_score / Decimal("100"))
        if trust_factor < Decimal("0"):
            trust_factor = Decimal("0")
        return (monthly_quota_liters * trust_factor).quantize(Decimal("0.01"))

    def _resolve_quota_owner(self, vehicle_ownership: VehicleOwnership) -> tuple[SubsidyOwnerType, object]:
        if vehicle_ownership.quota_mode == VehicleQuotaMode.OWNER_PERSONAL_QUOTA:
            if vehicle_ownership.owner_type != VehicleOwnerType.BUYER_PROFILE:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Company-owned vehicles cannot use owner personal quota.",
                )
            return SubsidyOwnerType.BUYER_PROFILE, vehicle_ownership.owner_id

        return SubsidyOwnerType.VEHICLE, vehicle_ownership.vehicle_id
