from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr

from app.modules.buyer_registrations.models import BuyerRegistrationStatus


class BuyerRegistrationAttemptCreate(BaseModel):
    nik_input: str
    email: EmailStr
    password: str
    ocr_raw_text: str | None = None


class BuyerRegistrationAttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: BuyerRegistrationStatus
    email: EmailStr
    nik_input: str
    nik_ocr: str | None = None
    is_nik_match: bool | None = None
    face_match_score: Decimal | None = None
    is_face_match: bool | None = None
    ocr_raw_text: str | None = None
    verification_detail: str | None = None
    failure_reason: str | None = None
    failure_detail: str | None = None
    created_user_id: UUID | None = None
    created_buyer_profile_id: UUID | None = None
    submitted_at: datetime
    verification_started_at: datetime | None = None
    verified_at: datetime | None = None
    completed_at: datetime | None = None


class BuyerRegistrationAttemptStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: BuyerRegistrationStatus
    nik_ocr: str | None = None
    is_nik_match: bool | None = None
    face_match_score: Decimal | None = None
    is_face_match: bool | None = None
    ocr_raw_text: str | None = None
    verification_detail: str | None = None
    failure_reason: str | None = None
    failure_detail: str | None = None
    created_user_id: UUID | None = None
    created_buyer_profile_id: UUID | None = None
    submitted_at: datetime
    verification_started_at: datetime | None = None
    verified_at: datetime | None = None
    completed_at: datetime | None = None
