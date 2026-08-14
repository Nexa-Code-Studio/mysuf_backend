import json
import shutil
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.modules.buyer_registrations.models import (
    BuyerDocumentType,
    BuyerProfileDocument,
    BuyerRegistrationAttempt,
    BuyerRegistrationDocument,
    BuyerRegistrationStatus,
)
from app.modules.buyer_registrations.service import BuyerRegistrationService
from app.modules.buyer_registrations.verification_service import VerificationService
from app.modules.registries.models import CitizenRegistryMockup, KK
from app.modules.users.models import BuyerProfile, User


def _quality_result(errors: list[str]):
    return SimpleNamespace(
        errors=errors,
        to_dict=lambda: {
            "errors": errors,
            "blurry": False,
            "brightness_ok": True,
            "resolution_ok": True,
            "glare_detected": False,
            "brightness": 120.0,
            "variance_of_laplacian": 180.0,
            "width": 1280,
            "height": 720,
        },
    )


@pytest.mark.anyio
async def test_verification_service_completes_attempt(monkeypatch):
    kk_id = uuid4()
    citizen_id = uuid4()
    attempt_id = None
    citizen_nik = f"320101{str(uuid4().int)[-10:]}"
    citizen_nfc = f"VERIFY-NFC-{uuid4().hex[:12]}"

    monkeypatch.setattr(
        "app.modules.buyer_registrations.image_utils.ImageUtils.load_cv2_image",
        lambda _: object(),
    )
    monkeypatch.setattr(
        "app.modules.buyer_registrations.image_utils.ImageUtils.load_cv2_image_from_bytes",
        lambda _: object(),
    )
    monkeypatch.setattr(
        "app.modules.buyer_registrations.image_utils.ImageUtils.perspective_correct_ktp",
        lambda image: image,
    )
    monkeypatch.setattr(
        "app.modules.buyer_registrations.image_utils.ImageUtils.crop_ktp_portrait",
        lambda image: image,
    )

    async with AsyncSessionLocal() as session:
        kk = KK(id=kk_id, code=f"VERIFY-KK-{uuid4().hex[:8]}")
        citizen = CitizenRegistryMockup(
            id=citizen_id,
            nik=citizen_nik,
            nama="Verifikasi Sukses",
            ktp_nfc_id=citizen_nfc,
            kk_id=kk_id,
        )
        attempt = BuyerRegistrationAttempt(
            id=uuid4(),
            nik_input=citizen.nik,
            email=f"verify_success_{uuid4()}@example.com",
            password_hash="hashed-password",
            ocr_raw_text=f"NIK {citizen_nik}\nNama {citizen.nama}",
            status=BuyerRegistrationStatus.PENDING,
        )
        attempt_id = attempt.id
        documents = [
            BuyerRegistrationDocument(
                registration_attempt_id=attempt_id,
                document_type=document_type,
                storage_key=f"{attempt_id}/{file_name}",
                original_filename=file_name,
                mime_type="image/jpeg",
                file_size_bytes=1024,
                checksum_sha256=f"sha-{file_name}",
            )
            for document_type, file_name in [
                (BuyerDocumentType.KTP_PHOTO, "ktp-photo.jpg"),
                (BuyerDocumentType.SELFIE_PHOTO, "selfie-photo.jpg"),
            ]
        ]
        session.add_all([kk, citizen, attempt, *documents])
        await session.commit()

        from app.core.storage import StorageService
        storage = StorageService()
        for doc in documents:
            storage.save_file(doc.storage_key, b"fake-image-bytes", doc.mime_type)

    try:
        async with AsyncSessionLocal() as session:
            service = VerificationService(session)
            service.quality_service.check_ktp_image = lambda _: _quality_result([])
            service.quality_service.check_selfie_image = lambda _: _quality_result([])
            service.ocr_service.extract_nik = lambda _: SimpleNamespace(
                raw_text=f"NIK {citizen.nik}",
                nik=citizen.nik,
                nik_valid=True,
            )
            service.face_service.compare_portrait_and_selfie = lambda *_: SimpleNamespace(
                match=True,
                similarity=0.93,
                threshold=0.55,
                error=None,
            )
            await service.process_attempt(str(attempt_id))

        async with AsyncSessionLocal() as session:
            attempt = await session.get(BuyerRegistrationAttempt, attempt_id)
            assert attempt.status == BuyerRegistrationStatus.COMPLETED
            assert attempt.nik_ocr == citizen.nik
            assert attempt.is_nik_match is True
            assert float(attempt.face_match_score) == pytest.approx(0.93)
            assert attempt.is_face_match is True
            assert attempt.registry_name_snapshot == citizen.nama
            detail = json.loads(attempt.verification_detail)
            assert detail["ktp_quality"]["errors"] == []
            user = await session.get(User, attempt.created_user_id)
            profile = await session.get(BuyerProfile, attempt.created_buyer_profile_id)
            assert user is not None
            assert user.name == citizen.nama
            assert profile is not None
            profile_documents = await session.execute(
                select(BuyerProfileDocument).where(BuyerProfileDocument.buyer_profile_id == profile.id)
            )
            assert len(profile_documents.scalars().all()) == 2
    finally:
        if attempt_id:
            async with AsyncSessionLocal() as session:
                attempt = await session.get(BuyerRegistrationAttempt, attempt_id)
                if attempt and attempt.created_buyer_profile_id:
                    await session.execute(
                        delete(BuyerProfileDocument).where(BuyerProfileDocument.buyer_profile_id == attempt.created_buyer_profile_id)
                    )
                await session.execute(
                    delete(BuyerRegistrationDocument).where(BuyerRegistrationDocument.registration_attempt_id == attempt_id)
                )
                await session.execute(delete(BuyerRegistrationAttempt).where(BuyerRegistrationAttempt.id == attempt_id))
                if attempt and attempt.created_buyer_profile_id:
                    await session.execute(delete(BuyerProfile).where(BuyerProfile.id == attempt.created_buyer_profile_id))
                if attempt and attempt.created_user_id:
                    await session.execute(delete(User).where(User.id == attempt.created_user_id))
                await session.execute(delete(CitizenRegistryMockup).where(CitizenRegistryMockup.id == citizen_id))
                await session.execute(delete(KK).where(KK.id == kk_id))
                await session.commit()
            shutil.rmtree(BuyerRegistrationService.STORAGE_ROOT / str(attempt_id), ignore_errors=True)


@pytest.mark.anyio
async def test_verification_service_fails_on_nik_mismatch(monkeypatch):
    kk_id = uuid4()
    citizen_id = uuid4()
    attempt_id = None
    citizen_nik = f"320101{str(uuid4().int)[-10:]}"
    citizen_nfc = f"VERIFY-NFC-{uuid4().hex[:12]}"

    monkeypatch.setattr(
        "app.modules.buyer_registrations.image_utils.ImageUtils.load_cv2_image",
        lambda _: object(),
    )
    monkeypatch.setattr(
        "app.modules.buyer_registrations.image_utils.ImageUtils.load_cv2_image_from_bytes",
        lambda _: object(),
    )
    monkeypatch.setattr(
        "app.modules.buyer_registrations.image_utils.ImageUtils.perspective_correct_ktp",
        lambda image: image,
    )

    async with AsyncSessionLocal() as session:
        kk = KK(id=kk_id, code=f"VERIFY-KK-{uuid4().hex[:8]}")
        citizen = CitizenRegistryMockup(
            id=citizen_id,
            nik=citizen_nik,
            nama="Verifikasi Gagal",
            ktp_nfc_id=citizen_nfc,
            kk_id=kk_id,
        )
        attempt = BuyerRegistrationAttempt(
            id=uuid4(),
            nik_input=citizen.nik,
            email=f"verify_fail_{uuid4()}@example.com",
            password_hash="hashed-password",
            ocr_raw_text=f"NIK 3201010101019999\nNama {citizen.nama}",
            status=BuyerRegistrationStatus.PENDING,
        )
        attempt_id = attempt.id
        documents = [
            BuyerRegistrationDocument(
                registration_attempt_id=attempt_id,
                document_type=document_type,
                storage_key=f"{attempt_id}/{file_name}",
                original_filename=file_name,
                mime_type="image/jpeg",
                file_size_bytes=1024,
                checksum_sha256=f"sha-{file_name}",
            )
            for document_type, file_name in [
                (BuyerDocumentType.KTP_PHOTO, "ktp-photo.jpg"),
                (BuyerDocumentType.SELFIE_PHOTO, "selfie-photo.jpg"),
            ]
        ]
        session.add_all([kk, citizen, attempt, *documents])
        await session.commit()

        from app.core.storage import StorageService
        storage = StorageService()
        for doc in documents:
            storage.save_file(doc.storage_key, b"fake-image-bytes", doc.mime_type)

    try:
        async with AsyncSessionLocal() as session:
            service = VerificationService(session)
            service.quality_service.check_ktp_image = lambda _: _quality_result([])
            service.quality_service.check_selfie_image = lambda _: _quality_result([])
            service.ocr_service.extract_nik = lambda _: SimpleNamespace(
                raw_text="NIK 3201010101019999",
                nik="3201010101019999",
                nik_valid=True,
            )
            await service.process_attempt(str(attempt_id))

        async with AsyncSessionLocal() as session:
            attempt = await session.get(BuyerRegistrationAttempt, attempt_id)
            assert attempt.status == BuyerRegistrationStatus.FAILED
            assert attempt.failure_reason == "NIK_OCR_MISMATCH"
            assert attempt.created_user_id is None
            assert attempt.created_buyer_profile_id is None
    finally:
        if attempt_id:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    delete(BuyerRegistrationDocument).where(BuyerRegistrationDocument.registration_attempt_id == attempt_id)
                )
                await session.execute(delete(BuyerRegistrationAttempt).where(BuyerRegistrationAttempt.id == attempt_id))
                await session.execute(delete(CitizenRegistryMockup).where(CitizenRegistryMockup.id == citizen_id))
                await session.execute(delete(KK).where(KK.id == kk_id))
                await session.commit()
