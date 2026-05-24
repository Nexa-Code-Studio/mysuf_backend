from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select

from app.core.database import AsyncSessionLocal
from app.modules.subsidies.models import KKSubsidyEligibility, SubsidyPolicy, SubsidyQuota
from app.modules.subsidies.seed_data import seed_subsidy_policies
from app.modules.vehicles.models import VehicleUsageType


TEST_SUBSIDY_POLICY_SEED_DATA = [
    {
        "name": "Test Quota Personal",
        "usage_type": VehicleUsageType.PERSONAL,
        "monthly_quota_liters": Decimal("251.00"),
        "max_allowed_njkb": Decimal("987654321.00"),
        "is_active": True,
    },
    {
        "name": "Test Quota OJOL",
        "usage_type": VehicleUsageType.OJOL,
        "monthly_quota_liters": Decimal("252.00"),
        "max_allowed_njkb": Decimal("987654322.00"),
        "is_active": True,
    },
    {
        "name": "Test Quota UMKM",
        "usage_type": VehicleUsageType.UMKM,
        "monthly_quota_liters": Decimal("253.00"),
        "max_allowed_njkb": Decimal("987654323.00"),
        "is_active": True,
    },
    {
        "name": "Test Quota Company Operational",
        "usage_type": VehicleUsageType.COMPANY_OPERATIONAL,
        "monthly_quota_liters": Decimal("254.00"),
        "max_allowed_njkb": Decimal("987654324.00"),
        "is_active": True,
    },
]


@pytest.mark.anyio
async def test_seed_subsidy_policies_is_idempotent_and_keeps_one_matching_policy_per_usage_type():
    usage_types = [item["usage_type"] for item in TEST_SUBSIDY_POLICY_SEED_DATA]

    try:
        async with AsyncSessionLocal() as session:
            policy_ids = (
                await session.execute(
                    select(SubsidyPolicy.id).where(SubsidyPolicy.usage_type.in_(usage_types))
                )
            ).scalars().all()
            if policy_ids:
                await session.execute(
                    delete(SubsidyQuota).where(SubsidyQuota.subsidy_policy_id.in_(policy_ids))
                )
                await session.execute(
                    delete(KKSubsidyEligibility).where(KKSubsidyEligibility.subsidy_policy_id.in_(policy_ids))
                )
            await session.execute(delete(SubsidyPolicy).where(SubsidyPolicy.usage_type.in_(usage_types)))
            await session.commit()
            first_summary = await seed_subsidy_policies(session, TEST_SUBSIDY_POLICY_SEED_DATA)
            assert first_summary == {"created": 4, "updated": 0, "active": 4}

        async with AsyncSessionLocal() as session:
            second_summary = await seed_subsidy_policies(session, TEST_SUBSIDY_POLICY_SEED_DATA)
            assert second_summary == {"created": 0, "updated": 0, "active": 4}

        async with AsyncSessionLocal() as session:
            policy_count = await session.scalar(
                select(func.count()).select_from(SubsidyPolicy).where(
                    SubsidyPolicy.usage_type.in_(usage_types),
                )
            )
            active_count = await session.scalar(
                select(func.count()).select_from(SubsidyPolicy).where(
                    SubsidyPolicy.usage_type.in_(usage_types),
                    SubsidyPolicy.is_active.is_(True),
                )
            )

            assert policy_count == 4
            assert active_count == 4
    finally:
        async with AsyncSessionLocal() as session:
            policy_ids = (
                await session.execute(
                    select(SubsidyPolicy.id).where(SubsidyPolicy.usage_type.in_(usage_types))
                )
            ).scalars().all()
            if policy_ids:
                await session.execute(
                    delete(SubsidyQuota).where(SubsidyQuota.subsidy_policy_id.in_(policy_ids))
                )
                await session.execute(
                    delete(KKSubsidyEligibility).where(KKSubsidyEligibility.subsidy_policy_id.in_(policy_ids))
                )
            await session.execute(
                delete(SubsidyPolicy).where(
                    SubsidyPolicy.usage_type.in_(usage_types),
                )
            )
            await session.commit()
