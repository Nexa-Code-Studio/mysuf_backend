from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.modules.companies.models import Company
from app.modules.registries.models import KK
from app.modules.subsidies.models import SubsidyOwnerType, SubsidyQuota, KKSubsidyEligibility
from app.modules.subsidies.seed_data import seed_subsidy_quotas
from app.modules.users.models import BuyerProfile, User, UserRole, VerificationStatus
from app.modules.vehicles.models import (
    VehicleOwnerType,
    VehicleOwnership,
    VehicleOwnershipStatus,
    VehicleQuotaMode,
    VehicleUsageType,
)


@pytest.mark.anyio
async def test_seed_subsidy_quotas_creates_rows_for_all_usage_types_present():
    current_time = datetime.utcnow()
    target_month = current_time.month
    target_year = current_time.year

    kk = KK(code=f"KK-SEED-{uuid4().hex[:8]}")
    buyer_user = User(
        name="Seed Buyer",
        email=f"seed-buyer-{uuid4().hex[:8]}@example.com",
        password="secret",
        role=[UserRole.BUYER],
        is_active=True,
    )
    buyer_profile = BuyerProfile(
        nik_snapshot=f"3275{uuid4().hex[:12]}",
        ktp_nfc_id_snapshot=f"NFC-{uuid4().hex[:8]}",
        kk=kk,
        user=buyer_user,
        verification_status=VerificationStatus.VERIFIED,
    )
    company = Company(name=f"Seed Company {uuid4().hex[:8]}")

    personal_ownership = VehicleOwnership(
        owner_type=VehicleOwnerType.BUYER_PROFILE,
        owner_id=uuid4(),
        vehicle_id=uuid4(),
        ownership_status=VehicleOwnershipStatus.PERSONAL,
        usage_type=VehicleUsageType.PERSONAL,
        quota_mode=VehicleQuotaMode.OWNER_PERSONAL_QUOTA,
        plate_number_snapshot="B 3000 TST",
        ktp_nfc_id_snapshot=f"NFC-PER-{uuid4().hex[:8]}",
    )
    ojol_ownership = VehicleOwnership(
        owner_type=VehicleOwnerType.BUYER_PROFILE,
        owner_id=uuid4(),
        vehicle_id=uuid4(),
        ownership_status=VehicleOwnershipStatus.PERSONAL,
        usage_type=VehicleUsageType.COMMERCIAL_MOTORCYCLE,
        quota_mode=VehicleQuotaMode.DEDICATED_VEHICLE_QUOTA,
        plate_number_snapshot="B 3001 TST",
        ktp_nfc_id_snapshot=f"NFC-OJL-{uuid4().hex[:8]}",
    )
    umkm_ownership = VehicleOwnership(
        owner_type=VehicleOwnerType.BUYER_PROFILE,
        owner_id=uuid4(),
        vehicle_id=uuid4(),
        ownership_status=VehicleOwnershipStatus.PERSONAL,
        usage_type=VehicleUsageType.COMMERCIAL_CAR,
        quota_mode=VehicleQuotaMode.DEDICATED_VEHICLE_QUOTA,
        plate_number_snapshot="B 3002 TST",
        ktp_nfc_id_snapshot=f"NFC-UMK-{uuid4().hex[:8]}",
    )
    company_ownership = VehicleOwnership(
        owner_type=VehicleOwnerType.COMPANY,
        owner_id=uuid4(),
        vehicle_id=uuid4(),
        ownership_status=VehicleOwnershipStatus.COMPANY,
        usage_type=VehicleUsageType.COMMERCIAL_TRUCK,
        quota_mode=VehicleQuotaMode.DEDICATED_VEHICLE_QUOTA,
        plate_number_snapshot="B 3003 TST",
        ktp_nfc_id_snapshot=f"NFC-CMP-{uuid4().hex[:8]}",
    )

    ownership_ids: list = []
    quota_ids: list = []
    pre_existing_quota_ids: list = []
    try:
        async with AsyncSessionLocal() as session:
            # Capture pre-existing quotas for this month/year so we can restore them
            pre_existing_quota_ids = list(
                (await session.execute(
                    select(SubsidyQuota.id).where(
                        SubsidyQuota.month == target_month,
                        SubsidyQuota.year == target_year,
                    )
                )).scalars().all()
            )
            # Clear all quotas for the target period so seed starts fresh
            await session.execute(delete(SubsidyQuota).where(
                SubsidyQuota.month == target_month,
                SubsidyQuota.year == target_year,
            ))
            # Clear test vehicle ownerships (by known plate snapshots)
            await session.execute(delete(VehicleOwnership).where(VehicleOwnership.plate_number_snapshot.in_([
                "B 3000 TST", "B 3001 TST", "B 3002 TST", "B 3003 TST"
            ])))
            await session.commit()

            session.add_all([kk, buyer_user, buyer_profile, company])
            await session.commit()
            await session.refresh(buyer_profile)
            await session.refresh(company)

            personal_ownership.owner_id = buyer_profile.id
            ojol_ownership.owner_id = buyer_profile.id
            umkm_ownership.owner_id = buyer_profile.id
            company_ownership.owner_id = company.id
            session.add_all([personal_ownership, ojol_ownership, umkm_ownership, company_ownership])
            await session.commit()

            ownership_ids = [
                personal_ownership.id,
                ojol_ownership.id,
                umkm_ownership.id,
                company_ownership.id,
            ]

            summary = await seed_subsidy_quotas(
                session,
                month=target_month,
                year=target_year,
                buyer_profile_ids=[buyer_profile.id],
                vehicle_ownership_ids=[ojol_ownership.id, umkm_ownership.id, company_ownership.id],
            )
            assert summary["created"] == 4
            assert summary["existing"] == 0
            assert summary["processed"] == 4
            assert summary["usage_types"] == {
                "PERSONAL": 1,
                "COMMERCIAL_MOTORCYCLE": 1,
                "COMMERCIAL_CAR": 1,
                "COMMERCIAL_TRUCK": 1,
            }

        async with AsyncSessionLocal() as session:
            quotas = list(
                (
                    await session.execute(
                        select(SubsidyQuota).where(
                            SubsidyQuota.month == target_month,
                            SubsidyQuota.year == target_year,
                            SubsidyQuota.owner_id.in_(
                                [
                                    buyer_profile.id,
                                    ojol_ownership.vehicle_id,
                                    umkm_ownership.vehicle_id,
                                    company_ownership.vehicle_id,
                                ]
                            ),
                        )
                    )
                ).scalars().all()
            )
            quota_ids = [quota.id for quota in quotas]
            assert len(quotas) == 4
            assert any(
                quota.owner_type == SubsidyOwnerType.BUYER_PROFILE and quota.owner_id == buyer_profile.id
                for quota in quotas
            )
            assert any(
                quota.owner_type == SubsidyOwnerType.VEHICLE and quota.owner_id == ojol_ownership.vehicle_id
                for quota in quotas
            )
            assert any(
                quota.owner_type == SubsidyOwnerType.VEHICLE and quota.owner_id == umkm_ownership.vehicle_id
                for quota in quotas
            )
            assert any(
                quota.owner_type == SubsidyOwnerType.VEHICLE and quota.owner_id == company_ownership.vehicle_id
                for quota in quotas
            )

        async with AsyncSessionLocal() as session:
            second_summary = await seed_subsidy_quotas(
                session,
                month=target_month,
                year=target_year,
                buyer_profile_ids=[buyer_profile.id],
                vehicle_ownership_ids=[ojol_ownership.id, umkm_ownership.id, company_ownership.id],
            )
            assert second_summary["created"] == 0
            assert second_summary["existing"] == 4
            assert second_summary["processed"] == 4
    finally:
        async with AsyncSessionLocal() as session:
            if quota_ids:
                await session.execute(delete(SubsidyQuota).where(SubsidyQuota.id.in_(quota_ids)))
            await session.execute(delete(VehicleOwnership).where(VehicleOwnership.id.in_(ownership_ids)))
            await session.execute(delete(BuyerProfile).where(BuyerProfile.id == buyer_profile.id))
            await session.execute(delete(User).where(User.id == buyer_user.id))
            await session.execute(delete(Company).where(Company.id == company.id))
            # Delete kk_subsidy_eligibilities before kk (FK constraint)
            await session.execute(delete(KKSubsidyEligibility).where(KKSubsidyEligibility.kk_id == kk.id))
            await session.execute(delete(KK).where(KK.id == kk.id))
            # Restore pre-existing quotas that were cleared for this test's month/year
            # (they are left as-is since we cannot reconstruct them — the seeder will
            # re-create them on the next scheduled seed run)
            await session.commit()
