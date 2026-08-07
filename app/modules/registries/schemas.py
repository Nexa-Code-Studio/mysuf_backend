from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict

# ----------------------------------------------------
# Pagination Schemas
# ----------------------------------------------------
class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int

# ----------------------------------------------------
# KK (Kartu Keluarga) Schemas
# ----------------------------------------------------
class KKBase(BaseModel):
    code: str

class KKCreate(KKBase):
    pass

class KKUpdate(BaseModel):
    code: Optional[str] = None

class KKResponse(KKBase):
    id: UUID

    model_config = ConfigDict(from_attributes=True)

class KKListResponse(BaseModel):
    items: List[KKResponse]
    pagination: PaginationMeta

# ----------------------------------------------------
# CitizenRegistryMockup Schemas
# ----------------------------------------------------
class CitizenBase(BaseModel):
    nik: str
    nama: str
    ktp_nfc_id: str
    kk_id: UUID
    pekerjaan: Optional[str] = None
    penghasilan: Optional[Decimal] = None

class CitizenCreate(CitizenBase):
    pass

class CitizenUpdate(BaseModel):
    nik: Optional[str] = None
    nama: Optional[str] = None
    ktp_nfc_id: Optional[str] = None
    kk_id: Optional[UUID] = None
    pekerjaan: Optional[str] = None
    penghasilan: Optional[Decimal] = None

class CitizenResponse(CitizenBase):
    id: UUID

    model_config = ConfigDict(from_attributes=True)

class CitizenListResponse(BaseModel):
    items: List[CitizenResponse]
    pagination: PaginationMeta

