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


# Fleet Role Schemas

class FuelTrendItem(BaseModel):
    month: str
    liters: float

class FleetSummaryResponse(BaseModel):
    totalVehicles: int
    monthlyConsumption: float
    activeDrivers: int
    remainingQuotaPercent: int
    fuelConsumptionTrend: list[FuelTrendItem]

class FleetVehicleItem(BaseModel):
    id: UUID
    plate: str
    type: str
    driver: str
    driver_id: Optional[UUID] = None
    status: str
    quotaLimit: float
    quotaUsed: float
    vehicle_nfc_id: Optional[str] = None

class FleetVehicleListResponse(BaseModel):
    items: list[FleetVehicleItem]
    total: int

class FleetVehicleCreateRequest(BaseModel):
    plate: str
    vehicle_nfc_id: Optional[str] = None

class FleetVehicleAssignDriverRequest(BaseModel):
    driver_id: Optional[UUID] = None

class FleetDriverItem(BaseModel):
    id: UUID
    name: str
    email: str

class FleetLegalResponse(BaseModel):
    siup_no: Optional[str] = None
    nib: Optional[str] = None
    npwp_no: Optional[str] = None
    status: str

class FleetProfileResponse(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    fleet_size: Optional[int] = None

class FleetVehicleTransactionItem(BaseModel):
    id: UUID
    date: str
    driver: str
    fuelType: str
    liters: float
    amount: float
    station: str
    status: str

class FleetVehicleTransactionListResponse(BaseModel):
    items: list[FleetVehicleTransactionItem]
    total: int

