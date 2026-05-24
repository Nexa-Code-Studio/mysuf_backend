from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.modules.buyer_registrations.schemas import (
    BuyerRegistrationAttemptCreate,
    BuyerRegistrationAttemptResponse,
    BuyerRegistrationAttemptStatusResponse,
)
from app.modules.buyer_registrations.service import BuyerRegistrationService
from app.modules.buyer_registrations.verification_service import run_attempt_verification

router = APIRouter()


@router.post("/", response_model=BuyerRegistrationAttemptResponse, status_code=status.HTTP_201_CREATED)
async def create_buyer_registration_attempt(
    background_tasks: BackgroundTasks,
    nik_input: str = Form(..., alias="nik"),
    email: str = Form(...),
    password: str = Form(...),
    ocr_raw_text: str | None = Form(None),
    ktp_photo: UploadFile = File(...),
    selfie_photo: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Submit a new buyer registration attempt for mysuf_warga.
    The final User and BuyerProfile are created only after verification passes.
    """
    service = BuyerRegistrationService(db)
    registration_in = BuyerRegistrationAttemptCreate(
        nik_input=nik_input,
        email=email,
        password=password,
        ocr_raw_text=ocr_raw_text,
    )
    attempt = await service.submit_attempt(
        registration_in=registration_in,
        ktp_photo=ktp_photo,
        selfie_photo=selfie_photo,
    )
    background_tasks.add_task(run_attempt_verification, str(attempt.id))
    return attempt


@router.get("/{attempt_id}", response_model=BuyerRegistrationAttemptStatusResponse)
async def read_buyer_registration_attempt(
    attempt_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Read the current status of a buyer registration attempt.
    """
    service = BuyerRegistrationService(db)
    return await service.get_attempt_status(attempt_id=attempt_id)
