from typing import List
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.registries.models import CitizenRegistryMockup, VehicleRegistryMockup
from app.modules.subsidies.models import KKSubsidyEligibility, SubsidyOwnerType, SubsidyPolicy, SubsidyQuota
from app.modules.users.models import BuyerProfile, User
from app.modules.vehicles.models import (
    VehicleOwnerType,
    VehicleOwnership,
    VehicleOwnershipDocument,
    VehicleOwnershipRequest,
    VehicleOwnershipRequestDocument,
)


class VehicleRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_vehicle_ownership_by_id(self, ownership_id: str | UUID) -> VehicleOwnership | None:
        result = await self.db.execute(
            select(VehicleOwnership)
            .options(selectinload(VehicleOwnership.documents))
            .filter(VehicleOwnership.id == ownership_id)
        )
        return result.scalars().first()

    async def get_vehicle_ownerships(self, skip: int = 0, limit: int = 100) -> List[VehicleOwnership]:
        result = await self.db.execute(
            select(VehicleOwnership)
            .options(selectinload(VehicleOwnership.documents))
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_vehicle_ownerships(self) -> int:
        result = await self.db.execute(select(func.count()).select_from(VehicleOwnership))
        return result.scalar() or 0

    async def update_vehicle_ownership(self, ownership: VehicleOwnership) -> VehicleOwnership:
        await self.db.commit()
        await self.db.refresh(ownership)
        return ownership

    async def create_vehicle_ownership(self, ownership: VehicleOwnership) -> VehicleOwnership:
        self.db.add(ownership)
        await self.db.flush()
        return ownership

    async def add_documents(self, documents: list[VehicleOwnershipDocument]) -> None:
        self.db.add_all(documents)

    async def commit(self) -> None:
        await self.db.commit()

    async def rollback(self) -> None:
        await self.db.rollback()

    async def refresh_vehicle_ownership(self, ownership: VehicleOwnership) -> VehicleOwnership:
        await self.db.refresh(ownership)
        return ownership

    async def get_vehicle_registry_by_registration(self, registration_number: str) -> VehicleRegistryMockup | None:
        result = await self.db.execute(
            select(VehicleRegistryMockup).filter(
                VehicleRegistryMockup.registration_number == registration_number
            )
        )
        return result.scalars().first()

    async def get_buyer_profile_by_user_id(self, user_id: str | UUID) -> BuyerProfile | None:
        result = await self.db.execute(
            select(BuyerProfile).filter(BuyerProfile.user_id == user_id)
        )
        return result.scalars().first()

    async def get_buyer_profile_by_id(self, buyer_profile_id: str | UUID) -> BuyerProfile | None:
        result = await self.db.execute(
            select(BuyerProfile).filter(BuyerProfile.id == buyer_profile_id)
        )
        return result.scalars().first()

    async def get_buyer_profile_by_ktp_nfc_id_snapshot(
        self,
        ktp_nfc_id_snapshot: str,
    ) -> BuyerProfile | None:
        result = await self.db.execute(
            select(BuyerProfile)
            .options(selectinload(BuyerProfile.user))
            .filter(BuyerProfile.ktp_nfc_id_snapshot == ktp_nfc_id_snapshot)
            .order_by(BuyerProfile.timestamp.desc(), BuyerProfile.id.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def create_vehicle_ownership_request(
        self,
        request: VehicleOwnershipRequest,
    ) -> VehicleOwnershipRequest:
        self.db.add(request)
        await self.db.flush()
        return request

    async def add_request_documents(self, documents: list[VehicleOwnershipRequestDocument]) -> None:
        self.db.add_all(documents)

    async def get_vehicle_ownership_request_by_id(
        self,
        request_id: str | UUID,
    ) -> VehicleOwnershipRequest | None:
        result = await self.db.execute(
            select(VehicleOwnershipRequest)
            .options(selectinload(VehicleOwnershipRequest.documents))
            .filter(VehicleOwnershipRequest.id == request_id)
        )
        return result.scalars().first()

    async def get_vehicle_ownerships_by_ktp_nfc_id_snapshot(
        self,
        ktp_nfc_id_snapshot: str,
    ) -> List[VehicleOwnership]:
        result = await self.db.execute(
            select(VehicleOwnership)
            .options(selectinload(VehicleOwnership.documents))
            .filter(VehicleOwnership.ktp_nfc_id_snapshot == ktp_nfc_id_snapshot)
            .order_by(VehicleOwnership.created_at.desc(), VehicleOwnership.id.desc())
        )
        return list(result.scalars().all())

    async def get_vehicle_registry_by_id(self, vehicle_id: str | UUID) -> VehicleRegistryMockup | None:
        result = await self.db.execute(
            select(VehicleRegistryMockup).filter(VehicleRegistryMockup.id == vehicle_id)
        )
        return result.scalars().first()

    async def get_vehicle_ownership_document_by_id(
        self,
        document_id: str | UUID,
    ) -> VehicleOwnershipDocument | None:
        result = await self.db.execute(
            select(VehicleOwnershipDocument).filter(VehicleOwnershipDocument.id == document_id)
        )
        return result.scalars().first()

    async def get_vehicle_ownership_request_document_by_id(
        self,
        document_id: str | UUID,
    ) -> VehicleOwnershipRequestDocument | None:
        result = await self.db.execute(
            select(VehicleOwnershipRequestDocument).filter(
                VehicleOwnershipRequestDocument.id == document_id
            )
        )
        return result.scalars().first()

    async def get_citizens_by_kk_id(self, kk_id: str | UUID) -> list[CitizenRegistryMockup]:
        result = await self.db.execute(
            select(CitizenRegistryMockup)
            .filter(CitizenRegistryMockup.kk_id == kk_id)
            .order_by(CitizenRegistryMockup.nama.asc())
        )
        return list(result.scalars().all())

    async def get_buyer_profiles_by_kk_id(self, kk_id: str | UUID) -> list[BuyerProfile]:
        result = await self.db.execute(
            select(BuyerProfile)
            .options(selectinload(BuyerProfile.user))
            .filter(BuyerProfile.kk_id == kk_id)
        )
        return list(result.scalars().all())

    async def get_vehicle_ownerships_by_owner_ids(self, owner_ids: list[UUID]) -> list[VehicleOwnership]:
        if not owner_ids:
            return []
        result = await self.db.execute(
            select(VehicleOwnership)
            .options(selectinload(VehicleOwnership.documents))
            .filter(
                VehicleOwnership.owner_type == VehicleOwnerType.BUYER_PROFILE,
                VehicleOwnership.owner_id.in_(owner_ids),
            )
            .order_by(VehicleOwnership.created_at.desc(), VehicleOwnership.id.desc())
        )
        return list(result.scalars().all())

    async def get_vehicle_ownership_requests_by_buyer_profile_id(
        self,
        buyer_profile_id: str | UUID,
    ) -> list[VehicleOwnershipRequest]:
        result = await self.db.execute(
            select(VehicleOwnershipRequest)
            .options(selectinload(VehicleOwnershipRequest.documents))
            .filter(VehicleOwnershipRequest.buyer_profile_id == buyer_profile_id)
            .order_by(VehicleOwnershipRequest.submitted_at.desc(), VehicleOwnershipRequest.id.desc())
        )
        return list(result.scalars().all())

    async def get_subsidy_quota_by_owner(
        self,
        owner_type: SubsidyOwnerType,
        owner_id: str | UUID,
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

    async def get_subsidy_policy_by_usage_type(self, usage_type) -> SubsidyPolicy | None:
        result = await self.db.execute(
            select(SubsidyPolicy).filter(SubsidyPolicy.usage_type == usage_type)
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

    async def create_kk_subsidy_eligibility(
        self,
        eligibility: KKSubsidyEligibility,
    ) -> KKSubsidyEligibility:
        self.db.add(eligibility)
        await self.db.flush()
        return eligibility

    async def get_all_vehicle_ownership_requests(self) -> List[VehicleOwnershipRequest]:
        result = await self.db.execute(
            select(VehicleOwnershipRequest)
            .options(
                selectinload(VehicleOwnershipRequest.documents),
                selectinload(VehicleOwnershipRequest.buyer_profile).selectinload(BuyerProfile.user),
                selectinload(VehicleOwnershipRequest.company),
            )
            .order_by(VehicleOwnershipRequest.submitted_at.desc(), VehicleOwnershipRequest.id.desc())
        )
        return list(result.scalars().all())
