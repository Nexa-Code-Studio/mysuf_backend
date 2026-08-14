from datetime import datetime
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.subsidies.models import SubsidyOwnerType, SubsidyPolicy, SubsidyQuota, SubsidySetting, KKSubsidyEligibility
from app.modules.vehicles.models import VehicleUsageType


DEFAULT_SUBSIDY_POLICY_SEED_DATA = [
    {
        "name": "Quota Personal",
        "usage_type": VehicleUsageType.PERSONAL,
        "monthly_quota_liters": Decimal("250.00"),
        "max_allowed_njkb": Decimal("250000000.00"),
        "is_active": True,
    },
    {
        "name": "Quota Commercial Motorcycle",
        "usage_type": VehicleUsageType.COMMERCIAL_MOTORCYCLE,
        "monthly_quota_liters": Decimal("100.00"),
        "max_allowed_njkb": Decimal("50000000.00"),
        "is_active": True,
    },
    {
        "name": "Quota Commercial Car",
        "usage_type": VehicleUsageType.COMMERCIAL_CAR,
        "monthly_quota_liters": Decimal("250.00"),
        "max_allowed_njkb": Decimal("250000000.00"),
        "is_active": True,
    },
    {
        "name": "Quota Commercial Truck",
        "usage_type": VehicleUsageType.COMMERCIAL_TRUCK,
        "monthly_quota_liters": Decimal("500.00"),
        "max_allowed_njkb": Decimal("500000000.00"),
        "is_active": True,
    },
]


async def seed_subsidy_policies(
    session: AsyncSession,
    seed_data: Sequence[dict] | None = None,
) -> dict[str, int]:
    dataset = seed_data or DEFAULT_SUBSIDY_POLICY_SEED_DATA
    summary = {"created": 0, "updated": 0, "active": 0}

    for item in dataset:
        created_now = False
        result = await session.execute(
            select(SubsidyPolicy).filter(
                SubsidyPolicy.usage_type == item["usage_type"],
            )
        )
        policy = result.scalars().first()

        if policy is None:
            policy = SubsidyPolicy(
                name=item["name"],
                usage_type=item["usage_type"],
                monthly_quota_liters=item["monthly_quota_liters"],
                max_allowed_njkb=item["max_allowed_njkb"],
            )
            session.add(policy)
            created_now = True
            summary["created"] += 1

        if policy.name != item["name"]:
            policy.name = item["name"]
            if not created_now:
                summary["updated"] += 1

        if policy.monthly_quota_liters != item["monthly_quota_liters"]:
            policy.monthly_quota_liters = item["monthly_quota_liters"]
            if not created_now:
                summary["updated"] += 1

        if policy.max_allowed_njkb != item["max_allowed_njkb"]:
            policy.max_allowed_njkb = item["max_allowed_njkb"]
            if not created_now:
                summary["updated"] += 1

        is_active = item.get("is_active", True)
        if policy.is_active != is_active:
            policy.is_active = is_active
            if not created_now:
                summary["updated"] += 1

    await session.commit()

    for item in dataset:
        active_policy_id = await session.scalar(
            select(SubsidyPolicy.id).where(
                SubsidyPolicy.usage_type == item["usage_type"],
                SubsidyPolicy.is_active.is_(True),
            )
        )
        if active_policy_id is not None:
            summary["active"] += 1

    return summary


async def seed_subsidy_settings(session: AsyncSession) -> None:
    result = await session.execute(select(SubsidySetting))
    setting = result.scalars().first()
    if setting is None:
        setting = SubsidySetting(
            income_threshold=Decimal("5000000.00"),
            default_quota_liters=Decimal("100.00"),
            occupation_bonuses={"OJOL": 50.0, "NELAYAN": 100.0, "UMKM": 50.0}
        )
        session.add(setting)
    else:
        setting.income_threshold = Decimal("5000000.00")
        setting.default_quota_liters = Decimal("100.00")
        setting.occupation_bonuses = {"OJOL": 50.0, "NELAYAN": 100.0, "UMKM": 50.0}
    await session.commit()


async def seed_subsidy_quotas(
    session: AsyncSession,
    month: int | None = None,
    year: int | None = None,
    buyer_profile_ids: list | None = None,
    vehicle_ownership_ids: list | None = None,
) -> dict[str, object]:
    current_time = datetime.utcnow()
    target_month = month or current_time.month
    target_year = year or current_time.year

    await seed_subsidy_policies(session)
    await seed_subsidy_settings(session)

    from app.modules.users.models import BuyerProfile
    from app.modules.subsidies.service import SubsidyService
    from app.modules.vehicles.models import VehicleOwnership, VehicleQuotaMode

    bp_query = select(BuyerProfile).order_by(BuyerProfile.timestamp, BuyerProfile.id)
    if buyer_profile_ids is not None:
        bp_query = bp_query.where(BuyerProfile.id.in_(buyer_profile_ids))
    buyer_profiles = list((await session.execute(bp_query)).scalars().all())

    summary: dict[str, object] = {
        "created": 0,
        "existing": 0,
        "processed": 0,
        "month": target_month,
        "year": target_year,
        "usage_types": {},
    }

    from app.modules.subsidies.models import EligibilityStatus
    from app.modules.vehicles.models import VehicleUsageType

    # Fetch the PERSONAL subsidy policy
    personal_policy = await session.scalar(
        select(SubsidyPolicy).where(
            SubsidyPolicy.usage_type == VehicleUsageType.PERSONAL
        )
    )

    subsidy_service = SubsidyService(session)

    # -------------------------------------------------------------------
    # Process PERSONAL quotas for each BuyerProfile
    # -------------------------------------------------------------------
    for profile in buyer_profiles:
        # Check if KKSubsidyEligibility already exists for this KK and the personal policy
        if personal_policy:
            existing_eligibility = await session.scalar(
                select(KKSubsidyEligibility.id).where(
                    KKSubsidyEligibility.kk_id == profile.kk_id,
                    KKSubsidyEligibility.subsidy_policy_id == personal_policy.id,
                )
            )
            if existing_eligibility is None:
                new_eligibility = KKSubsidyEligibility(
                    kk_id=profile.kk_id,
                    subsidy_policy_id=personal_policy.id,
                    total_njkb=Decimal("0.00"),
                    eligibility_status=EligibilityStatus.ELIGIBLE,
                    eligibility_reason="Seeded as eligible during master data setup.",
                    checked_at=datetime.utcnow()
                )
                session.add(new_eligibility)
                await session.flush()

        # Check if quota already exists for this period
        existing_quota = await session.scalar(
            select(SubsidyQuota.id).where(
                SubsidyQuota.owner_type == SubsidyOwnerType.BUYER_PROFILE,
                SubsidyQuota.owner_id == profile.id,
                SubsidyQuota.month == target_month,
                SubsidyQuota.year == target_year,
            )
        )

        await subsidy_service.get_or_sync_personal_quota(profile, target_month, target_year)

        if existing_quota is None:
            summary["created"] += 1
            usage_types = summary["usage_types"]
            usage_types["PERSONAL"] = usage_types.get("PERSONAL", 0) + 1
        else:
            summary["existing"] += 1

        summary["processed"] += 1

    # -------------------------------------------------------------------
    # Process VEHICLE-level quotas (OJOL, UMKM, Truck, etc.)
    # -------------------------------------------------------------------
    ded_query = select(VehicleOwnership).where(
        VehicleOwnership.quota_mode == VehicleQuotaMode.DEDICATED_VEHICLE_QUOTA
    )
    if vehicle_ownership_ids is not None:
        ded_query = ded_query.where(VehicleOwnership.id.in_(vehicle_ownership_ids))
    dedicated_ownerships = list((await session.execute(ded_query)).scalars().all())


    for ownership in dedicated_ownerships:
        # Find the policy for this usage type
        policy = await session.scalar(
            select(SubsidyPolicy).where(
                SubsidyPolicy.usage_type == ownership.usage_type,
                SubsidyPolicy.is_active.is_(True),
            )
        )
        if policy is None:
            continue

        existing_quota = await session.scalar(
            select(SubsidyQuota.id).where(
                SubsidyQuota.owner_type == SubsidyOwnerType.VEHICLE,
                SubsidyQuota.owner_id == ownership.vehicle_id,
                SubsidyQuota.month == target_month,
                SubsidyQuota.year == target_year,
            )
        )

        if existing_quota is None:
            new_quota = SubsidyQuota(
                owner_type=SubsidyOwnerType.VEHICLE,
                owner_id=ownership.vehicle_id,
                month=target_month,
                year=target_year,
                quota_liters=policy.monthly_quota_liters,
                used_liters=0,
                is_active=True,
            )
            session.add(new_quota)
            await session.flush()
            summary["created"] += 1
            usage_types = summary["usage_types"]
            usage_type_key = ownership.usage_type.value if hasattr(ownership.usage_type, "value") else str(ownership.usage_type)
            usage_types[usage_type_key] = usage_types.get(usage_type_key, 0) + 1
        else:
            summary["existing"] += 1

        summary["processed"] += 1

    await session.commit()
    return summary


