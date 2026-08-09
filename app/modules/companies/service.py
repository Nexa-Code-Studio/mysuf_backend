import hashlib
import mimetypes
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import Company
from app.modules.companies.repository import CompanyRepository
from app.modules.companies.schemas import CompanyCreate, CompanyVerifyRequest
from app.core.storage import StorageService

# Root storage directory – absolute path anchored to the project root (4 parents up from this file)
STORAGE_ROOT = Path(__file__).resolve().parents[4] / "storage" / "companies"

MAX_FILE_NAME_LENGTH = 255
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB per document


class CompanyService:
    def __init__(self, db: AsyncSession):
        self.repo = CompanyRepository(db)
        self.storage = StorageService()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def register_company(
        self,
        data: CompanyCreate,
        siup_file: Optional[UploadFile] = None,
        tdp_file: Optional[UploadFile] = None,
        npwp_file: Optional[UploadFile] = None,
        nib_file: Optional[UploadFile] = None,
    ) -> Company:
        # Validate files before touching the database
        if siup_file and siup_file.filename:
            await self._validate_document_upload(siup_file, label="SIUP")
        if tdp_file and tdp_file.filename:
            await self._validate_document_upload(tdp_file, label="TDP")
        if npwp_file and npwp_file.filename:
            await self._validate_document_upload(npwp_file, label="NPWP")
        if nib_file and nib_file.filename:
            await self._validate_document_upload(nib_file, label="NIB")

        company = Company(
            name=data.name,
            nib=data.nib,
            email=data.email,
            phone=data.phone,
            fleet_size=data.fleet_size,
            siup_no=data.siup_no,
            tdp_no=data.tdp_no,
            npwp_no=data.npwp_no,
            notes=data.notes,
            status="Belum Verifikasi",
        )

        uploaded_keys: list[str] = []
        try:
            await self.repo.create_company(company)

            company.siup_doc = await self._save_document(siup_file, "siup", company.id, uploaded_keys)
            company.tdp_doc = await self._save_document(tdp_file, "tdp", company.id, uploaded_keys)
            company.npwp_doc = await self._save_document(npwp_file, "npwp", company.id, uploaded_keys)
            company.nib_doc = await self._save_document(nib_file, "nib", company.id, uploaded_keys)

            await self.repo.commit()
        except HTTPException:
            await self.repo.rollback()
            self._cleanup_uploaded_keys(uploaded_keys)
            raise
        except Exception:
            await self.repo.rollback()
            self._cleanup_uploaded_keys(uploaded_keys)
            raise

        saved = await self.repo.get_company(company.id)
        if not saved:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Company was created but could not be reloaded.",
            )
        return saved

    async def get_all_companies(self) -> List[Company]:
        return await self.repo.get_companies()

    async def verify_company(self, company_id: UUID, req: CompanyVerifyRequest) -> Company:
        company = await self.repo.get_company(company_id)
        if not company:
            raise ValueError("Perusahaan tidak ditemukan")

        company.status = req.status
        if req.notes:
            company.notes = req.notes

        return await self.repo.update_company(company)

    def get_document_file_path(self, company_id: str, filename: str) -> Path:
        """Resolve the absolute path for a stored company document."""
        return STORAGE_ROOT / company_id / filename

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _save_document(
        self,
        upload: Optional[UploadFile],
        label: str,
        company_id,
        uploaded_keys: list[str],
    ) -> Optional[str]:
        """Save an uploaded file to storage and return a storage_key (relative path)."""
        if not upload or not upload.filename:
            return None

        file_bytes = await upload.read()
        if not file_bytes:
            return None

        if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File {label.upper()} melebihi batas ukuran 10 MB.",
            )

        suffix = self._guess_file_suffix(upload)
        file_name = f"{label}{suffix}"
        storage_key = f"companies/{company_id}/{file_name}"
        
        self.storage.save_file(storage_key, file_bytes, upload.content_type)
        uploaded_keys.append(storage_key)

        # storage_key returned to DB matches the legacy "company_id/filename" pattern to stay backward compatible
        return f"{company_id}/{file_name}"

    async def _validate_document_upload(self, upload: UploadFile, label: str) -> None:
        if not upload.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Nama file {label} wajib ada.",
            )
        if len(upload.filename) > MAX_FILE_NAME_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Nama file {label} terlalu panjang.",
            )
        content_type = upload.content_type or ""
        allowed = content_type.startswith("image/") or content_type == "application/pdf"
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File {label} harus berupa gambar (JPG/PNG) atau PDF.",
            )

    def _guess_file_suffix(self, upload: UploadFile) -> str:
        original_suffix = Path(upload.filename or "").suffix.lower()
        if original_suffix:
            return original_suffix
        guessed = mimetypes.guess_extension(upload.content_type or "")
        if guessed:
            return guessed
        return ".bin"

    def _cleanup_uploaded_keys(self, uploaded_keys: list[str]) -> None:
        for key in uploaded_keys:
            try:
                self.storage.delete_file(key)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to delete {key} during cleanup: {e}")
