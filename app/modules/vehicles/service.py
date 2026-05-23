import hashlib
import mimetypes
import shutil
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User
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
