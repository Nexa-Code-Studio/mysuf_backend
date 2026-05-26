from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, ConfigDict
from uuid import UUID

class CompanyBase(BaseModel):
    name: str
    nib: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    fleet_size: Optional[int] = None
    siup_no: Optional[str] = None
    tdp_no: Optional[str] = None
    npwp_no: Optional[str] = None
    notes: Optional[str] = None
    status: str = "Belum Verifikasi"
    siup_doc: Optional[str] = None
    tdp_doc: Optional[str] = None
    npwp_doc: Optional[str] = None
    nib_doc: Optional[str] = None

class CompanyCreate(BaseModel):
    name: str
    nib: str
    email: EmailStr
    phone: str
    fleet_size: int
    siup_no: Optional[str] = None
    tdp_no: Optional[str] = None
    npwp_no: Optional[str] = None
    notes: Optional[str] = None

class CompanyVerifyRequest(BaseModel):
    status: str  # "Approved" or "Rejected"
    notes: Optional[str] = None

class CompanyResponse(CompanyBase):
    id: UUID
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)
