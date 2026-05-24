from typing import Any
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user, get_optional_current_user, require_roles
from app.modules.users.models import User, UserRole
from app.modules.users.schemas import (
    UserCreate, UserUpdate, UserResponse, UserListResponse,
    BuyerProfileCreate, BuyerProfileUpdate, BuyerProfileResponse, BuyerProfileCheckResponse,
    UserProfileResponse, BuyerHomeResponse, BuyerQuotaResponse,
)
from app.modules.users.service import UserService

router = APIRouter()

@router.get("/", response_model=UserListResponse)
async def read_users(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Number of items per page"),
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Retrieve users with pagination. Only SUPERADMIN can list all users currently.
    """
    service = UserService(db)
    return await service.get_users(page=page, page_size=page_size)

@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
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
    return await service.create_user(user_in=user_in, current_user=current_user)

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
    return await service.update_user(user_id=user_id, user_in=user_in, current_user=current_user)

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: AsyncSession = Depends(get_db)
) -> None:
    """
    Delete a user. Only SUPERADMIN can do this.
    """
    service = UserService(db)
    await service.delete_user(user_id=user_id, current_user=current_user)
