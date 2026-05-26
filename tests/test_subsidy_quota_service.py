from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.core.database import AsyncSessionLocal
from app.modules.registries.models import KK
from app.modules.subsidies.models import SubsidyOwnerType, SubsidyPolicy, SubsidyQuota
from app.modules.subsidies.seed_data import seed_subsidy_policies
from app.modules.subsidies.service import SubsidyService
from app.modules.users.models import BuyerProfile, User, UserRole, VerificationStatus
from app.modules.vehicles.models import (
    VehicleOwnerType,
    VehicleOwnership,
    VehicleOwnershipStatus,
    VehicleQuotaMode,
    VehicleUsageType,
)


@pytest.mark.anyio
async def test_get_or_create_subsidy_quota_uses_correct_owner_bucket():
    kk = KK(code=f"KK-QUOTA-{uuid4().hex[:8]}")
    user = User(
        name="Quota Buyer",
        email=f"quota-{uuid4().hex[:8]}@example.com",
        password="secret",
        role=[UserRole.BUYER],
        is_active=True,
    )
    buyer_profile = BuyerProfile(
        nik_snapshot=f"3275{uuid4().hex[:12]}",
        ktp_nfc_id_snapshot=f"NFC-{uuid4().hex[:8]}",
        kk=kk,
        user=user,
        verification_status=VerificationStatus.VERIFIED,
    )
    personal_vehicle_id = uuid4()
    ojol_vehicle_id = uuid4()
    personal_ownership = VehicleOwnership(
        owner_type=VehicleOwnerType.BUYER_PROFILE,
        owner_id=buyer_profile.id,
        vehicle_id=personal_vehicle_id,
        ownership_status=VehicleOwnershipStatus.PERSONAL,
        usage_type=VehicleUsageType.PERSONAL,
        quota_mode=VehicleQuotaMode.OWNER_PERSONAL_QUOTA,
        plate_number_snapshot="B 1000 TST",
        ktp_nfc_id_snapshot=f"NFC-PER-{uuid4().hex[:8]}",
    )
    ojol_ownership = VehicleOwnership(
        owner_type=VehicleOwnerType.BUYER_PROFILE,
        owner_id=buyer_profile.id,
        vehicle_id=ojol_vehicle_id,
        ownership_status=VehicleOwnershipStatus.PERSONAL,
        usage_type=VehicleUsageType.COMMERCIAL_MOTORCYCLE,
        quota_mode=VehicleQuotaMode.DEDICATED_VEHICLE_QUOTA,
        plate_number_snapshot="B 2000 TST",
        ktp_nfc_id_snapshot=f"NFC-OJL-{uuid4().hex[:8]}",
    )

    try:
        async with AsyncSessionLocal() as session:
            await seed_subsidy_policies(session)

        async with AsyncSessionLocal() as session:
            session.add_all([kk, user, buyer_profile])
            await session.commit()
            await session.refresh(buyer_profile)

            personal_ownership.owner_id = buyer_profile.id
            ojol_ownership.owner_id = buyer_profile.id
            session.add_all([personal_ownership, ojol_ownership])
            await session.commit()
            await session.refresh(personal_ownership)
            await session.refresh(ojol_ownership)

            service = SubsidyService(session)
            personal_quota = await service.get_or_create_subsidy_quota(personal_ownership, month=6, year=2026)
            same_personal_quota = await service.get_or_create_subsidy_quota(personal_ownership, month=6, year=2026)
            ojol_quota = await service.get_or_create_subsidy_quota(ojol_ownership, month=6, year=2026)
            same_ojol_quota = await service.get_or_create_subsidy_quota(ojol_ownership, month=6, year=2026)

            assert personal_quota.id == same_personal_quota.id
            assert personal_quota.owner_type == SubsidyOwnerType.BUYER_PROFILE
            assert personal_quota.owner_id == buyer_profile.id
            assert Decimal(personal_quota.quota_liters) == Decimal("250.00")

            assert ojol_quota.id == same_ojol_quota.id
            assert ojol_quota.owner_type == SubsidyOwnerType.VEHICLE
            assert ojol_quota.owner_id == ojol_vehicle_id
            assert Decimal(ojol_quota.quota_liters) == Decimal("100.00")

            personal_policy = await session.scalar(
                select(SubsidyPolicy).where(SubsidyPolicy.usage_type == VehicleUsageType.PERSONAL)
            )
            ojol_policy = await session.scalar(
                select(SubsidyPolicy).where(SubsidyPolicy.usage_type == VehicleUsageType.COMMERCIAL_MOTORCYCLE)
            )
            quota_count = await session.scalar(
                select(func.count()).select_from(SubsidyQuota).where(
                    SubsidyQuota.id.in_([personal_quota.id, ojol_quota.id])
                )
            )

            assert personal_policy is not None
            assert ojol_policy is not None
            assert personal_quota.subsidy_policy_id == personal_policy.id
            assert ojol_quota.subsidy_policy_id == ojol_policy.id
            assert quota_count == 2
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(SubsidyQuota).where(SubsidyQuota.owner_id.in_([buyer_profile.id, ojol_vehicle_id])))
            await session.execute(delete(VehicleOwnership).where(VehicleOwnership.id.in_([personal_ownership.id, ojol_ownership.id])))
            await session.execute(delete(BuyerProfile).where(BuyerProfile.id == buyer_profile.id))
            await session.execute(delete(User).where(User.id == user.id))
            await session.execute(delete(KK).where(KK.id == kk.id))
            await session.commit()
