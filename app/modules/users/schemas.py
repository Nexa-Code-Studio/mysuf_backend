from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional
from pydantic import BaseModel, EmailStr, ConfigDict
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
    shift: Optional[str] = None

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
    shift: Optional[str] = None

class UserResponse(UserBase):
    id: UUID

    model_config = ConfigDict(from_attributes=True)

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
    risk_score: Decimal
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)

class BuyerProfileCheckResponse(BaseModel):
    has_buyer_profile: bool
    buyer_profile_id: Optional[UUID] = None
    verification_status: Optional[str] = None

class UserProfileResponse(BaseModel):
    name: str
    nikMasked: str
    isVerified: bool
    isEligible: bool
    familyCardNumber: str
    vehiclesCount: int
    quotaRemaining: int
    walletBalance: int
    isPinActive: bool = False

class UserPinUpdate(BaseModel):
    pin: str
    old_pin: Optional[str] = None


class HomeVehicleVerificationResponse(BaseModel):
    has_verified_vehicle: bool
    show_verify_vehicle_cta: bool
    cta_route: str


class HomePersonalQuotaResponse(BaseModel):
    month: int
    year: int
    quota_liters: float
    used_liters: float
    remaining_liters: float


class HomeNearbyGasStationItemResponse(BaseModel):
    id: UUID
    name: str
    latitude: float
    longitude: float
    distance_km: float


class HomeNearbyGasStationsResponse(BaseModel):
    location_available: bool
    message: str | None = None
    items: List[HomeNearbyGasStationItemResponse]


class HomeRecentTransactionFuelResponse(BaseModel):
    fuel_type_name: str
    gas_station_name: str
    liters: float


class HomeRecentTransactionResponse(BaseModel):
    id: str
    tile_type: Literal["FUEL", "TOP_UP", "TRANSFER"]
    title: str
    subtitle: str
    amount: float
    transaction_flow: str
    status: str
    occurred_at: datetime
    fuel: HomeRecentTransactionFuelResponse | None = None


class HomeRiskStatusResponse(BaseModel):
    verification_status: VerificationStatus
    risk_score: float


class BuyerHomeResponse(BaseModel):
    vehicle_verification: HomeVehicleVerificationResponse
    personal_quota: Optional[HomePersonalQuotaResponse] = None
    nearby_gas_stations: HomeNearbyGasStationsResponse
    recent_transactions: List[HomeRecentTransactionResponse]
    risk_status: HomeRiskStatusResponse


class SubsidizedFuelResponse(BaseModel):
    id: UUID
    name: str
    price_per_liter: float
    subsidy_price_per_liter: Optional[float] = None


class VehicleQuotaDetailResponse(BaseModel):
    id: UUID
    plate_number: str
    brand: str
    total_liters_purchased: float


class BuyerQuotaResponse(BaseModel):
    personal_quota: Optional[HomePersonalQuotaResponse] = None
    subsidized_fuels: List[SubsidizedFuelResponse]
    vehicles: List[VehicleQuotaDetailResponse]


class UserDeviceTokenUpdate(BaseModel):
    token: str
