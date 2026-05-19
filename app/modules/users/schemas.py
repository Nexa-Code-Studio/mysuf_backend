from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr
from uuid import UUID

from app.modules.users.models import UserRole, VerificationStatus

class UserBase(BaseModel):
    name: str
    email: EmailStr
    role: List[UserRole] = [UserRole.BUYER]
    is_active: bool = True
    employee_id: Optional[str] = None
    gas_station_id: Optional[UUID] = None
    company_id: Optional[UUID] = None

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    role: Optional[List[UserRole]] = None
    is_active: Optional[bool] = None
    employee_id: Optional[str] = None
    gas_station_id: Optional[UUID] = None
    company_id: Optional[UUID] = None

class UserResponse(UserBase):
    id: UUID

    class Config:
        from_attributes = True

class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int

class UserListResponse(BaseModel):
    items: List[UserResponse]
    pagination: PaginationMeta

class BuyerProfileCreate(BaseModel):
    nik_snapshot: str
    ktp_nfc_id_snapshot: str
    kk_id: UUID

class BuyerProfileUpdate(BaseModel):
    nik_snapshot: Optional[str] = None
    ktp_nfc_id_snapshot: Optional[str] = None
    kk_id: Optional[UUID] = None

class BuyerProfileResponse(BaseModel):
    id: UUID
    nik_snapshot: str
    ktp_nfc_id_snapshot: str
    kk_id: UUID
    user_id: UUID
    verification_status: VerificationStatus
    timestamp: datetime

    class Config:
        from_attributes = True

class BuyerProfileCheckResponse(BaseModel):
    has_buyer_profile: bool
    buyer_profile_id: Optional[UUID] = None
    verification_status: Optional[str] = None
