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
    foto_ktp: Optional[str] = None

class CitizenCreate(CitizenBase):
    pass

class CitizenUpdate(BaseModel):
    nik: Optional[str] = None
    nama: Optional[str] = None
    ktp_nfc_id: Optional[str] = None
    kk_id: Optional[UUID] = None
    pekerjaan: Optional[str] = None
    penghasilan: Optional[Decimal] = None
    foto_ktp: Optional[str] = None

class CitizenResponse(CitizenBase):
    id: UUID

    model_config = ConfigDict(from_attributes=True)

class CitizenListResponse(BaseModel):
    items: List[CitizenResponse]
    pagination: PaginationMeta


# ----------------------------------------------------
# VehicleRegistryMockup Schemas
# ----------------------------------------------------
class VehicleBase(BaseModel):
    plate_number: str
    registration_number: str
    brand: str
    vehicle_type: str
    manufacture_year: int
    color: str
    engine_capacity_cc: int
    pkb: Decimal
    njkb: Decimal
    owner_name: Optional[str] = None
    owner_nik: Optional[str] = None

class VehicleCreate(VehicleBase):
    pass

class VehicleUpdate(BaseModel):
    plate_number: Optional[str] = None
    registration_number: Optional[str] = None
    brand: Optional[str] = None
    vehicle_type: Optional[str] = None
    manufacture_year: Optional[int] = None
    color: Optional[str] = None
    engine_capacity_cc: Optional[int] = None
    pkb: Optional[Decimal] = None
    njkb: Optional[Decimal] = None
    owner_name: Optional[str] = None
    owner_nik: Optional[str] = None

class VehicleResponse(VehicleBase):
    id: UUID

    model_config = ConfigDict(from_attributes=True)

class VehicleListResponse(BaseModel):
    items: List[VehicleResponse]
    pagination: PaginationMeta

