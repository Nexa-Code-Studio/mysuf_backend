from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.modules.buyer_registrations.face_service import FaceService
from app.modules.buyer_registrations.image_utils import ImageUtils
from app.modules.buyer_registrations.models import (
    BuyerDocumentType,
    BuyerProfileDocument,
    BuyerRegistrationAttempt,
    BuyerRegistrationStatus,
)
from app.modules.buyer_registrations.model_store import get_model_store
from app.modules.buyer_registrations.ocr_service import OCRService
from app.modules.buyer_registrations.quality_service import QualityService
from app.modules.buyer_registrations.repository import BuyerRegistrationRepository
from app.modules.registries.models import CitizenRegistryMockup
from app.modules.users.models import BuyerProfile, User, UserRole, VerificationStatus
from app.core.storage import StorageService


@dataclass
class VerificationFailure(Exception):
    reason: str
    detail: str


class VerificationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = BuyerRegistrationRepository(db)
        self.quality_service = QualityService()
        self.ocr_service = OCRService(get_model_store())
        self.face_service = FaceService(get_model_store())
        self.storage = StorageService()

    async def process_attempt(self, attempt_id: str) -> None:
        attempt = await self.repo.get_attempt_by_id(attempt_id)
        if not attempt:
            return

        attempt.status = BuyerRegistrationStatus.PROCESSING
        attempt.verification_started_at = datetime.utcnow()
        await self.repo.commit()

        try:
            await self._verify_attempt(attempt)
            print("\n" + "=" * 60)
            print(f" [BACKEND LOG] VERIFIKASI SELESAI & SUKSES (Attempt: {attempt.id})")
            print("=" * 60)
            print(f"NIK Inputan Warga : {attempt.nik_input}")
            print(f"Nama Registri DB  : {attempt.registry_name_snapshot}")
            print("=" * 60 + "\n")
        except VerificationFailure as failure:
            print("\n" + "=" * 60)
            print(f" [BACKEND LOG] VERIFIKASI GAGAL (Attempt: {attempt.id})")
            print("=" * 60)
            print(f"NIK Inputan Warga : {attempt.nik_input}")
            print(f"NIK Hasil OCR BE  : {attempt.nik_ocr}")
            print(f"Alasan Kegagalan  : {failure.reason}")
            print(f"Detail Kegagalan  : {failure.detail}")
            print(f"\nTeks Mentah OCR KTP BE:\n{attempt.ocr_raw_text}")
            print("=" * 60 + "\n")
            await self._mark_failed(attempt, failure.reason, failure.detail)
        except Exception as exc:
            import traceback
            print("\n" + "=" * 60)
            print(f" [BACKEND LOG] VERIFIKASI ERROR SYSTEM (Attempt: {attempt.id})")
            print("=" * 60)
            print(f"Error Message     : {str(exc)}")
            traceback.print_exc()
            print("=" * 60 + "\n")
            await self._mark_failed(attempt, "VERIFICATION_INTERNAL_ERROR", str(exc))

    async def _verify_attempt(self, attempt: BuyerRegistrationAttempt) -> None:
        ktp_document = self.repo.get_document_by_type(attempt, BuyerDocumentType.KTP_PHOTO)
        selfie_document = self.repo.get_document_by_type(attempt, BuyerDocumentType.SELFIE_PHOTO)
        if not ktp_document or not selfie_document:
            raise VerificationFailure("VERIFICATION_INTERNAL_ERROR", "Registration documents are incomplete.")

        ktp_bytes, _ = self.storage.get_file(ktp_document.storage_key)
        selfie_bytes, _ = self.storage.get_file(selfie_document.storage_key)

        ktp_image = await asyncio.to_thread(
            ImageUtils.load_cv2_image_from_bytes,
            ktp_bytes,
        )
        selfie_image = await asyncio.to_thread(
            ImageUtils.load_cv2_image_from_bytes,
            selfie_bytes,
        )

        ktp_quality = await asyncio.to_thread(self.quality_service.check_ktp_image, ktp_image)
        selfie_quality = await asyncio.to_thread(self.quality_service.check_selfie_image, selfie_image)
        attempt.verification_detail = json.dumps(
            {
                "ktp_quality": ktp_quality.to_dict(),
                "selfie_quality": selfie_quality.to_dict(),
            }
        )
        await self.repo.commit()

        quality_errors = [*ktp_quality.errors, *selfie_quality.errors]
        if quality_errors:
            raise VerificationFailure(quality_errors[0], json.dumps({"errors": quality_errors}))

        ktp_rectified = await asyncio.to_thread(ImageUtils.perspective_correct_ktp, ktp_image)
        
        # Skip backend PaddleOCR and directly use the frontend-supplied OCR text
        if not attempt.ocr_raw_text:
            raise VerificationFailure("NIK_OCR_NOT_FOUND", "Teks OCR tidak terdeteksi dari frontend.")

        ocr_nik = self.ocr_service.extract_nik_from_text(attempt.ocr_raw_text)
        attempt.nik_ocr = ocr_nik
        attempt.is_nik_match = (ocr_nik == attempt.nik_input)

        if not attempt.is_nik_match:
            raise VerificationFailure("NIK_OCR_MISMATCH", "NIK on KTP does not match the inputted NIK.")

        citizen = await self.repo.get_citizen_by_nik(attempt.nik_input)
        if not citizen:
            raise VerificationFailure("NIK_NOT_FOUND", "NIK was not found in citizen registry mockup.")

        # Log OCR Results (Bypassed but showing Frontend ML Kit data) directly to the backend terminal
        print("\n" + "=" * 60)
        print(f" [BACKEND LOG] OCR VERIFIKASI KTP (Attempt: {attempt.id})")
        print("=" * 60)
        print(f"NIK Inputan Warga : {attempt.nik_input}")
        print(f"NIK Registri DB   : {citizen.nik} (COCOK)")
        print(f"Status NIK Cocok  : {attempt.is_nik_match} (Bypassed Backend OCR - Google ML Kit Frontend)")
        print(f"\nTEKS MENTAH HASIL BACAAN OCR KTP DARI FRONTEND:\n{attempt.ocr_raw_text}")
        print("=" * 60 + "\n")

        attempt.registry_citizen_id = citizen.id
        attempt.registry_name_snapshot = citizen.nama
        attempt.registry_kk_id_snapshot = citizen.kk_id
        attempt.registry_ktp_nfc_id_snapshot = citizen.ktp_nfc_id
        await self.repo.commit()

        # Fuzzy match the official registry name against the raw KTP OCR text
        from rapidfuzz import fuzz

        registry_name = citizen.nama.strip().upper()
        ocr_text = (attempt.ocr_raw_text or "").strip().upper()

        # We use partial_ratio because the registry name is a substring of the full OCR text
        name_match_score = fuzz.partial_ratio(registry_name, ocr_text)

        print("\n" + "=" * 60)
        print(" [BACKEND LOG] FUZZY NAME MATCHING (VALIDASI NAMA KTP)")
        print("=" * 60)
        print(f"Nama Registri Database : {registry_name}")
        print(f"Skor Kesamaan Nama     : {name_match_score:.2f}% (Threshold Lolos: 75.00%)")
        print(f"Hasil Validasi Nama    : {'COCOK (PASSED)' if name_match_score >= 75.0 else 'TIDAK COCOK (FAILED)'}")
        print("=" * 60 + "\n")

        if name_match_score < 75.0:
            print(f"ERROR: Validasi nama gagal! Skor {name_match_score:.2f}% di bawah batas 75.00%")
            # We raise KTP_CARD_NOT_CLEAR as a generic error to keep it secret from the user
            raise VerificationFailure(
                "KTP_CARD_NOT_CLEAR",
                f"Nama pada KTP tidak cocok dengan data registri kependudukan (Fuzzy Score: {name_match_score:.2f}%)."
            )

        ktp_portrait = await asyncio.to_thread(ImageUtils.crop_ktp_portrait, ktp_rectified)
        face_result = await asyncio.to_thread(
            self.face_service.compare_portrait_and_selfie,
            ktp_portrait,
            selfie_image,
        )
        attempt.face_match_score = face_result.similarity
        attempt.is_face_match = face_result.match
        await self.repo.commit()

        # Log Face Comparison Results directly to the backend terminal
        print("\n" + "=" * 60)
        print(f" [BACKEND LOG] PENCOCOKAN WAJAH / FACE MATCHING")
        print("=" * 60)
        print(f"Skor Kemiripan Wajah: {face_result.similarity}")
        print(f"Batas Lolos (Threshold): {face_result.threshold}")
        print(f"Hasil Pencocokan    : {'COCOK (PASSED)' if face_result.match else 'TIDAK COCOK (FAILED)'}")
        if face_result.error:
            print(f"Error Detail        : {face_result.error}")
        print("=" * 60 + "\n")

        if face_result.error:
            detail = (
                f"Face comparison failed with similarity {face_result.similarity} and threshold {face_result.threshold}."
                if face_result.similarity is not None
                else "Face comparison could not be completed."
            )
            raise VerificationFailure(face_result.error, detail)

        await self._finalize_success(attempt, citizen)

    async def _finalize_success(self, attempt: BuyerRegistrationAttempt, citizen: CitizenRegistryMockup) -> None:
        user = User(
            email=attempt.email,
            name=citizen.nama,
            password=attempt.password_hash,
            role=[UserRole.BUYER],
            is_active=True,
        )
        await self.repo.create_user(user)

        buyer_profile = BuyerProfile(
            nik_snapshot=attempt.nik_input,
            ktp_nfc_id_snapshot=citizen.ktp_nfc_id,
            kk_id=citizen.kk_id,
            user_id=user.id,
            verification_status=VerificationStatus.VERIFIED,
        )
        await self.repo.create_buyer_profile(buyer_profile)

        profile_documents = []
        for document in attempt.documents:
            profile_documents.append(
                BuyerProfileDocument(
                    buyer_profile_id=buyer_profile.id,
                    document_type=document.document_type,
                    storage_key=document.storage_key,
                    original_filename=document.original_filename,
                    mime_type=document.mime_type,
                    file_size_bytes=document.file_size_bytes,
                    checksum_sha256=document.checksum_sha256,
                    source_registration_document_id=document.id,
                )
            )
        await self.repo.create_buyer_profile_documents(profile_documents)

        attempt.created_user_id = user.id
        attempt.created_buyer_profile_id = buyer_profile.id
        attempt.status = BuyerRegistrationStatus.COMPLETED
        attempt.verified_at = datetime.utcnow()
        attempt.completed_at = datetime.utcnow()
        attempt.failure_reason = None
        attempt.failure_detail = None
        await self.repo.commit()

    async def _mark_failed(self, attempt: BuyerRegistrationAttempt, reason: str, detail: str) -> None:
        attempt.status = BuyerRegistrationStatus.FAILED
        attempt.failure_reason = reason
        attempt.failure_detail = detail
        await self.repo.commit()


async def run_attempt_verification(attempt_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await VerificationService(session).process_attempt(attempt_id)
