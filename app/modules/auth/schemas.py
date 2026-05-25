from typing import List, Optional
from pydantic import BaseModel, EmailStr
from uuid import UUID

from app.modules.users.models import UserRole

class AccessContext(BaseModel):
    role: UserRole
    scope_type: str
    company_id: Optional[UUID] = None
    gas_station_id: Optional[UUID] = None
    buyer_profile_id: Optional[UUID] = None

class UserAuthResponse(BaseModel):
    id: UUID
    name: str
    email: EmailStr
    roles: List[UserRole]
    access_contexts: List[AccessContext]

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserAuthResponse
    allowed_apps: List[str]

class LoginRequest(BaseModel):
    email: str
    password: str
    client_type: str  # e.g., "ADMIN_WEB", "POS_ANDROID", "BUYER_ANDROID"


class RefreshTokenRequest(BaseModel):
    refresh_token: str
    client_type: str


class LogoutResponse(BaseModel):
    message: str
