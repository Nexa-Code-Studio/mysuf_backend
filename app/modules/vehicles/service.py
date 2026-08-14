import hashlib
import mimetypes
import shutil
from datetime import datetime
from typing import Any, Dict, Optional
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import io
from fastapi import HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.storage import StorageService

from app.modules.registries.models import CitizenRegistryMockup
from app.modules.subsidies.models import EligibilityStatus, KKSubsidyEligibility, SubsidyOwnerType
from app.modules.users.models import User, VerificationStatus
from app.modules.transactions.models import CashierScanMethod, CashierScanResult
from app.modules.transactions.service import TransactionService
from app.modules.vehicles.models import (
    VehicleOwnership,
    VehicleOwnershipDocument,
    VehicleOwnershipDocumentType,
    VehicleOwnershipRequest,
    VehicleOwnershipRequestDocument,
    VehicleOwnershipRequestStatus,
    VehicleOwnerType,
    VehicleOwnershipStatus,
    VehicleQuotaMode,
    VehicleUsageType,
)
from app.modules.vehicles.repository import VehicleRepository
from app.modules.vehicles.schemas import VehicleOwnershipUpdate


class VehicleService:
    STORAGE_ROOT = Path(__file__).resolve().parents[3] / "storage" / "vehicle-ownerships"
    REQUEST_STORAGE_ROOT = Path(__file__).resolve().parents[3] / "storage" / "vehicle-ownership-requests"
    MAX_FILE_NAME_LENGTH = 255
    MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = VehicleRepository(db)
        self.storage = StorageService()
        self.transaction_service = TransactionService(db)

    async def get_vehicle_ownerships(self, page: int = 1, page_size: int = 20) -> dict:
        skip = (page - 1) * page_size
        limit = page_size

        items = await self.repo.get_vehicle_ownerships(skip=skip, limit=limit)
        total = await self.repo.count_vehicle_ownerships()
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

    async def get_vehicle_ownership(self, ownership_id: str) -> VehicleOwnership:
        ownership = await self.repo.get_vehicle_ownership_by_id(ownership_id)
        if not ownership:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle ownership not found")
        return ownership

    async def get_vehicle_ownership_request_for_buyer(
        self,
        current_user: User,
        request_id: str,
    ) -> VehicleOwnershipRequest:
        request = await self.repo.get_vehicle_ownership_request_by_id(request_id)
        if not request:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle ownership request not found")

        buyer_profile = await self.repo.get_buyer_profile_by_user_id(current_user.id)
        if not buyer_profile or request.buyer_profile_id != buyer_profile.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle ownership request not found")
        return request

    async def get_buyer_vehicle_ownerships(self, current_user: User) -> dict:
        buyer_profile = await self.repo.get_buyer_profile_by_user_id(current_user.id)
        if not buyer_profile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Buyer profile not found for current user.",
            )

        ownerships = await self.repo.get_vehicle_ownerships_by_ktp_nfc_id_snapshot(
            buyer_profile.ktp_nfc_id_snapshot
        )
        current_time = self._utcnow()
        items = []
        for ownership in ownerships:
            registry_vehicle = await self.repo.get_vehicle_registry_by_id(ownership.vehicle_id)
            type_label = ownership.plate_number_snapshot
            if registry_vehicle is not None:
                type_label = f"{registry_vehicle.brand} - {registry_vehicle.vehicle_type}"
            quota_summary = await self._build_vehicle_quota_summary(
                ownership=ownership,
                buyer_profile=buyer_profile,
                month=current_time.month,
                year=current_time.year,
            )
            items.append(
                {
                    "ownership_id": ownership.id,
                    "vehicle_id": ownership.vehicle_id,
                    "plate_number": ownership.plate_number_snapshot,
                    "type_label": type_label,
                    "category": self._to_vehicle_category(ownership.usage_type),
                    "is_active": True,
                    "usage_type": ownership.usage_type,
                    "quota_liters": quota_summary["quota_liters"],
                    "used_liters": quota_summary["used_liters"],
                    "remaining_liters": quota_summary["remaining_liters"],
                }
            )

        return {"items": items}

    async def validate_cross_nfc_uniqueness(self, nfc_id: str, exclude_ownership_id: UUID | None = None) -> None:
        from sqlalchemy import select
        from app.modules.registries.models import CitizenRegistryMockup, VehicleRegistryMockup
        from app.modules.vehicles.models import VehicleOwnership
        from app.modules.users.models import BuyerProfile

        # 1. Cek apakah NFC ID sudah dipakai di CitizenRegistryMockup (KTP warga)
        res_citizen = await self.db.execute(
            select(CitizenRegistryMockup).filter(CitizenRegistryMockup.ktp_nfc_id == nfc_id)
        )
        if res_citizen.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Kode NFC '{nfc_id}' sudah terdaftar sebagai KTP warga di sistem Kependudukan.",
            )

        # 2. Cek apakah NFC ID sudah dipakai di BuyerProfile
        res_buyer = await self.db.execute(
            select(BuyerProfile).filter(BuyerProfile.ktp_nfc_id_snapshot == nfc_id)
        )
        if res_buyer.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Kode NFC '{nfc_id}' sudah terdaftar sebagai KTP warga aktif.",
            )

        # 3. Cek apakah NFC ID sudah dipakai di VehicleRegistryMockup (NFC kendaraan)
        res_veh_registry = await self.db.execute(
            select(VehicleRegistryMockup).filter(VehicleRegistryMockup.vehicle_nfc_id == nfc_id)
        )
        if res_veh_registry.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Kode NFC '{nfc_id}' sudah terdaftar sebagai NFC kendaraan di database Kepolisian.",
            )

        # 4. Cek apakah NFC ID sudah dipakai di VehicleOwnership
        stmt_ownership = select(VehicleOwnership).filter(VehicleOwnership.vehicle_nfc_id == nfc_id)
        if exclude_ownership_id:
            stmt_ownership = stmt_ownership.filter(VehicleOwnership.id != exclude_ownership_id)
        res_ownership = await self.db.execute(stmt_ownership)
        if res_ownership.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Kode NFC '{nfc_id}' sudah terdaftar pada kendaraan lain.",
            )

    async def get_cashier_buyer_by_nfc(self, current_user: User, nfc_id: str) -> dict:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from app.modules.vehicles.models import VehicleOwnership
        from app.modules.users.models import BuyerProfile
        from app.modules.subsidies.service import SubsidyService

        buyer_profile = await self.repo.get_buyer_profile_by_ktp_nfc_id_snapshot(nfc_id)
        lookup_method = CashierScanMethod.NFC
        current_time = self._utcnow()

        if not buyer_profile:
            # Fallback to search by NIK snapshot
            stmt = select(BuyerProfile).options(selectinload(BuyerProfile.user)).filter(BuyerProfile.nik_snapshot == nfc_id)
            res = await self.db.execute(stmt)
            buyer_profile = res.scalars().first()
            if buyer_profile:
                lookup_method = CashierScanMethod.NIK

        # If still not found, check if it's a Commercial Vehicle NFC card
        if not buyer_profile:
            stmt_veh = select(VehicleOwnership).filter(VehicleOwnership.vehicle_nfc_id == nfc_id)
            res_veh = await self.db.execute(stmt_veh)
            ownership = res_veh.scalars().first()
            if ownership:
                if not ownership.assigned_user_id:
                    await self.transaction_service.log_cashier_scan_event(
                        cashier_user=current_user,
                        lookup_method=lookup_method,
                        lookup_value=nfc_id,
                        result=CashierScanResult.FAILED,
                        error_message="Kendaraan komersial ini belum ditugaskan ke pengemudi mana pun.",
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Kendaraan komersial ini belum ditugaskan ke pengemudi mana pun.",
                    )

                # Get the assigned driver's profile with eager load user
                stmt_bp = select(BuyerProfile).options(selectinload(BuyerProfile.user)).filter(BuyerProfile.user_id == ownership.assigned_user_id)
                res_bp = await self.db.execute(stmt_bp)
                buyer_profile = res_bp.scalars().first()
                if not buyer_profile or buyer_profile.user is None:
                    await self.transaction_service.log_cashier_scan_event(
                        cashier_user=current_user,
                        lookup_method=lookup_method,
                        lookup_value=nfc_id,
                        result=CashierScanResult.FAILED,
                        error_message="Profil pengemudi yang ditugaskan tidak ditemukan.",
                    )
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Profil pengemudi yang ditugaskan tidak ditemukan.",
                    )

                # Build commercial vehicle details
                registry_vehicle = await self.repo.get_vehicle_registry_by_id(ownership.vehicle_id)
                type_label = ownership.plate_number_snapshot
                if registry_vehicle is not None:
                    type_label = f"{registry_vehicle.brand} - {registry_vehicle.vehicle_type}"

                _user_obj = buyer_profile.user
                _is_blocked = getattr(_user_obj, "is_blocked", False) if _user_obj else False
                _frozen_until = getattr(_user_obj, "frozen_until", None) if _user_obj else None
                from datetime import datetime as _dt
                _is_frozen = bool(_frozen_until and _frozen_until > _dt.utcnow())

                quota_summary = await self._build_vehicle_quota_summary(
                    ownership=ownership,
                    buyer_profile=buyer_profile,
                    month=current_time.month,
                    year=current_time.year,
                )
                is_eligible = quota_summary["quota_liters"] is not None and not _is_blocked and not _is_frozen
 
                vehicles = [
                    {
                        "ownership_id": ownership.id,
                        "vehicle_id": ownership.vehicle_id,
                        "plate_number": ownership.plate_number_snapshot,
                        "registration_number": (
                            registry_vehicle.registration_number if registry_vehicle is not None else None
                        ),
                        "type_label": type_label,
                        "category": self._to_vehicle_category(ownership.usage_type),
                        "ownership_status": ownership.ownership_status,
                        "usage_type": ownership.usage_type,
                        "brand": registry_vehicle.brand if registry_vehicle is not None else None,
                        "vehicle_type": (
                            registry_vehicle.vehicle_type if registry_vehicle is not None else None
                        ),
                        "color": registry_vehicle.color if registry_vehicle is not None else None,
                        "manufacture_year": (
                            registry_vehicle.manufacture_year if registry_vehicle is not None else None
                        ),
                        "is_eligible": is_eligible,
                        "quota_liters": quota_summary["quota_liters"],
                        "used_liters": quota_summary["used_liters"],
                        "remaining_liters": quota_summary["remaining_liters"],
                    }
                ]
 
                # Get driver's personal quota
                subsidy_service = SubsidyService(self.db)
                personal_quota = await subsidy_service.get_or_sync_personal_quota(
                    buyer_profile=buyer_profile,
                    month=current_time.month,
                    year=current_time.year,
                )
                quota_liters = float(Decimal(personal_quota.quota_liters)) if personal_quota else 0.0
                used_liters = float(Decimal(personal_quota.used_liters)) if personal_quota else 0.0
                remaining_liters = max(quota_liters - used_liters, 0.0)
                is_eligible_driver = (personal_quota.is_active if personal_quota else False) and not _is_blocked and not _is_frozen

                account_status_commercial = self._compute_account_status(
                    is_blocked=_is_blocked,
                    is_frozen=_is_frozen,
                    is_quota_active=personal_quota.is_active if personal_quota else False,
                    remaining_liters=remaining_liters,
                )

                response = {
                    "buyer": {
                        "buyer_profile_id": buyer_profile.id,
                        "user_id": buyer_profile.user_id,
                        "name": buyer_profile.user.name,
                        "nik_snapshot": buyer_profile.nik_snapshot,
                        "verification_status": buyer_profile.verification_status.value,
                        "risk_score": float(Decimal(buyer_profile.risk_score)),
                        "is_pin_active": buyer_profile.is_pin_active,
                        "is_blocked": _is_blocked,
                        "is_frozen": _is_frozen,
                        "frozen_until": _frozen_until.isoformat() if _frozen_until else None,
                        "quota_liters": quota_liters,
                        "used_liters": used_liters,
                        "remaining_liters": remaining_liters,
                        "is_eligible": is_eligible_driver,
                        "account_status": account_status_commercial,
                    },
                    "vehicles": vehicles,
                }

                await self.transaction_service.log_cashier_scan_event(
                    cashier_user=current_user,
                    lookup_method=lookup_method,
                    lookup_value=nfc_id,
                    result=CashierScanResult.SUCCESS,
                    buyer_profile=buyer_profile,
                )
                return response

        if not buyer_profile or buyer_profile.user is None:
            await self.transaction_service.log_cashier_scan_event(
                cashier_user=current_user,
                lookup_method=lookup_method,
                lookup_value=nfc_id,
                result=CashierScanResult.FAILED,
                error_message="Buyer profile or Vehicle not found for the provided NFC ID or NIK.",
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Buyer profile or Vehicle not found for the provided NFC ID or NIK.",
            )

        _user_obj2 = buyer_profile.user
        _is_blocked2 = getattr(_user_obj2, "is_blocked", False) if _user_obj2 else False
        _frozen_until2 = getattr(_user_obj2, "frozen_until", None) if _user_obj2 else None
        from datetime import datetime as _dt2
        _is_frozen2 = bool(_frozen_until2 and _frozen_until2 > _dt2.utcnow())

        ownerships = await self.repo.get_vehicle_ownerships_by_ktp_nfc_id_snapshot(
            buyer_profile.ktp_nfc_id_snapshot
        )
        vehicles = []
        current_time = self._utcnow()
        for ownership in ownerships:
            registry_vehicle = await self.repo.get_vehicle_registry_by_id(ownership.vehicle_id)
            type_label = ownership.plate_number_snapshot
            if registry_vehicle is not None:
                type_label = f"{registry_vehicle.brand} - {registry_vehicle.vehicle_type}"

            quota_summary = await self._build_vehicle_quota_summary(
                ownership=ownership,
                buyer_profile=buyer_profile,
                month=current_time.month,
                year=current_time.year,
            )
            is_eligible = quota_summary["quota_liters"] is not None and not _is_blocked2 and not _is_frozen2

            vehicles.append(
                {
                    "ownership_id": ownership.id,
                    "vehicle_id": ownership.vehicle_id,
                    "plate_number": ownership.plate_number_snapshot,
                    "registration_number": (
                        registry_vehicle.registration_number if registry_vehicle is not None else None
                    ),
                    "type_label": type_label,
                    "category": self._to_vehicle_category(ownership.usage_type),
                    "ownership_status": ownership.ownership_status,
                    "usage_type": ownership.usage_type,
                    "brand": registry_vehicle.brand if registry_vehicle is not None else None,
                    "vehicle_type": (
                        registry_vehicle.vehicle_type if registry_vehicle is not None else None
                    ),
                    "color": registry_vehicle.color if registry_vehicle is not None else None,
                    "manufacture_year": (
                        registry_vehicle.manufacture_year if registry_vehicle is not None else None
                    ),
                    "is_eligible": is_eligible,
                    "quota_liters": quota_summary["quota_liters"],
                    "used_liters": quota_summary["used_liters"],
                    "remaining_liters": quota_summary["remaining_liters"],
                }
            )

        from app.modules.subsidies.service import SubsidyService
        subsidy_service = SubsidyService(self.db)
        personal_quota = await subsidy_service.get_or_sync_personal_quota(
            buyer_profile=buyer_profile,
            month=current_time.month,
            year=current_time.year,
        )
        quota_liters = float(Decimal(personal_quota.quota_liters)) if personal_quota else 0.0
        used_liters = float(Decimal(personal_quota.used_liters)) if personal_quota else 0.0
        remaining_liters = max(quota_liters - used_liters, 0.0)
        is_eligible = (personal_quota.is_active if personal_quota else False) and not _is_blocked2 and not _is_frozen2

        account_status_personal = self._compute_account_status(
            is_blocked=_is_blocked2,
            is_frozen=_is_frozen2,
            is_quota_active=personal_quota.is_active if personal_quota else False,
            remaining_liters=remaining_liters,
        )

        response = {
            "buyer": {
                "buyer_profile_id": buyer_profile.id,
                "user_id": buyer_profile.user_id,
                "name": buyer_profile.user.name,
                "nik_snapshot": buyer_profile.nik_snapshot,
                "verification_status": buyer_profile.verification_status.value,
                "risk_score": float(Decimal(buyer_profile.risk_score)),
                "is_pin_active": buyer_profile.is_pin_active,
                "is_blocked": _is_blocked2,
                "is_frozen": _is_frozen2,
                "frozen_until": _frozen_until2.isoformat() if _frozen_until2 else None,
                "quota_liters": quota_liters,
                "used_liters": used_liters,
                "remaining_liters": remaining_liters,
                "is_eligible": is_eligible,
                "account_status": account_status_personal,
            },
            "vehicles": vehicles,
        }

        await self.transaction_service.log_cashier_scan_event(
            cashier_user=current_user,
            lookup_method=lookup_method,
            lookup_value=nfc_id,
            result=CashierScanResult.SUCCESS,
            buyer_profile=buyer_profile,
        )
        return response

    async def get_buyer_vehicle_ownership_detail(
        self,
        current_user: User,
        ownership_id: str,
    ) -> dict:
        buyer_profile = await self.repo.get_buyer_profile_by_user_id(current_user.id)
        if not buyer_profile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Buyer profile not found for current user.",
            )

        ownership = await self.get_vehicle_ownership(ownership_id)
        if ownership.ktp_nfc_id_snapshot != buyer_profile.ktp_nfc_id_snapshot:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle ownership not found")

        registry_vehicle = await self.repo.get_vehicle_registry_by_id(ownership.vehicle_id)
        if not registry_vehicle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle registry detail not found for this ownership.",
            )
        current_time = self._utcnow()
        quota_summary = await self._build_vehicle_quota_summary(
            ownership=ownership,
            buyer_profile=buyer_profile,
            month=current_time.month,
            year=current_time.year,
        )

        return {
            "ownership_id": ownership.id,
            "vehicle_id": ownership.vehicle_id,
            "plate_number": ownership.plate_number_snapshot,
            "status_label": "Aktif",
            "category": self._to_vehicle_category(ownership.usage_type),
            "registration_number": registry_vehicle.registration_number,
            "brand": registry_vehicle.brand,
            "vehicle_type": registry_vehicle.vehicle_type,
            "manufacture_year": registry_vehicle.manufacture_year,
            "color": registry_vehicle.color,
            "engine_capacity_cc": registry_vehicle.engine_capacity_cc,
            "pkb": str(registry_vehicle.pkb),
            "njkb": str(registry_vehicle.njkb),
            "owner_name": registry_vehicle.owner_name,
            "owner_nik": registry_vehicle.owner_nik,
            "ownership_status": ownership.ownership_status,
            "usage_type": ownership.usage_type,
            "quota_mode": ownership.quota_mode,
            "quota_liters": quota_summary["quota_liters"],
            "used_liters": quota_summary["used_liters"],
            "remaining_liters": quota_summary["remaining_liters"],
            "holders_in_family": await self._build_family_holders_for_vehicle(
                buyer_profile_kk_id=buyer_profile.kk_id,
                vehicle_id=ownership.vehicle_id,
            ),
            "documents": ownership.documents,
        }

    async def get_buyer_pending_vehicle_requests(self, current_user: User) -> dict:
        buyer_profile = await self.repo.get_buyer_profile_by_user_id(current_user.id)
        if not buyer_profile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Buyer profile not found for current user.",
            )

        requests = await self.repo.get_vehicle_ownership_requests_by_buyer_profile_id(buyer_profile.id)
        items = []
        for request in requests:
            registry_vehicle = await self.repo.get_vehicle_registry_by_id(request.vehicle_id)
            items.append(
                {
                    "request_id": request.id,
                    "plate_number": request.plate_number_snapshot,
                    "registration_number": registry_vehicle.registration_number if registry_vehicle else "-",
                    "usage_type": request.usage_type,
                    "status": request.status,
                    "submitted_at": request.submitted_at,
                    "review_note": request.review_note,
                }
            )

        return {"items": items}

    async def get_buyer_pending_vehicle_request_detail(
        self,
        current_user: User,
        request_id: str,
    ) -> dict:
        request = await self.get_vehicle_ownership_request_for_buyer(
            current_user=current_user,
            request_id=request_id,
        )
        registry_vehicle = await self.repo.get_vehicle_registry_by_id(request.vehicle_id)
        if not registry_vehicle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle registry detail not found for this request.",
            )

        return {
            "request_id": request.id,
            "vehicle_id": request.vehicle_id,
            "plate_number": request.plate_number_snapshot,
            "registration_number": registry_vehicle.registration_number,
            "brand": registry_vehicle.brand,
            "vehicle_type": registry_vehicle.vehicle_type,
            "manufacture_year": registry_vehicle.manufacture_year,
            "color": registry_vehicle.color,
            "engine_capacity_cc": registry_vehicle.engine_capacity_cc,
            "pkb": str(registry_vehicle.pkb),
            "njkb": str(registry_vehicle.njkb),
            "owner_name": registry_vehicle.owner_name,
            "owner_nik": registry_vehicle.owner_nik,
            "ownership_status": request.ownership_status,
            "usage_type": request.usage_type,
            "quota_mode": request.quota_mode,
            "status": request.status,
            "review_note": request.review_note,
            "submitted_at": request.submitted_at,
            "reviewed_at": request.reviewed_at,
            "documents": request.documents,
        }

    async def approve_vehicle_ownership_request_public(
        self,
        request_id: str,
        review_note: str | None = None,
    ) -> dict:
        request = await self.repo.get_vehicle_ownership_request_by_id(request_id)
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle ownership request not found.",
            )

        if request.status == VehicleOwnershipRequestStatus.APPROVED and request.approved_vehicle_ownership_id:
            return {
                "request_id": request.id,
                "status": request.status,
                "approved_vehicle_ownership_id": request.approved_vehicle_ownership_id,
                "message": "Vehicle ownership request was already approved.",
            }

        final_storage_dir: Path | None = None
        try:
            ownership = VehicleOwnership(
                owner_type=VehicleOwnerType.BUYER_PROFILE,
                owner_id=request.buyer_profile_id,
                vehicle_id=request.vehicle_id,
                ownership_status=request.ownership_status,
                usage_type=request.usage_type,
                quota_mode=request.quota_mode,
                plate_number_snapshot=request.plate_number_snapshot,
                ktp_nfc_id_snapshot=request.ktp_nfc_id_snapshot,
            )
            await self.repo.create_vehicle_ownership(ownership)

            copied_documents = []
            for request_document in request.documents:
                copied_documents.append(
                    self._copy_request_document_to_ownership(
                        ownership_id=ownership.id,
                        request_id=request.id,
                        request_document=request_document,
                    )
                )

            await self.repo.add_documents(copied_documents)

            request.status = VehicleOwnershipRequestStatus.APPROVED
            request.approved_vehicle_ownership_id = ownership.id
            request.review_note = review_note
            request.reviewed_at = self._utcnow()

            if request.usage_type in {
                VehicleUsageType.PERSONAL,
                VehicleUsageType.COMMERCIAL_MOTORCYCLE,
                VehicleUsageType.COMMERCIAL_CAR,
                VehicleUsageType.COMMERCIAL_TRUCK,
            }:
                await self._recompute_kk_subsidy_eligibility(request.buyer_profile_id)

            await self.repo.commit()
        except HTTPException:
            await self.repo.rollback()
            self._cleanup_storage_dir(final_storage_dir)
            raise
        except Exception:
            await self.repo.rollback()
            self._cleanup_storage_dir(final_storage_dir)
            raise

        return {
            "request_id": request.id,
            "status": request.status,
            "approved_vehicle_ownership_id": ownership.id,
            "message": "Vehicle ownership request approved and final ownership created.",
        }

    async def get_buyer_family_overview(self, current_user: User) -> dict:
        buyer_profile = await self.repo.get_buyer_profile_by_user_id(current_user.id)
        if not buyer_profile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Buyer profile not found for current user.",
            )

        citizens = await self.repo.get_citizens_by_kk_id(buyer_profile.kk_id)
        buyer_profiles = await self.repo.get_buyer_profiles_by_kk_id(buyer_profile.kk_id)
        buyer_profiles_by_nik = {profile.nik_snapshot: profile for profile in buyer_profiles}
        owner_ids = [profile.id for profile in buyer_profiles]
        ownerships = await self.repo.get_vehicle_ownerships_by_owner_ids(owner_ids)

        members = [self._build_family_member_payload(citizen, buyer_profiles_by_nik, current_user.id) for citizen in citizens]

        ownerships_by_vehicle_id: dict[UUID, list] = {}
        for ownership in ownerships:
            ownerships_by_vehicle_id.setdefault(ownership.vehicle_id, []).append(ownership)

        vehicles = []
        for vehicle_id, grouped_ownerships in ownerships_by_vehicle_id.items():
            primary_ownership = grouped_ownerships[0]
            registry_vehicle = await self.repo.get_vehicle_registry_by_id(vehicle_id)
            type_label = primary_ownership.plate_number_snapshot
            if registry_vehicle is not None:
                type_label = f"{registry_vehicle.brand} - {registry_vehicle.vehicle_type}"

            holders = []
            seen_holder_ids: set[UUID] = set()
            for ownership in grouped_ownerships:
                for profile in buyer_profiles:
                    if profile.id == ownership.owner_id and profile.id not in seen_holder_ids:
                        seen_holder_ids.add(profile.id)
                        holders.append(
                            {
                                "buyer_profile_id": profile.id,
                                "name": profile.user.name if profile.user else "-",
                                "nik_masked": self._mask_nik(profile.nik_snapshot),
                            }
                        )

            vehicles.append(
                {
                    "ownership_id": primary_ownership.id,
                    "vehicle_id": primary_ownership.vehicle_id,
                    "plate_number": primary_ownership.plate_number_snapshot,
                    "type_label": type_label,
                    "usage_type": primary_ownership.usage_type,
                    "category": self._to_vehicle_category(primary_ownership.usage_type),
                    "holders": holders,
                }
            )

        return {"members": members, "vehicles": vehicles}

    async def stream_vehicle_ownership_document(
        self,
        current_user: User,
        ownership_id: str,
        document_id: str,
    ) -> StreamingResponse:
        buyer_profile = await self.repo.get_buyer_profile_by_user_id(current_user.id)
        if not buyer_profile:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Buyer profile not found for current user.")

        ownership = await self.get_vehicle_ownership(ownership_id)
        if ownership.ktp_nfc_id_snapshot != buyer_profile.ktp_nfc_id_snapshot:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle ownership not found")

        document = await self.repo.get_vehicle_ownership_document_by_id(document_id)
        if not document or document.vehicle_ownership_id != ownership.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle ownership document not found")

        try:
            content, content_type = self.storage.get_file(document.storage_key)
        except Exception:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored vehicle ownership document file not found")

        return StreamingResponse(
            io.BytesIO(content),
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{document.original_filename or "document"}"'
            }
        )

    async def stream_vehicle_ownership_request_document(
        self,
        current_user: User,
        request_id: str,
        document_id: str,
    ) -> StreamingResponse:
        request = await self.get_vehicle_ownership_request_for_buyer(current_user=current_user, request_id=request_id)
        document = await self.repo.get_vehicle_ownership_request_document_by_id(document_id)
        if not document or document.vehicle_ownership_request_id != request.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle ownership request document not found")

        try:
            content, content_type = self.storage.get_file(document.storage_key)
        except Exception:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored vehicle ownership request document file not found")

        return StreamingResponse(
            io.BytesIO(content),
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{document.original_filename or "document"}"'
            }
        )

    async def update_vehicle_ownership(
        self,
        ownership_id: str,
        ownership_in: VehicleOwnershipUpdate,
    ) -> VehicleOwnership:
        ownership = await self.get_vehicle_ownership(ownership_id)

        update_data = ownership_in.model_dump(exclude_unset=True)
        next_quota_mode = update_data.get("quota_mode", ownership.quota_mode)
        next_owner_type = ownership.owner_type

        if (
            next_quota_mode == VehicleQuotaMode.OWNER_PERSONAL_QUOTA
            and next_owner_type != VehicleOwnerType.BUYER_PROFILE
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only buyer-owned vehicles can use owner personal quota.",
            )

        for field, value in update_data.items():
            setattr(ownership, field, value)

        return await self.repo.update_vehicle_ownership(ownership)

    async def create_vehicle_ownership(
        self,
        owner_type: VehicleOwnerType,
        owner_id: str,
        vehicle_id: str,
        ownership_status: VehicleOwnershipStatus,
        usage_type: VehicleUsageType,
        quota_mode: VehicleQuotaMode,
        plate_number_snapshot: str,
        ktp_nfc_id_snapshot: str,
        stnk_photo: UploadFile,
        vehicle_photo: UploadFile,
        productive_business_proof: UploadFile | None = None,
        assigned_user_id: str | None = None,
    ) -> VehicleOwnership:
        self._validate_quota_mode(owner_type=owner_type, quota_mode=quota_mode)
        self._validate_business_proof_requirement(usage_type, productive_business_proof)

        try:
            parsed_owner_id = UUID(owner_id)
            parsed_vehicle_id = UUID(vehicle_id)
            parsed_assigned_user_id = UUID(assigned_user_id) if assigned_user_id else None
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="owner_id, vehicle_id, and assigned_user_id must be valid UUID values.",
            ) from exc

        await self._validate_image_upload(stnk_photo, label="STNK photo")
        await self._validate_image_upload(vehicle_photo, label="vehicle photo")
        if productive_business_proof is not None:
            await self._validate_supporting_upload(productive_business_proof, label="productive business proof")

        ownership = VehicleOwnership(
            owner_type=owner_type,
            owner_id=parsed_owner_id,
            vehicle_id=parsed_vehicle_id,
            ownership_status=ownership_status,
            usage_type=usage_type,
            quota_mode=quota_mode,
            plate_number_snapshot=plate_number_snapshot,
            ktp_nfc_id_snapshot=ktp_nfc_id_snapshot,
            assigned_user_id=parsed_assigned_user_id,
        )

        uploaded_keys: list[str] = []
        try:
            await self.repo.create_vehicle_ownership(ownership)
            documents = [
                await self._build_document(
                    ownership_id=ownership.id,
                    upload=stnk_photo,
                    document_type=VehicleOwnershipDocumentType.STNK_PHOTO,
                    uploaded_keys=uploaded_keys,
                ),
                await self._build_document(
                    ownership_id=ownership.id,
                    upload=vehicle_photo,
                    document_type=VehicleOwnershipDocumentType.VEHICLE_PHOTO,
                    uploaded_keys=uploaded_keys,
                ),
            ]

            if productive_business_proof is not None:
                documents.append(
                    await self._build_document(
                        ownership_id=ownership.id,
                        upload=productive_business_proof,
                        document_type=VehicleOwnershipDocumentType.PRODUCTIVE_BUSINESS_PROOF,
                        uploaded_keys=uploaded_keys,
                    )
                )

            await self.repo.add_documents(documents)

            if owner_type == VehicleOwnerType.BUYER_PROFILE and usage_type in {
                VehicleUsageType.PERSONAL,
                VehicleUsageType.COMMERCIAL_MOTORCYCLE,
                VehicleUsageType.COMMERCIAL_CAR,
                VehicleUsageType.COMMERCIAL_TRUCK,
            }:
                buyer_profile = await self.repo.get_buyer_profile_by_id(parsed_owner_id)
                if buyer_profile is not None:
                    await self._recompute_kk_subsidy_eligibility(parsed_owner_id)

            await self.repo.commit()
        except HTTPException:
            await self.repo.rollback()
            self._cleanup_uploaded_keys(uploaded_keys)
            raise
        except Exception:
            await self.repo.rollback()
            self._cleanup_uploaded_keys(uploaded_keys)
            raise

        saved_ownership = await self.repo.get_vehicle_ownership_by_id(str(ownership.id))
        if not saved_ownership:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Vehicle ownership was created but could not be reloaded.",
            )
        return saved_ownership

    async def submit_buyer_vehicle(
        self,
        current_user: User,
        registration_number: str,
        usage_type: VehicleUsageType,
        stnk_photo: UploadFile,
        vehicle_photo: UploadFile,
        productive_business_proof: UploadFile | None = None,
    ) -> dict:
        # Company owned operational vehicles are not submitted via the buyer portal

        buyer_profile = await self.repo.get_buyer_profile_by_user_id(current_user.id)
        if not buyer_profile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Buyer profile not found for current user.",
            )

        vehicle = await self.repo.get_vehicle_registry_by_registration(registration_number)
        if not vehicle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Vehicle with registration number {registration_number} not found.",
            )

        if usage_type == VehicleUsageType.PERSONAL:
            ownership = await self.create_vehicle_ownership(
                owner_type=VehicleOwnerType.BUYER_PROFILE,
                owner_id=str(buyer_profile.id),
                vehicle_id=str(vehicle.id),
                ownership_status=VehicleOwnershipStatus.PERSONAL,
                usage_type=usage_type,
                quota_mode=VehicleQuotaMode.OWNER_PERSONAL_QUOTA,
                plate_number_snapshot=vehicle.plate_number,
                ktp_nfc_id_snapshot=buyer_profile.ktp_nfc_id_snapshot,
                stnk_photo=stnk_photo,
                vehicle_photo=vehicle_photo,
                productive_business_proof=productive_business_proof,
            )
            return {
                "submission_type": "created",
                "message": "Kendaraan berhasil ditambahkan.",
                "ownership": ownership,
                "request": None,
            }

        request = await self._create_vehicle_ownership_request(
            buyer_profile_id=buyer_profile.id,
            vehicle_id=vehicle.id,
            plate_number_snapshot=vehicle.plate_number,
            ktp_nfc_id_snapshot=buyer_profile.ktp_nfc_id_snapshot,
            usage_type=usage_type,
            stnk_photo=stnk_photo,
            vehicle_photo=vehicle_photo,
            productive_business_proof=productive_business_proof,
        )
        return {
            "submission_type": "pending_review",
            "message": "Pengajuan kendaraan berhasil dikirim dan sedang ditinjau admin.",
            "ownership": None,
            "request": request,
        }

    async def _create_vehicle_ownership_request(
        self,
        buyer_profile_id: UUID,
        vehicle_id: UUID,
        plate_number_snapshot: str,
        ktp_nfc_id_snapshot: str,
        usage_type: VehicleUsageType,
        stnk_photo: UploadFile,
        vehicle_photo: UploadFile,
        productive_business_proof: UploadFile | None,
    ) -> VehicleOwnershipRequest:
        self._validate_business_proof_requirement(usage_type, productive_business_proof)

        await self._validate_image_upload(stnk_photo, label="STNK photo")
        await self._validate_image_upload(vehicle_photo, label="vehicle photo")
        if productive_business_proof is not None:
            await self._validate_supporting_upload(productive_business_proof, label="productive business proof")

        request = VehicleOwnershipRequest(
            buyer_profile_id=buyer_profile_id,
            vehicle_id=vehicle_id,
            ownership_status=VehicleOwnershipStatus.PERSONAL,
            usage_type=usage_type,
            quota_mode=VehicleQuotaMode.DEDICATED_VEHICLE_QUOTA,
            plate_number_snapshot=plate_number_snapshot,
            ktp_nfc_id_snapshot=ktp_nfc_id_snapshot,
            status=VehicleOwnershipRequestStatus.PENDING,
        )

        uploaded_keys: list[str] = []
        try:
            await self.repo.create_vehicle_ownership_request(request)
            documents = [
                await self._build_request_document(
                    request_id=request.id,
                    upload=stnk_photo,
                    document_type=VehicleOwnershipDocumentType.STNK_PHOTO,
                    uploaded_keys=uploaded_keys,
                ),
                await self._build_request_document(
                    request_id=request.id,
                    upload=vehicle_photo,
                    document_type=VehicleOwnershipDocumentType.VEHICLE_PHOTO,
                    uploaded_keys=uploaded_keys,
                ),
            ]
            if productive_business_proof is not None:
                documents.append(
                    await self._build_request_document(
                        request_id=request.id,
                        upload=productive_business_proof,
                        document_type=VehicleOwnershipDocumentType.PRODUCTIVE_BUSINESS_PROOF,
                        uploaded_keys=uploaded_keys,
                    )
                )
            await self.repo.add_request_documents(documents)
            await self.repo.commit()
        except HTTPException:
            await self.repo.rollback()
            self._cleanup_uploaded_keys(uploaded_keys)
            raise
        except Exception:
            await self.repo.rollback()
            self._cleanup_uploaded_keys(uploaded_keys)
            raise

        saved_request = await self.repo.get_vehicle_ownership_request_by_id(str(request.id))
        if not saved_request:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Vehicle ownership request was created but could not be reloaded.",
            )
        return saved_request

    def _validate_quota_mode(self, owner_type: VehicleOwnerType, quota_mode: VehicleQuotaMode) -> None:
        if quota_mode == VehicleQuotaMode.OWNER_PERSONAL_QUOTA and owner_type != VehicleOwnerType.BUYER_PROFILE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only buyer-owned vehicles can use owner personal quota.",
            )

    def _validate_business_proof_requirement(
        self,
        usage_type: VehicleUsageType,
        productive_business_proof: UploadFile | None,
    ) -> None:
        if usage_type in {
            VehicleUsageType.COMMERCIAL_MOTORCYCLE,
            VehicleUsageType.COMMERCIAL_CAR,
            VehicleUsageType.COMMERCIAL_TRUCK,
        } and productive_business_proof is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Productive business proof is required for commercial vehicles.",
            )

    async def _validate_image_upload(self, upload: UploadFile, label: str) -> None:
        if not upload.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{label} filename is required.",
            )
        if len(upload.filename) > self.MAX_FILE_NAME_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{label} filename is too long.",
            )
        content_type = upload.content_type or ""
        if not content_type.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{label} must be an image file.",
            )

    async def _validate_supporting_upload(self, upload: UploadFile, label: str) -> None:
        if not upload.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{label} filename is required.",
            )
        if len(upload.filename) > self.MAX_FILE_NAME_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{label} filename is too long.",
            )
        content_type = upload.content_type or ""
        if not (content_type.startswith("image/") or content_type == "application/pdf"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{label} must be an image or PDF file.",
            )

    async def _build_document(
        self,
        ownership_id,
        upload: UploadFile,
        document_type: VehicleOwnershipDocumentType,
        uploaded_keys: list[str],
    ) -> VehicleOwnershipDocument:
        file_bytes = await upload.read()
        if not file_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{document_type.value} file is empty.",
            )
        if len(file_bytes) > self.MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{document_type.value} file exceeds the 5 MB upload limit.",
            )

        suffix = self._guess_file_suffix(upload)
        file_name = f"{document_type.value.lower().replace('_', '-')}{suffix}"
        storage_key = f"vehicle-ownerships/{ownership_id}/{file_name}"
        
        self.storage.save_file(storage_key, file_bytes, upload.content_type)
        uploaded_keys.append(storage_key)

        return VehicleOwnershipDocument(
            vehicle_ownership_id=ownership_id,
            document_type=document_type,
            storage_key=storage_key,
            original_filename=upload.filename,
            mime_type=upload.content_type,
            file_size_bytes=len(file_bytes),
            checksum_sha256=hashlib.sha256(file_bytes).hexdigest(),
        )

    async def _build_request_document(
        self,
        request_id,
        upload: UploadFile,
        document_type: VehicleOwnershipDocumentType,
        uploaded_keys: list[str],
    ) -> VehicleOwnershipRequestDocument:
        file_bytes = await upload.read()
        if not file_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{document_type.value} file is empty.",
            )
        if len(file_bytes) > self.MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{document_type.value} file exceeds the 5 MB upload limit.",
            )

        suffix = self._guess_file_suffix(upload)
        file_name = f"{document_type.value.lower().replace('_', '-')}{suffix}"
        storage_key = f"vehicle-ownership-requests/{request_id}/{file_name}"
        
        self.storage.save_file(storage_key, file_bytes, upload.content_type)
        uploaded_keys.append(storage_key)

        return VehicleOwnershipRequestDocument(
            vehicle_ownership_request_id=request_id,
            document_type=document_type,
            storage_key=storage_key,
            original_filename=upload.filename,
            mime_type=upload.content_type,
            file_size_bytes=len(file_bytes),
            checksum_sha256=hashlib.sha256(file_bytes).hexdigest(),
        )

    def _copy_request_document_to_ownership(
        self,
        ownership_id: UUID,
        request_id: UUID,
        request_document: VehicleOwnershipRequestDocument,
    ) -> VehicleOwnershipDocument:
        try:
            content, content_type = self.storage.get_file(request_document.storage_key)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stored vehicle ownership request document file not found during approval.",
            )

        file_name = request_document.storage_key.split("/")[-1]
        target_storage_key = f"vehicle-ownerships/{ownership_id}/{file_name}"
        
        self.storage.save_file(target_storage_key, content, content_type)

        return VehicleOwnershipDocument(
            vehicle_ownership_id=ownership_id,
            document_type=request_document.document_type,
            storage_key=target_storage_key,
            original_filename=request_document.original_filename,
            mime_type=request_document.mime_type,
            file_size_bytes=request_document.file_size_bytes,
            checksum_sha256=request_document.checksum_sha256,
        )

    def _guess_file_suffix(self, upload: UploadFile) -> str:
        original_suffix = Path(upload.filename or "").suffix.lower()
        if original_suffix:
            return original_suffix

        guessed_suffix = mimetypes.guess_extension(upload.content_type or "")
        if guessed_suffix:
            return guessed_suffix
        return ".bin"

    def _cleanup_uploaded_keys(self, uploaded_keys: list[str]) -> None:
        for key in uploaded_keys:
            try:
                self.storage.delete_file(key)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to delete {key} during cleanup: {e}")

    def _cleanup_storage_dir(self, directory: Path | None) -> None:
        if directory and directory.exists():
            try:
                import shutil
                shutil.rmtree(directory)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to delete directory {directory} during cleanup: {e}")

    def _to_vehicle_category(self, usage_type: VehicleUsageType) -> str:
        if usage_type == VehicleUsageType.PERSONAL:
            return "nonCommercial"
        return "commercial"

    def _mask_nik(self, nik: str) -> str:
        if len(nik) <= 8:
            return nik
        return f"{nik[:4]}****{nik[-4:]}"

    def _utcnow(self):
        return datetime.utcnow()

    def _compute_account_status(
        self,
        *,
        is_blocked: bool,
        is_frozen: bool,
        is_quota_active: bool,
        remaining_liters: float,
    ) -> str:
        """Return a single enum string representing the buyer's subsidy account state.

        Priority order:
          BANNED          — account permanently blocked (fraud / policy violation)
          FROZEN          — account temporarily frozen
          NOT_ELIGIBLE    — quota record not active (no KK match / income too high)
          QUOTA_EXHAUSTED — quota active but monthly allowance fully consumed
          ACTIVE          — eligible and has remaining quota
        """
        if is_blocked:
            return "BANNED"
        if is_frozen:
            return "FROZEN"
        if not is_quota_active:
            return "NOT_ELIGIBLE"
        if remaining_liters <= 0:
            return "QUOTA_EXHAUSTED"
        return "ACTIVE"

    def _build_family_member_payload(
        self,
        citizen: CitizenRegistryMockup,
        buyer_profiles_by_nik: dict[str, object],
        current_user_id: UUID,
    ) -> dict:
        buyer_profile = buyer_profiles_by_nik.get(citizen.nik)
        is_registered_buyer = buyer_profile is not None
        is_verified = bool(
            buyer_profile is not None and getattr(buyer_profile, "verification_status", None) == VerificationStatus.VERIFIED
        )
        role = "Anggota KK"
        if buyer_profile is not None and getattr(buyer_profile, "user_id", None) == current_user_id:
            role = "Pemilik Akun"
        return {
            "name": citizen.nama,
            "role": role,
            "nik_masked": self._mask_nik(citizen.nik),
            "is_registered_buyer": is_registered_buyer,
            "is_verified": is_verified,
        }

    async def _build_family_holders_for_vehicle(self, buyer_profile_kk_id: UUID, vehicle_id: UUID) -> list[dict]:
        buyer_profiles = await self.repo.get_buyer_profiles_by_kk_id(buyer_profile_kk_id)
        owner_ids = [profile.id for profile in buyer_profiles]
        ownerships = await self.repo.get_vehicle_ownerships_by_owner_ids(owner_ids)
        holders = []
        seen_holder_ids: set[UUID] = set()
        for ownership in ownerships:
            if ownership.vehicle_id != vehicle_id:
                continue
            for profile in buyer_profiles:
                if profile.id == ownership.owner_id and profile.id not in seen_holder_ids:
                    seen_holder_ids.add(profile.id)
                    holders.append(
                        {
                            "buyer_profile_id": profile.id,
                            "name": profile.user.name if profile.user else "-",
                            "nik_masked": self._mask_nik(profile.nik_snapshot),
                        }
                    )
        return holders

    async def _build_vehicle_quota_summary(
        self,
        ownership: VehicleOwnership,
        buyer_profile,
        month: int,
        year: int,
    ) -> dict[str, float | None]:
        if ownership.usage_type not in {
            VehicleUsageType.PERSONAL,
            VehicleUsageType.COMMERCIAL_MOTORCYCLE,
            VehicleUsageType.COMMERCIAL_CAR,
            VehicleUsageType.COMMERCIAL_TRUCK,
        }:
            return {
                "quota_liters": None,
                "used_liters": None,
                "remaining_liters": None,
            }

        policy = await self.repo.get_subsidy_policy_by_usage_type(ownership.usage_type)
        if policy is None:
            return {
                "quota_liters": None,
                "used_liters": None,
                "remaining_liters": None,
            }

        if ownership.usage_type == VehicleUsageType.PERSONAL:
            latest_eligibility = await self.repo.get_latest_kk_subsidy_eligibility(
                kk_id=buyer_profile.kk_id,
                subsidy_policy_id=policy.id,
            )
            if latest_eligibility is None or latest_eligibility.eligibility_status != EligibilityStatus.ELIGIBLE:
                return {
                    "quota_liters": None,
                    "used_liters": None,
                    "remaining_liters": None,
                }
            quota_owner_type = SubsidyOwnerType.BUYER_PROFILE
            quota_owner_id = ownership.owner_id
        else:
            quota_owner_type = SubsidyOwnerType.VEHICLE
            quota_owner_id = ownership.vehicle_id

        quota = await self.repo.get_subsidy_quota_by_owner(
            owner_type=quota_owner_type,
            owner_id=quota_owner_id,
            month=month,
            year=year,
        )

        quota_liters = Decimal(policy.monthly_quota_liters) * self._quota_trust_factor(
            Decimal(buyer_profile.risk_score)
        )
        used_liters = Decimal(quota.used_liters) if quota is not None else Decimal("0")
        remaining_liters = quota_liters - used_liters
        if remaining_liters < 0:
            remaining_liters = Decimal("0")

        return {
            "quota_liters": float(quota_liters),
            "used_liters": float(used_liters),
            "remaining_liters": float(remaining_liters),
        }

    async def _recompute_kk_subsidy_eligibility(self, buyer_profile_id: UUID) -> None:
        buyer_profile = await self.repo.get_buyer_profile_by_id(buyer_profile_id)
        if buyer_profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Buyer profile not found for KK eligibility recompute.",
            )

        from app.modules.registries.models import CitizenRegistryMockup
        from app.modules.subsidies.models import SubsidySetting, KKSubsidyEligibility, EligibilityStatus
        from sqlalchemy import select

        # 1. Ambil income_threshold dari SubsidySetting
        setting_stmt = select(SubsidySetting)
        setting = (await self.db.execute(setting_stmt)).scalars().first()
        income_threshold = Decimal(setting.income_threshold) if setting else Decimal("5000000.00")

        # 2. Hitung jumlah anggota keluarga dan rata-rata penghasilan KK
        citizen_stmt = select(CitizenRegistryMockup).filter(CitizenRegistryMockup.kk_id == buyer_profile.kk_id)
        citizens = (await self.db.execute(citizen_stmt)).scalars().all()
        
        member_count = len(citizens)
        total_income = sum(Decimal(c.penghasilan or 0) for c in citizens)
        avg_income = total_income / Decimal(member_count) if member_count > 0 else Decimal("0.00")

        # 3. Ambil/buat KKSubsidyEligibility
        personal_policy = await self.repo.get_subsidy_policy_by_usage_type(VehicleUsageType.PERSONAL)
        if personal_policy is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subsidy policy for PERSONAL usage type not found.",
            )

        eligibility = await self.repo.get_latest_kk_subsidy_eligibility(
            kk_id=buyer_profile.kk_id,
            subsidy_policy_id=personal_policy.id,
        )
        if eligibility is None:
            eligibility = KKSubsidyEligibility(
                kk_id=buyer_profile.kk_id,
                subsidy_policy_id=personal_policy.id,
                total_njkb=avg_income,
                eligibility_status=EligibilityStatus.ELIGIBLE,
            )
            await self.repo.create_kk_subsidy_eligibility(eligibility)

        is_eligible = avg_income <= income_threshold
        eligibility.total_njkb = avg_income
        eligibility.eligibility_status = (
            EligibilityStatus.ELIGIBLE if is_eligible else EligibilityStatus.NOT_ELIGIBLE
        )
        eligibility.eligibility_reason = (
            f"Rata-rata penghasilan KK adalah Rp {avg_income:,.2f} (di bawah batas Rp {income_threshold:,.2f})."
            if is_eligible
            else f"Rata-rata penghasilan KK adalah Rp {avg_income:,.2f} (melebihi batas Rp {income_threshold:,.2f})."
        )
        eligibility.checked_at = self._utcnow()

    def _quota_trust_factor(self, risk_score: Decimal) -> Decimal:
        trust_factor = Decimal("1") - (risk_score / Decimal("100"))
        if trust_factor < Decimal("0"):
            return Decimal("0")
        return trust_factor

    def _is_account_suspended(self, risk_score: Decimal) -> bool:
        return risk_score > Decimal("85")

    async def get_all_vehicle_requests_admin(self) -> list:
        from app.modules.vehicles.schemas import AdminVehicleRequestResponse, VehicleOwnershipDocumentResponse
        requests = await self.repo.get_all_vehicle_ownership_requests()
        results = []
        for req in requests:
            buyer_profile = req.buyer_profile
            buyer_name = ""
            buyer_nik = ""
            company_id = req.company_id
            company_name = None
            company_nib = None

            if buyer_profile:
                buyer_nik = buyer_profile.nik_snapshot
                if buyer_profile.user:
                    buyer_name = buyer_profile.user.name
            elif req.company:
                company_name = req.company.name
                company_nib = req.company.nib
                # Defensively fill buyer fields for older frontend compatibility
                buyer_name = req.company.name
                buyer_nik = req.company.nib

            results.append(
                AdminVehicleRequestResponse(
                    id=req.id,
                    buyer_profile_id=req.buyer_profile_id,
                    buyer_name=buyer_name,
                    buyer_nik=buyer_nik,
                    company_id=company_id,
                    company_name=company_name,
                    company_nib=company_nib,
                    vehicle_id=req.vehicle_id,
                    ownership_status=req.ownership_status,
                    usage_type=req.usage_type,
                    quota_mode=req.quota_mode,
                    plate_number_snapshot=req.plate_number_snapshot,
                    ktp_nfc_id_snapshot=req.ktp_nfc_id_snapshot,
                    vehicle_nfc_id=req.vehicle_nfc_id,
                    status=req.status,
                    review_note=req.review_note,
                    submitted_at=req.submitted_at,
                    reviewed_at=req.reviewed_at,
                    documents=[
                        VehicleOwnershipDocumentResponse.model_validate(doc)
                        for doc in req.documents
                    ]
                )
            )
        return results

    async def stream_vehicle_ownership_request_document_admin(
        self,
        request_id: str,
        document_id: str,
    ) -> StreamingResponse:
        document = await self.repo.get_vehicle_ownership_request_document_by_id(document_id)
        if not document or str(document.vehicle_ownership_request_id) != str(request_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle ownership request document not found")

        try:
            content, content_type = self.storage.get_file(document.storage_key)
        except Exception:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored vehicle ownership request document file not found")

        return StreamingResponse(
            io.BytesIO(content),
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{document.original_filename or "document"}"'
            }
        )

    async def verify_vehicle_request_admin(
        self,
        request_id: str,
        status_str: str,
        review_note: str | None = None,
    ) -> dict:
        request = await self.repo.get_vehicle_ownership_request_by_id(request_id)
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle ownership request not found.",
            )

        if request.status in {VehicleOwnershipRequestStatus.APPROVED, VehicleOwnershipRequestStatus.REJECTED}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Vehicle ownership request was already processed as {request.status.value}.",
            )

        if status_str == "APPROVED":
            # Validate vehicle class against usage type
            from app.modules.registries.models import VehicleClass
            registry_vehicle = await self.repo.get_vehicle_registry_by_id(request.vehicle_id)
            if registry_vehicle:
                if request.usage_type == VehicleUsageType.COMMERCIAL_MOTORCYCLE:
                    if registry_vehicle.jenis != VehicleClass.MOTORCYCLE:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="COMMERCIAL_MOTORCYCLE usage registration requires a motorcycle vehicle class."
                        )
                elif request.usage_type == VehicleUsageType.COMMERCIAL_CAR:
                    if registry_vehicle.jenis != VehicleClass.CAR:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="COMMERCIAL_CAR usage registration requires a car vehicle class."
                        )
                elif request.usage_type == VehicleUsageType.COMMERCIAL_TRUCK:
                    if registry_vehicle.jenis != VehicleClass.TRUCK:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="COMMERCIAL_TRUCK usage registration requires a truck vehicle class."
                        )

            final_storage_dir: Path | None = None
            try:
                if request.company_id:
                    ownership = VehicleOwnership(
                        owner_type=VehicleOwnerType.COMPANY,
                        owner_id=request.company_id,
                        vehicle_id=request.vehicle_id,
                        ownership_status=request.ownership_status,
                        usage_type=request.usage_type,
                        quota_mode=request.quota_mode,
                        plate_number_snapshot=request.plate_number_snapshot,
                        ktp_nfc_id_snapshot=request.ktp_nfc_id_snapshot,
                        vehicle_nfc_id=request.vehicle_nfc_id,
                    )
                else:
                    ownership = VehicleOwnership(
                        owner_type=VehicleOwnerType.BUYER_PROFILE,
                        owner_id=request.buyer_profile_id,
                        vehicle_id=request.vehicle_id,
                        ownership_status=request.ownership_status,
                        usage_type=request.usage_type,
                        quota_mode=request.quota_mode,
                        plate_number_snapshot=request.plate_number_snapshot,
                        ktp_nfc_id_snapshot=request.ktp_nfc_id_snapshot,
                        vehicle_nfc_id=request.vehicle_nfc_id,
                    )
                await self.repo.create_vehicle_ownership(ownership)

                copied_documents = []
                for request_document in request.documents:
                    copied_documents.append(
                        self._copy_request_document_to_ownership(
                            ownership_id=ownership.id,
                            request_id=request.id,
                            request_document=request_document,
                        )
                    )

                await self.repo.add_documents(copied_documents)

                request.status = VehicleOwnershipRequestStatus.APPROVED
                request.approved_vehicle_ownership_id = ownership.id
                request.review_note = review_note
                request.reviewed_at = self._utcnow()

                if request.company_id:
                    # Create SubsidyQuota for company vehicle
                    from app.modules.subsidies.models import SubsidyQuota, SubsidyPolicy, SubsidyOwnerType
                    from decimal import Decimal
                    from sqlalchemy import select
                    
                    policy_stmt = select(SubsidyPolicy).filter(SubsidyPolicy.usage_type == request.usage_type)
                    policy = (await self.db.execute(policy_stmt)).scalars().first()
                    limit = policy.monthly_quota_liters if policy else Decimal("200.00")
                    
                    quota = SubsidyQuota(
                        owner_type=SubsidyOwnerType.VEHICLE,
                        owner_id=request.vehicle_id,
                        subsidy_policy_id=policy.id if policy else None,
                        month=request.submitted_at.month,
                        year=request.submitted_at.year,
                        quota_liters=limit,
                        used_liters=Decimal("0.00"),
                        is_active=True,
                    )
                    self.db.add(quota)
                else:
                    # Recalculate KK eligibility for buyer
                    if request.usage_type in {
                        VehicleUsageType.PERSONAL,
                        VehicleUsageType.COMMERCIAL_MOTORCYCLE,
                        VehicleUsageType.COMMERCIAL_CAR,
                        VehicleUsageType.COMMERCIAL_TRUCK,
                    }:
                        await self._recompute_kk_subsidy_eligibility(request.buyer_profile_id)

                await self.repo.commit()
            except HTTPException:
                await self.repo.rollback()
                self._cleanup_storage_dir(final_storage_dir)
                raise
            except Exception:
                await self.repo.rollback()
                self._cleanup_storage_dir(final_storage_dir)
                raise

            return {
                "request_id": request.id,
                "status": request.status.value,
                "approved_vehicle_ownership_id": ownership.id,
                "message": "Vehicle ownership request approved and final ownership created.",
            }

        elif status_str == "REJECTED":
            try:
                request.status = VehicleOwnershipRequestStatus.REJECTED
                request.review_note = review_note
                request.reviewed_at = self._utcnow()
                await self.repo.commit()
            except Exception:
                await self.repo.rollback()
                raise

            return {
                "request_id": request.id,
                "status": request.status.value,
                "approved_vehicle_ownership_id": None,
                "message": "Vehicle ownership request rejected by admin.",
            }

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification status. Must be APPROVED or REJECTED.",
            )

    async def calculate_cashier_pricing(
        self,
        *,
        nik: str,
        fuel_type_id: UUID,
        calc_type: str,
        nominal: float,
        plate_number: str | None = None,
    ) -> dict[str, Any]:
        from decimal import Decimal
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from app.modules.users.models import BuyerProfile, VerificationStatus
        from app.modules.vehicles.models import VehicleOwnership, VehicleUsageType
        from app.modules.fuels.models import FuelType, SubsidyType
        from app.modules.subsidies.service import SubsidyService
        from app.modules.subsidies.models import EligibilityStatus

        # 1. Lookup buyer profile
        res_profile = await self.db.execute(
            select(BuyerProfile)
            .options(selectinload(BuyerProfile.user))
            .filter(BuyerProfile.nik_snapshot == nik),
        )
        buyer_profile = res_profile.scalars().first()
        if not buyer_profile:
            # Fallback by NFC ID
            res_profile = await self.db.execute(
                select(BuyerProfile)
                .options(selectinload(BuyerProfile.user))
                .filter(BuyerProfile.ktp_nfc_id_snapshot == nik),
            )
            buyer_profile = res_profile.scalars().first()

        if not buyer_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profil pembeli tidak ditemukan.",
            )

        # 2. Lookup vehicle ownership if plate_number is provided
        vehicle_ownership = None
        if plate_number and plate_number.strip().upper() != "-":
            res_vehicle = await self.db.execute(
                select(VehicleOwnership).filter(
                    VehicleOwnership.plate_number_snapshot == plate_number.strip().upper(),
                    VehicleOwnership.owner_id == buyer_profile.id,
                ),
            )
            vehicle_ownership = res_vehicle.scalars().first()

        # 3. Lookup fuel type
        res_fuel = await self.db.execute(
            select(FuelType).filter(FuelType.id == fuel_type_id),
        )
        fuel_type = res_fuel.scalars().first()
        if not fuel_type:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tipe bahan bakar tidak ditemukan.",
            )

        # 4. Check block/freeze status
        _user_obj = buyer_profile.user
        is_buyer_blocked = (buyer_profile.verification_status == VerificationStatus.REJECTED or 
                            (_user_obj and _user_obj.is_blocked))
        
        is_buyer_frozen = False
        if _user_obj and _user_obj.frozen_until:
            if _user_obj.frozen_until > datetime.utcnow():
                is_buyer_frozen = True

        is_eligible_for_subsidy = (
            buyer_profile.verification_status == VerificationStatus.VERIFIED
            and not is_buyer_blocked
            and not is_buyer_frozen
        )

        # 5. Fetch subsidy quota
        subsidy_service = SubsidyService(self.db)
        now = datetime.utcnow()
        month = now.month
        year = now.year

        subsidy_quota = None
        is_quota_active = False

        if fuel_type.subsidy_type == SubsidyType.SUBSIDIZED:
            if is_eligible_for_subsidy:
                if vehicle_ownership is None or vehicle_ownership.usage_type == VehicleUsageType.PERSONAL:
                    policy = await subsidy_service.repo.get_subsidy_policy_by_usage_type(VehicleUsageType.PERSONAL)
                    if policy:
                        latest_eligibility = await subsidy_service.repo.get_latest_kk_subsidy_eligibility(
                            kk_id=buyer_profile.kk_id,
                            subsidy_policy_id=policy.id,
                        )
                        if latest_eligibility and latest_eligibility.eligibility_status == EligibilityStatus.ELIGIBLE:
                            kk_eligibility_id = latest_eligibility.id
                            if vehicle_ownership is None:
                                subsidy_quota = await subsidy_service.get_or_sync_personal_quota(
                                    buyer_profile=buyer_profile,
                                    month=month,
                                    year=year,
                                )
                            else:
                                subsidy_quota = await subsidy_service.get_or_create_subsidy_quota(
                                    vehicle_ownership=vehicle_ownership,
                                    month=month,
                                    year=year,
                                    kk_subsidy_eligibility_id=kk_eligibility_id,
                                )
                else:
                    policy = await subsidy_service.repo.get_subsidy_policy_by_usage_type(vehicle_ownership.usage_type)
                    if policy:
                        subsidy_quota = await subsidy_service.get_or_create_subsidy_quota(
                            vehicle_ownership=vehicle_ownership,
                            month=month,
                            year=year,
                        )

        if subsidy_quota:
            is_quota_active = subsidy_quota.is_active

        quota_liters = float(Decimal(subsidy_quota.quota_liters)) if subsidy_quota else 0.0
        used_liters = float(Decimal(subsidy_quota.used_liters)) if subsidy_quota else 0.0
        remaining_quota = max(0.0, quota_liters - used_liters)

        # 6. Compute account status using existing helper
        account_status = self._compute_account_status(
            is_blocked=is_buyer_blocked,
            is_frozen=is_buyer_frozen,
            is_quota_active=is_quota_active,
            remaining_liters=remaining_quota,
        )

        market_price = float(Decimal(fuel_type.price_per_liter))
        subsidized_price = float(Decimal(fuel_type.subsidy_price_per_liter)) if fuel_type.subsidy_price_per_liter is not None else None

        # Buyer can use subsidy pricing only if active, is subsidized fuel, and remaining quota exists
        can_use_subsidy = (
            fuel_type.subsidy_type == SubsidyType.SUBSIDIZED
            and account_status == "ACTIVE"
            and subsidized_price is not None
            and remaining_quota > 0
        )

        # 7. Perform liters/amount pricing calculation
        if calc_type == "LITERS":
            liters = nominal
            if can_use_subsidy:
                subsidized_liters = min(liters, remaining_quota)
                non_subsidized_liters = max(0.0, liters - subsidized_liters)
                total_amount = (subsidized_liters * subsidized_price) + (non_subsidized_liters * market_price)
            else:
                subsidized_liters = 0.0
                non_subsidized_liters = liters
                total_amount = liters * market_price
        else:  # calc_type == "AMOUNT"
            total_amount = nominal
            if can_use_subsidy:
                subsidy_ceiling_amount = remaining_quota * subsidized_price
                subsidized_amount = min(float(total_amount), subsidy_ceiling_amount)
                remaining_amount = max(0.0, float(total_amount) - subsidized_amount)

                subsidized_liters = subsidized_amount / subsidized_price
                non_subsidized_liters = remaining_amount / market_price
                liters = subsidized_liters + non_subsidized_liters
            else:
                subsidized_liters = 0.0
                non_subsidized_liters = float(total_amount) / market_price
                liters = non_subsidized_liters

        return {
            "account_status": account_status,
            "price_per_liter_market": market_price,
            "price_per_liter_subsidy": subsidized_price,
            "subsidized_liters": subsidized_liters,
            "non_subsidized_liters": non_subsidized_liters,
            "total_liters": liters,
            "total_amount": int(round(total_amount)),
        }

    async def submit_company_vehicle(
        self,
        company_id: UUID,
        current_user: User,
        plate: str,
        vehicle_nfc_id: str | None,
        stnk_photo: UploadFile,
        vehicle_photo: UploadFile,
    ) -> VehicleOwnershipRequest:
        from app.modules.registries.models import VehicleRegistryMockup, VehicleClass
        from sqlalchemy import select, func
        import hashlib

        plate_clean = plate.strip().upper()

        # 1. Lookup plate number in VehicleRegistryMockup
        registry_stmt = select(VehicleRegistryMockup).filter(
            func.upper(VehicleRegistryMockup.plate_number) == plate_clean
        )
        registry_vehicle = (await self.db.execute(registry_stmt)).scalars().first()
        if not registry_vehicle:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Plat nomor tidak ditemukan di database Kepolisian (Registry Mockup)",
            )

        # 2. Check if already registered in VehicleOwnership
        existing_stmt = select(VehicleOwnership).filter(
            VehicleOwnership.vehicle_id == registry_vehicle.id
        )
        existing = (await self.db.execute(existing_stmt)).scalars().first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Kendaraan dengan plat nomor ini sudah terdaftar",
            )

        # Check if there is an active/pending request
        existing_req_stmt = select(VehicleOwnershipRequest).filter(
            VehicleOwnershipRequest.vehicle_id == registry_vehicle.id,
            VehicleOwnershipRequest.status == VehicleOwnershipRequestStatus.PENDING
        )
        existing_req = (await self.db.execute(existing_req_stmt)).scalars().first()
        if existing_req:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Kendaraan dengan plat nomor ini sedang dalam proses verifikasi",
            )

        # Determine usage type based on registry
        usage_type = VehicleUsageType.COMMERCIAL_CAR
        if registry_vehicle.jenis == VehicleClass.TRUCK:
            usage_type = VehicleUsageType.COMMERCIAL_TRUCK
        elif registry_vehicle.jenis == VehicleClass.MOTORCYCLE:
            usage_type = VehicleUsageType.COMMERCIAL_MOTORCYCLE

        # Validate and save vehicle_nfc_id if provided
        if vehicle_nfc_id:
            await self.validate_cross_nfc_uniqueness(vehicle_nfc_id)

        # Validate file uploads
        await self._validate_image_upload(stnk_photo, label="STNK photo")
        await self._validate_image_upload(vehicle_photo, label="vehicle photo")

        request = VehicleOwnershipRequest(
            company_id=company_id,
            vehicle_id=registry_vehicle.id,
            ownership_status=VehicleOwnershipStatus.COMPANY,
            usage_type=usage_type,
            quota_mode=VehicleQuotaMode.DEDICATED_VEHICLE_QUOTA,
            plate_number_snapshot=registry_vehicle.plate_number,
            ktp_nfc_id_snapshot=f"COMPANY-{str(company_id)[:8]}",
            vehicle_nfc_id=vehicle_nfc_id,
            status=VehicleOwnershipRequestStatus.PENDING,
        )

        uploaded_keys: list[str] = []
        try:
            await self.repo.create_vehicle_ownership_request(request)
            documents = [
                await self._build_request_document(
                    request_id=request.id,
                    upload=stnk_photo,
                    document_type=VehicleOwnershipDocumentType.STNK_PHOTO,
                    uploaded_keys=uploaded_keys,
                ),
                await self._build_request_document(
                    request_id=request.id,
                    upload=vehicle_photo,
                    document_type=VehicleOwnershipDocumentType.VEHICLE_PHOTO,
                    uploaded_keys=uploaded_keys,
                ),
            ]
            await self.repo.add_request_documents(documents)
            await self.repo.commit()
        except HTTPException:
            await self.repo.rollback()
            self._cleanup_uploaded_keys(uploaded_keys)
            raise
        except Exception:
            await self.repo.rollback()
            self._cleanup_uploaded_keys(uploaded_keys)
            raise

        saved_request = await self.repo.get_vehicle_ownership_request_by_id(str(request.id))
        if not saved_request:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Vehicle ownership request was created but could not be reloaded.",
            )
        return saved_request
