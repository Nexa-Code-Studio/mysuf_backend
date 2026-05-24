import shutil
from datetime import datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.main import app
from app.modules.buyer_registrations.models import BuyerRegistrationAttempt, BuyerRegistrationDocument, BuyerRegistrationStatus
from app.modules.buyer_registrations.service import BuyerRegistrationService
from app.modules.users.models import User, UserRole


@pytest.fixture(autouse=True)
def disable_background_verification(monkeypatch):
    async def _noop(_: str) -> None:
        return None

    monkeypatch.setattr(
        "app.api.v1.routes.buyer_registrations.run_attempt_verification",
        _noop,
    )


@pytest.mark.anyio
async def test_buyer_registration_attempt_flow():
    email = f"buyer_attempt_{uuid4()}@example.com"
    nik = f"320101{uuid4().hex[:10]}"
    created_attempt_id = None

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/buyer-registrations/",
                data={
                    "nik": nik,
                    "email": email,
                    "password": "password123",
                },
                files={
                    "ktp_photo": ("ktp.jpg", b"fake-ktp-image", "image/jpeg"),
                    "selfie_photo": ("selfie.jpg", b"fake-selfie-image", "image/jpeg"),
                },
            )
            assert response.status_code == 201

            payload = response.json()
            created_attempt_id = payload["id"]
            assert payload["status"] == "PENDING"
            assert payload["email"] == email
            assert payload["nik_input"] == nik
            assert payload["failure_reason"] is None

            status_response = await ac.get(f"/api/v1/buyer-registrations/{created_attempt_id}")
            assert status_response.status_code == 200
            status_payload = status_response.json()
            assert status_payload["id"] == created_attempt_id
            assert status_payload["status"] == "PENDING"
            assert status_payload["failure_reason"] is None

            duplicate_email_response = await ac.post(
                "/api/v1/buyer-registrations/",
                data={
                    "nik": f"320101{uuid4().hex[:10]}",
                    "email": email,
                    "password": "password123",
                },
                files={
                    "ktp_photo": ("ktp.jpg", b"another-ktp-image", "image/jpeg"),
                    "selfie_photo": ("selfie.jpg", b"another-selfie-image", "image/jpeg"),
                },
            )
            assert duplicate_email_response.status_code == 400
            assert duplicate_email_response.json()["detail"] == "An active buyer registration attempt already exists for this email."

        storage_dir = BuyerRegistrationService.STORAGE_ROOT / str(created_attempt_id)
        assert storage_dir.exists()
        assert sorted(path.name for path in storage_dir.iterdir()) == ["ktp-photo.jpg", "selfie-photo.jpg"]

        async with AsyncSessionLocal() as session:
            result = await session.get(BuyerRegistrationAttempt, created_attempt_id)
            assert result is not None

            await session.execute(
                delete(BuyerRegistrationDocument).where(BuyerRegistrationDocument.registration_attempt_id == created_attempt_id)
            )
            await session.execute(delete(BuyerRegistrationAttempt).where(BuyerRegistrationAttempt.id == created_attempt_id))
            await session.commit()
    finally:
        if created_attempt_id:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    delete(BuyerRegistrationDocument).where(BuyerRegistrationDocument.registration_attempt_id == created_attempt_id)
                )
                await session.execute(delete(BuyerRegistrationAttempt).where(BuyerRegistrationAttempt.id == created_attempt_id))
                await session.commit()

            shutil.rmtree(BuyerRegistrationService.STORAGE_ROOT / str(created_attempt_id), ignore_errors=True)


@pytest.mark.anyio
async def test_buyer_registration_rejects_existing_user_email():
    existing_user_id = uuid4()
    email = f"existing_buyer_{uuid4()}@example.com"
    nik = f"320101{uuid4().hex[:10]}"

    async with AsyncSessionLocal() as session:
        user = User(
            id=existing_user_id,
            name="Existing Buyer",
            email=email,
            password=get_password_hash("password123"),
            role=[UserRole.BUYER],
            is_active=True,
        )
        session.add(user)
        await session.commit()

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/buyer-registrations/",
                data={
                    "nik": nik,
                    "email": email,
                    "password": "password123",
                },
                files={
                    "ktp_photo": ("ktp.jpg", b"fake-ktp-image", "image/jpeg"),
                    "selfie_photo": ("selfie.jpg", b"fake-selfie-image", "image/jpeg"),
                },
            )
            assert response.status_code == 400
            assert response.json()["detail"] == "The user with this email already exists in the system."
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(User).where(User.id == existing_user_id))
            await session.commit()


@pytest.mark.anyio
async def test_buyer_registration_rejects_duplicate_active_nik():
    first_email = f"buyer_first_{uuid4()}@example.com"
    second_email = f"buyer_second_{uuid4()}@example.com"
    nik = f"320101{uuid4().hex[:10]}"
    created_attempt_id = None

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            first_response = await ac.post(
                "/api/v1/buyer-registrations/",
                data={
                    "nik": nik,
                    "email": first_email,
                    "password": "password123",
                },
                files={
                    "ktp_photo": ("ktp.jpg", b"fake-ktp-image", "image/jpeg"),
                    "selfie_photo": ("selfie.jpg", b"fake-selfie-image", "image/jpeg"),
                },
            )
            assert first_response.status_code == 201
            created_attempt_id = first_response.json()["id"]

            second_response = await ac.post(
                "/api/v1/buyer-registrations/",
                data={
                    "nik": nik,
                    "email": second_email,
                    "password": "password123",
                },
                files={
                    "ktp_photo": ("ktp.jpg", b"another-ktp-image", "image/jpeg"),
                    "selfie_photo": ("selfie.jpg", b"another-selfie-image", "image/jpeg"),
                },
            )
            assert second_response.status_code == 400
            assert second_response.json()["detail"] == "An active buyer registration attempt already exists for this NIK."
    finally:
        if created_attempt_id:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    delete(BuyerRegistrationDocument).where(BuyerRegistrationDocument.registration_attempt_id == created_attempt_id)
                )
                await session.execute(delete(BuyerRegistrationAttempt).where(BuyerRegistrationAttempt.id == created_attempt_id))
                await session.commit()

            shutil.rmtree(BuyerRegistrationService.STORAGE_ROOT / str(created_attempt_id), ignore_errors=True)


@pytest.mark.anyio
async def test_buyer_registration_rejects_non_image_file():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/buyer-registrations/",
            data={
                "nik": f"320101{uuid4().hex[:10]}",
                "email": f"buyer_file_{uuid4()}@example.com",
                "password": "password123",
            },
            files={
                "ktp_photo": ("ktp.txt", b"not-image", "text/plain"),
                "selfie_photo": ("selfie.jpg", b"fake-selfie-image", "image/jpeg"),
            },
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "KTP photo must be an image file."


@pytest.mark.anyio
async def test_buyer_registration_rejects_empty_image_file():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/buyer-registrations/",
            data={
                "nik": f"320101{uuid4().hex[:10]}",
                "email": f"buyer_empty_{uuid4()}@example.com",
                "password": "password123",
            },
            files={
                "ktp_photo": ("ktp.jpg", b"", "image/jpeg"),
                "selfie_photo": ("selfie.jpg", b"fake-selfie-image", "image/jpeg"),
            },
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "KTP_PHOTO file is empty."


@pytest.mark.anyio
async def test_buyer_registration_status_returns_404_for_unknown_attempt():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/buyer-registrations/{uuid4()}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Buyer registration attempt not found."


@pytest.mark.anyio
async def test_buyer_registration_status_can_complete_via_background_task(monkeypatch):
    async def _complete(attempt_id: str) -> None:
        async with AsyncSessionLocal() as session:
            attempt = await session.get(BuyerRegistrationAttempt, attempt_id)
            attempt.status = BuyerRegistrationStatus.COMPLETED
            attempt.nik_ocr = attempt.nik_input
            attempt.is_nik_match = True
            attempt.face_match_score = 0.91
            attempt.is_face_match = True
            attempt.completed_at = datetime.utcnow()
            await session.commit()

    monkeypatch.setattr(
        "app.api.v1.routes.buyer_registrations.run_attempt_verification",
        _complete,
    )

    created_attempt_id = None
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/buyer-registrations/",
                data={
                    "nik": f"320101{uuid4().hex[:10]}",
                    "email": f"buyer_completed_{uuid4()}@example.com",
                    "password": "password123",
                },
                files={
                    "ktp_photo": ("ktp.jpg", b"fake-ktp-image", "image/jpeg"),
                    "selfie_photo": ("selfie.jpg", b"fake-selfie-image", "image/jpeg"),
                },
            )
            assert response.status_code == 201
            created_attempt_id = response.json()["id"]

            status_response = await ac.get(f"/api/v1/buyer-registrations/{created_attempt_id}")
            assert status_response.status_code == 200
            payload = status_response.json()
            assert payload["status"] == "COMPLETED"
            assert payload["nik_ocr"] is not None
            assert payload["is_nik_match"] is True
            assert float(payload["face_match_score"]) == pytest.approx(0.91)
            assert payload["is_face_match"] is True
    finally:
        if created_attempt_id:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    delete(BuyerRegistrationDocument).where(BuyerRegistrationDocument.registration_attempt_id == created_attempt_id)
                )
                await session.execute(delete(BuyerRegistrationAttempt).where(BuyerRegistrationAttempt.id == created_attempt_id))
                await session.commit()
            shutil.rmtree(BuyerRegistrationService.STORAGE_ROOT / str(created_attempt_id), ignore_errors=True)


@pytest.mark.anyio
async def test_buyer_registration_status_can_fail_via_background_task(monkeypatch):
    async def _fail(attempt_id: str) -> None:
        async with AsyncSessionLocal() as session:
            attempt = await session.get(BuyerRegistrationAttempt, attempt_id)
            attempt.status = BuyerRegistrationStatus.FAILED
            attempt.failure_reason = "NIK_OCR_MISMATCH"
            attempt.failure_detail = "Input NIK does not match OCR NIK."
            await session.commit()

    monkeypatch.setattr(
        "app.api.v1.routes.buyer_registrations.run_attempt_verification",
        _fail,
    )

    created_attempt_id = None
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/buyer-registrations/",
                data={
                    "nik": f"320101{uuid4().hex[:10]}",
                    "email": f"buyer_failed_{uuid4()}@example.com",
                    "password": "password123",
                },
                files={
                    "ktp_photo": ("ktp.jpg", b"fake-ktp-image", "image/jpeg"),
                    "selfie_photo": ("selfie.jpg", b"fake-selfie-image", "image/jpeg"),
                },
            )
            assert response.status_code == 201
            created_attempt_id = response.json()["id"]

            status_response = await ac.get(f"/api/v1/buyer-registrations/{created_attempt_id}")
            assert status_response.status_code == 200
            payload = status_response.json()
            assert payload["status"] == "FAILED"
            assert payload["failure_reason"] == "NIK_OCR_MISMATCH"
            assert payload["failure_detail"] == "Input NIK does not match OCR NIK."
    finally:
        if created_attempt_id:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    delete(BuyerRegistrationDocument).where(BuyerRegistrationDocument.registration_attempt_id == created_attempt_id)
                )
                await session.execute(delete(BuyerRegistrationAttempt).where(BuyerRegistrationAttempt.id == created_attempt_id))
                await session.commit()
            shutil.rmtree(BuyerRegistrationService.STORAGE_ROOT / str(created_attempt_id), ignore_errors=True)
