from typing import Any
from fastapi import APIRouter, Depends, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user, get_optional_current_user, require_roles
from app.modules.users.models import User, UserRole
from app.modules.users.schemas import (
    UserCreate, UserUpdate, UserResponse, UserListResponse,
    BuyerProfileCreate, BuyerProfileUpdate, BuyerProfileResponse, BuyerProfileCheckResponse,
    UserProfileResponse, BuyerHomeResponse, BuyerQuotaResponse, UserPinUpdate, UserDeviceTokenUpdate,
    HomeNearbyGasStationsResponse,
)
from app.modules.users.service import UserService

router = APIRouter()

@router.get("/", response_model=UserListResponse)
async def read_users(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Number of items per page"),
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Retrieve users with pagination. Only SUPERADMIN can list all users currently.
    """
    service = UserService(db)
    return await service.get_users(page=page, page_size=page_size)

@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: Request,
    user_in: UserCreate,
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Create a new user.
    - Public: Can create BUYER accounts.
    - ADMIN_COMPANY: Can create BUYER accounts linked to their company.
    - ADMIN_GAS_STATION: Can create SALES_OFFICER accounts linked to their gas station.
    - SUPERADMIN: Can create any account.
    """
    service = UserService(db)
    user = await service.create_user(user_in=user_in, current_user=current_user)
    
    # Audit logging
    from app.modules.system_audit_logs.service import SystemAuditLogService
    ip = SystemAuditLogService.resolve_ip(request)
    audit_svc = SystemAuditLogService(db)
    await audit_svc.log_action(
        actor=current_user,
        action=f"Tambah user baru: {user.name}",
        ip_address=ip
    )
    return user

@router.post("/me/buyer-profile", response_model=BuyerProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_buyer_profile(
    profile_in: BuyerProfileCreate,
    current_user: User = Depends(require_roles([UserRole.BUYER])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Create a BuyerProfile for the current authenticated user. Only for BUYER role.
    """
    service = UserService(db)
    return await service.create_buyer_profile(user_id=str(current_user.id), profile_in=profile_in)

@router.put("/me/buyer-profile", response_model=BuyerProfileResponse)
async def update_buyer_profile(
    profile_in: BuyerProfileUpdate,
    current_user: User = Depends(require_roles([UserRole.BUYER])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Update the current user's BuyerProfile. Only for BUYER role.
    """
    service = UserService(db)
    return await service.update_buyer_profile(user_id=str(current_user.id), profile_in=profile_in)

@router.post("/me/pin")
async def create_or_update_pin(
    pin_in: UserPinUpdate,
    current_user: User = Depends(require_roles([UserRole.BUYER])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Create or update PIN for the current authenticated user. Only for BUYER role.
    """
    service = UserService(db)
    return await service.update_buyer_pin(user_id=str(current_user.id), pin_in=pin_in)

@router.get("/me/buyer-profile/check", response_model=BuyerProfileCheckResponse)
async def check_buyer_profile(
    current_user: User = Depends(require_roles([UserRole.BUYER])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Check the current user's BuyerProfile status. Only for BUYER role.
    """
    service = UserService(db)
    return await service.check_buyer_profile(user_id=str(current_user.id))

@router.get("/me/buyer-profile", response_model=BuyerProfileResponse)
async def read_buyer_profile(
    current_user: User = Depends(require_roles([UserRole.BUYER])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Get the current user's BuyerProfile. Only for BUYER role.
    """
    service = UserService(db)
    return await service.get_buyer_profile(user_id=str(current_user.id))

@router.get("/me/profile", response_model=UserProfileResponse)
async def read_user_profile(
    current_user: User = Depends(require_roles([UserRole.BUYER])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Get the current user's aggregated Profile details. Only for BUYER role.
    """
    service = UserService(db)
    return await service.get_user_profile_detail(user_id=str(current_user.id))


@router.get("/me/home", response_model=BuyerHomeResponse)
async def read_buyer_home(
    latitude: float | None = Query(None),
    longitude: float | None = Query(None),
    current_user: User = Depends(require_roles([UserRole.BUYER])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    service = UserService(db)
    return await service.get_buyer_home(
        user_id=str(current_user.id),
        latitude=latitude,
        longitude=longitude,
    )


@router.get("/me/nearby-gas-stations", response_model=HomeNearbyGasStationsResponse)
async def read_nearby_gas_stations(
    latitude: float | None = Query(None),
    longitude: float | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_roles([UserRole.BUYER])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    service = UserService(db)
    return await service.get_nearby_gas_stations(
        latitude=latitude,
        longitude=longitude,
        limit=limit,
    )


@router.get("/me/quota", response_model=BuyerQuotaResponse)
async def read_buyer_quota(
    current_user: User = Depends(require_roles([UserRole.BUYER])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Retrieve user quota details including subsidized fuels and vehicle totals.
    """
    service = UserService(db)
    return await service.get_buyer_quota_detail(user_id=str(current_user.id))


@router.post("/me/device-token")
async def update_user_device_token(
    request: UserDeviceTokenUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Register or update the authenticated user's FCM device token.
    """
    service = UserService(db)
    return await service.update_device_token(user_id=str(current_user.id), token=request.token)


@router.get("/{user_id}", response_model=UserResponse)
async def read_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Get a specific user by id.
    """
    service = UserService(db)
    return await service.get_user(user_id=user_id)

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    request: Request,
    user_id: str,
    user_in: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Update a user.
    - Self: Can edit their own data.
    - SUPERADMIN: Can edit any user's data.
    - ADMIN_GAS_STATION: Can only modify a BUYER to grant them SALES_OFFICER role and link to gas station.
    """
    service = UserService(db)
    user = await service.update_user(user_id=user_id, user_in=user_in, current_user=current_user)
    
    # Audit logging
    from app.modules.system_audit_logs.service import SystemAuditLogService
    ip = SystemAuditLogService.resolve_ip(request)
    audit_svc = SystemAuditLogService(db)
    await audit_svc.log_action(
        actor=current_user,
        action=f"Update user: {user.name}",
        ip_address=ip
    )
    return user

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    request: Request,
    user_id: str,
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN])),
    db: AsyncSession = Depends(get_db)
) -> None:
    """
    Delete a user. Only SUPERADMIN can do this.
    """
    service = UserService(db)
    target_user = await service.get_user(user_id=user_id)
    target_name = target_user.name if target_user else user_id
    
    await service.delete_user(user_id=user_id, current_user=current_user)
    
    # Audit logging
    from app.modules.system_audit_logs.service import SystemAuditLogService
    ip = SystemAuditLogService.resolve_ip(request)
    audit_svc = SystemAuditLogService(db)
    await audit_svc.log_action(
        actor=current_user,
        action=f"Hapus user: {target_name}",
        ip_address=ip
    )

@router.get("/gas-stations/options")
async def get_gas_stations_options(
    query: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
) -> Any:
    from app.modules.gas_stations.models import GasStation
    from sqlalchemy.future import select
    from sqlalchemy import func
    stmt = select(GasStation)
    if query:
        stmt = stmt.filter(GasStation.name.ilike(f"%{query}%"))
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    stations = result.scalars().all()
    return {
        "items": [{"id": str(s.id), "name": s.name} for s in stations],
        "total": total,
        "page": page,
        "page_size": page_size
    }

@router.get("/companies/options")
async def get_companies_options(
    query: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
) -> Any:
    from app.modules.companies.models import Company
    from sqlalchemy.future import select
    from sqlalchemy import func
    stmt = select(Company)
    if query:
        stmt = stmt.filter(Company.name.ilike(f"%{query}%"))
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    companies = result.scalars().all()
    return {
        "items": [{"id": str(c.id), "name": c.name} for c in companies],
        "total": total,
        "page": page,
        "page_size": page_size
    }
