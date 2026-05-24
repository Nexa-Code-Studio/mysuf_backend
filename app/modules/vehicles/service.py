import hashlib
import mimetypes
import shutil
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.registries.models import CitizenRegistryMockup
from app.modules.subsidies.models import EligibilityStatus, KKSubsidyEligibility, SubsidyOwnerType
from app.modules.users.models import User, VerificationStatus
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
        self.repo = VehicleRepository(db)

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

            final_storage_dir = self.STORAGE_ROOT / str(ownership.id)
            final_storage_dir.mkdir(parents=True, exist_ok=True)

            copied_documents = []
            for request_document in request.documents:
                copied_documents.append(
                    self._copy_request_document_to_ownership(
                        ownership_id=ownership.id,
                        request_id=request.id,
                        request_document=request_document,
                        final_storage_dir=final_storage_dir,
                    )
                )

            await self.repo.add_documents(copied_documents)

            request.status = VehicleOwnershipRequestStatus.APPROVED
            request.approved_vehicle_ownership_id = ownership.id
            request.review_note = review_note
            request.reviewed_at = self._utcnow()

            if request.usage_type in {
                VehicleUsageType.PERSONAL,
                VehicleUsageType.OJOL,
                VehicleUsageType.UMKM,
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
    ) -> FileResponse:
        buyer_profile = await self.repo.get_buyer_profile_by_user_id(current_user.id)
        if not buyer_profile:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Buyer profile not found for current user.")

        ownership = await self.get_vehicle_ownership(ownership_id)
        if ownership.ktp_nfc_id_snapshot != buyer_profile.ktp_nfc_id_snapshot:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle ownership not found")

        document = await self.repo.get_vehicle_ownership_document_by_id(document_id)
        if not document or document.vehicle_ownership_id != ownership.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle ownership document not found")

        file_path = self.STORAGE_ROOT / document.storage_key
        if not file_path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored vehicle ownership document file not found")

        return FileResponse(
            path=file_path,
            media_type=document.mime_type or "application/octet-stream",
            filename=document.original_filename or file_path.name,
        )

    async def stream_vehicle_ownership_request_document(
        self,
        current_user: User,
        request_id: str,
        document_id: str,
    ) -> FileResponse:
        request = await self.get_vehicle_ownership_request_for_buyer(current_user=current_user, request_id=request_id)
        document = await self.repo.get_vehicle_ownership_request_document_by_id(document_id)
        if not document or document.vehicle_ownership_request_id != request.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle ownership request document not found")

        file_path = self.REQUEST_STORAGE_ROOT / document.storage_key
        if not file_path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored vehicle ownership request document file not found")

        return FileResponse(
            path=file_path,
            media_type=document.mime_type or "application/octet-stream",
            filename=document.original_filename or file_path.name,
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

        storage_dir: Path | None = None
        try:
            await self.repo.create_vehicle_ownership(ownership)
            storage_dir = self.STORAGE_ROOT / str(ownership.id)
            documents = [
                await self._build_document(
                    ownership_id=ownership.id,
                    upload=stnk_photo,
                    document_type=VehicleOwnershipDocumentType.STNK_PHOTO,
                    storage_dir=storage_dir,
                ),
                await self._build_document(
                    ownership_id=ownership.id,
                    upload=vehicle_photo,
                    document_type=VehicleOwnershipDocumentType.VEHICLE_PHOTO,
                    storage_dir=storage_dir,
                ),
            ]

            if productive_business_proof is not None:
                documents.append(
                    await self._build_document(
                        ownership_id=ownership.id,
                        upload=productive_business_proof,
                        document_type=VehicleOwnershipDocumentType.PRODUCTIVE_BUSINESS_PROOF,
                        storage_dir=storage_dir,
                    )
                )

            await self.repo.add_documents(documents)

            if owner_type == VehicleOwnerType.BUYER_PROFILE and usage_type in {
                VehicleUsageType.PERSONAL,
                VehicleUsageType.OJOL,
                VehicleUsageType.UMKM,
            }:
                buyer_profile = await self.repo.get_buyer_profile_by_id(parsed_owner_id)
                if buyer_profile is not None:
                    await self._recompute_kk_subsidy_eligibility(parsed_owner_id)

            await self.repo.commit()
        except HTTPException:
            await self.repo.rollback()
            self._cleanup_storage_dir(storage_dir)
            raise
        except Exception:
            await self.repo.rollback()
            self._cleanup_storage_dir(storage_dir)
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
        if usage_type == VehicleUsageType.COMPANY_OPERATIONAL:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="COMPANY_OPERATIONAL vehicles cannot be submitted from buyer app.",
            )

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

        storage_dir: Path | None = None
        try:
            await self.repo.create_vehicle_ownership_request(request)
            storage_dir = self.REQUEST_STORAGE_ROOT / str(request.id)
            documents = [
                await self._build_request_document(
                    request_id=request.id,
                    upload=stnk_photo,
                    document_type=VehicleOwnershipDocumentType.STNK_PHOTO,
                    storage_dir=storage_dir,
                ),
                await self._build_request_document(
                    request_id=request.id,
                    upload=vehicle_photo,
                    document_type=VehicleOwnershipDocumentType.VEHICLE_PHOTO,
                    storage_dir=storage_dir,
                ),
            ]
            if productive_business_proof is not None:
                documents.append(
                    await self._build_request_document(
                        request_id=request.id,
                        upload=productive_business_proof,
                        document_type=VehicleOwnershipDocumentType.PRODUCTIVE_BUSINESS_PROOF,
                        storage_dir=storage_dir,
                    )
                )
            await self.repo.add_request_documents(documents)
            await self.repo.commit()
        except HTTPException:
            await self.repo.rollback()
            self._cleanup_storage_dir(storage_dir)
            raise
        except Exception:
            await self.repo.rollback()
            self._cleanup_storage_dir(storage_dir)
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
        if usage_type in {VehicleUsageType.OJOL, VehicleUsageType.UMKM} and productive_business_proof is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Productive business proof is required for OJOL and UMKM vehicles.",
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
        storage_dir: Path,
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

        storage_dir.mkdir(parents=True, exist_ok=True)
        suffix = self._guess_file_suffix(upload)
        file_name = f"{document_type.value.lower().replace('_', '-')}{suffix}"
        storage_key = f"{ownership_id}/{file_name}"
        file_path = storage_dir / file_name
        file_path.write_bytes(file_bytes)

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
        storage_dir: Path,
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

        storage_dir.mkdir(parents=True, exist_ok=True)
        suffix = self._guess_file_suffix(upload)
        file_name = f"{document_type.value.lower().replace('_', '-')}{suffix}"
        storage_key = f"{request_id}/{file_name}"
        file_path = storage_dir / file_name
        file_path.write_bytes(file_bytes)

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
        final_storage_dir: Path,
    ) -> VehicleOwnershipDocument:
        source_file_path = self.REQUEST_STORAGE_ROOT / request_document.storage_key
        if not source_file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stored vehicle ownership request document file not found during approval.",
            )

        file_name = source_file_path.name
        target_storage_key = f"{ownership_id}/{file_name}"
        target_file_path = final_storage_dir / file_name
        shutil.copy2(source_file_path, target_file_path)

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

    def _cleanup_storage_dir(self, storage_dir: Path | None) -> None:
        if storage_dir and storage_dir.exists():
            shutil.rmtree(storage_dir, ignore_errors=True)

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
            VehicleUsageType.OJOL,
            VehicleUsageType.UMKM,
            VehicleUsageType.COMPANY_OPERATIONAL,
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

        personal_policy = await self.repo.get_subsidy_policy_by_usage_type(VehicleUsageType.PERSONAL)
        if personal_policy is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subsidy policy for PERSONAL usage type not found.",
            )

        buyer_profiles = await self.repo.get_buyer_profiles_by_kk_id(buyer_profile.kk_id)
        owner_ids = [profile.id for profile in buyer_profiles]
        ownerships = await self.repo.get_vehicle_ownerships_by_owner_ids(owner_ids)

        unique_vehicle_ids: set[UUID] = set()
        total_njkb = Decimal("0")
        for ownership in ownerships:
            if ownership.usage_type == VehicleUsageType.COMPANY_OPERATIONAL:
                continue
            if ownership.vehicle_id in unique_vehicle_ids:
                continue
            unique_vehicle_ids.add(ownership.vehicle_id)
            registry_vehicle = await self.repo.get_vehicle_registry_by_id(ownership.vehicle_id)
            if registry_vehicle is not None:
                total_njkb += Decimal(registry_vehicle.njkb)

        eligibility = await self.repo.get_latest_kk_subsidy_eligibility(
            kk_id=buyer_profile.kk_id,
            subsidy_policy_id=personal_policy.id,
        )
        if eligibility is None:
            eligibility = KKSubsidyEligibility(
                kk_id=buyer_profile.kk_id,
                subsidy_policy_id=personal_policy.id,
                total_njkb=total_njkb,
                eligibility_status=EligibilityStatus.ELIGIBLE,
            )
            await self.repo.create_kk_subsidy_eligibility(eligibility)

        is_eligible = total_njkb <= Decimal(personal_policy.max_allowed_njkb)
        eligibility.total_njkb = total_njkb
        eligibility.eligibility_status = (
            EligibilityStatus.ELIGIBLE if is_eligible else EligibilityStatus.NOT_ELIGIBLE
        )
        eligibility.eligibility_reason = (
            f"Total NJKB kendaraan unik dalam KK adalah {total_njkb}."
            if is_eligible
            else f"Total NJKB kendaraan unik dalam KK melebihi batas {personal_policy.max_allowed_njkb}."
        )
        eligibility.checked_at = self._utcnow()

    def _quota_trust_factor(self, risk_score: Decimal) -> Decimal:
        trust_factor = Decimal("1") - (risk_score / Decimal("100"))
        if trust_factor < Decimal("0"):
            return Decimal("0")
        return trust_factor

    def _is_account_suspended(self, risk_score: Decimal) -> bool:
        return risk_score > Decimal("85")
