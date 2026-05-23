import hashlib
import mimetypes
import shutil
from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.modules.buyer_registrations.models import BuyerDocumentType, BuyerRegistrationAttempt, BuyerRegistrationDocument, BuyerRegistrationStatus
from app.modules.buyer_registrations.repository import BuyerRegistrationRepository
from app.modules.buyer_registrations.schemas import BuyerRegistrationAttemptCreate


class BuyerRegistrationService:
    STORAGE_ROOT = Path(__file__).resolve().parents[3] / "storage" / "buyer-registrations"
    MAX_FILE_NAME_LENGTH = 255
    MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024

    def __init__(self, db: AsyncSession):
        self.repo = BuyerRegistrationRepository(db)

    async def submit_attempt(
        self,
        registration_in: BuyerRegistrationAttemptCreate,
        ktp_photo: UploadFile,
        selfie_photo: UploadFile,
    ) -> BuyerRegistrationAttempt:
        await self._validate_new_attempt(registration_in=registration_in)
        await self._validate_image_upload(ktp_photo, label="KTP photo")
        await self._validate_image_upload(selfie_photo, label="selfie photo")

        attempt = BuyerRegistrationAttempt(
            nik_input=registration_in.nik_input,
            email=registration_in.email,
            password_hash=get_password_hash(registration_in.password),
            status=BuyerRegistrationStatus.PENDING,
            ocr_raw_text=registration_in.ocr_raw_text,
        )

        attempt_storage_dir: Path | None = None
        try:
            await self.repo.create_attempt(attempt)
            attempt_storage_dir = self.STORAGE_ROOT / str(attempt.id)
            ktp_document = await self._build_document(
                attempt_id=attempt.id,
                upload=ktp_photo,
                document_type=BuyerDocumentType.KTP_PHOTO,
                storage_dir=attempt_storage_dir,
            )
            selfie_document = await self._build_document(
                attempt_id=attempt.id,
                upload=selfie_photo,
                document_type=BuyerDocumentType.SELFIE_PHOTO,
                storage_dir=attempt_storage_dir,
            )

            await self.repo.add_documents([ktp_document, selfie_document])
            await self.repo.commit()
        except HTTPException:
            await self.repo.rollback()
            self._cleanup_storage_dir(attempt_storage_dir)
            raise
        except IntegrityError:
            await self.repo.rollback()
            self._cleanup_storage_dir(attempt_storage_dir)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An active buyer registration attempt already exists for this email or NIK.",
            )
        except Exception:
            await self.repo.rollback()
            self._cleanup_storage_dir(attempt_storage_dir)
            raise

        saved_attempt = await self.repo.get_attempt_by_id(str(attempt.id))
        if not saved_attempt:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Buyer registration attempt was created but could not be reloaded.",
            )
        return saved_attempt

    async def get_attempt_status(self, attempt_id: str) -> BuyerRegistrationAttempt:
        attempt = await self.repo.get_attempt_by_id(attempt_id)
        if not attempt:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Buyer registration attempt not found.",
            )
        return attempt

    async def _validate_new_attempt(self, registration_in: BuyerRegistrationAttemptCreate) -> None:
        existing_user = await self.repo.get_user_by_email(registration_in.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The user with this email already exists in the system.",
            )

        existing_attempt_by_email = await self.repo.get_active_attempt_by_email(registration_in.email)
        if existing_attempt_by_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An active buyer registration attempt already exists for this email.",
            )

        existing_attempt_by_nik = await self.repo.get_active_attempt_by_nik(registration_in.nik_input)
        if existing_attempt_by_nik:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An active buyer registration attempt already exists for this NIK.",
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

    async def _build_document(
        self,
        attempt_id: UUID,
        upload: UploadFile,
        document_type: BuyerDocumentType,
        storage_dir: Path,
    ) -> BuyerRegistrationDocument:
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
        file_basename = "ktp-photo" if document_type == BuyerDocumentType.KTP_PHOTO else "selfie-photo"
        file_name = f"{file_basename}{suffix}"
        storage_key = f"{attempt_id}/{file_name}"
        file_path = storage_dir / file_name
        file_path.write_bytes(file_bytes)

        return BuyerRegistrationDocument(
            registration_attempt_id=attempt_id,
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
