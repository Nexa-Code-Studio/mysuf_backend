from datetime import datetime
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.subsidies.models import SubsidyOwnerType, SubsidyPolicy, SubsidyQuota
from app.modules.vehicles.models import VehicleOwnership, VehicleQuotaMode, VehicleUsageType


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


async def seed_subsidy_quotas(
    session: AsyncSession,
    month: int | None = None,
    year: int | None = None,
) -> dict[str, object]:
    current_time = datetime.utcnow()
    target_month = month or current_time.month
    target_year = year or current_time.year

    await seed_subsidy_policies(session)

    ownerships = list(
        (
            await session.execute(
                select(VehicleOwnership).order_by(VehicleOwnership.created_at, VehicleOwnership.id)
            )
        ).scalars().all()
    )
    summary = {
        "created": 0,
        "existing": 0,
        "processed": 0,
        "month": target_month,
        "year": target_year,
        "usage_types": {usage_type.value: 0 for usage_type in VehicleUsageType},
    }

    policies = {
        policy.usage_type: policy
        for policy in (
            await session.execute(select(SubsidyPolicy))
        ).scalars().all()
    }

    for ownership in ownerships:
        owner_type, owner_id = _resolve_quota_owner_for_seed(ownership)
        existing_quota = await session.scalar(
            select(SubsidyQuota.id).where(
                SubsidyQuota.owner_type == owner_type,
                SubsidyQuota.owner_id == owner_id,
                SubsidyQuota.month == target_month,
                SubsidyQuota.year == target_year,
            )
        )
        policy = policies.get(ownership.usage_type)
        if policy is None:
            raise ValueError(f"Missing subsidy policy for usage type {ownership.usage_type.value}")

        if existing_quota is None:
            session.add(
                SubsidyQuota(
                    owner_type=owner_type,
                    owner_id=owner_id,
                    subsidy_policy_id=policy.id,
                    month=target_month,
                    year=target_year,
                    quota_liters=policy.monthly_quota_liters,
                    used_liters=0,
                    is_active=True,
                )
            )
            summary["created"] += 1
        else:
            summary["existing"] += 1

        summary["processed"] += 1
        summary["usage_types"][ownership.usage_type.value] += 1

    await session.commit()
    return summary


def _resolve_quota_owner_for_seed(ownership: VehicleOwnership) -> tuple[SubsidyOwnerType, object]:
    if ownership.quota_mode == VehicleQuotaMode.OWNER_PERSONAL_QUOTA:
        return SubsidyOwnerType.BUYER_PROFILE, ownership.owner_id
    return SubsidyOwnerType.VEHICLE, ownership.vehicle_id
