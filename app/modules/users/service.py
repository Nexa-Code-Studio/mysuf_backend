from typing import List
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.modules.users.schemas import UserCreate, UserUpdate, BuyerProfileCreate, BuyerProfileUpdate
from app.modules.users.models import User, UserRole, BuyerProfile, VerificationStatus
from app.modules.users.repository import UserRepository
from app.modules.auth.utils import has_role

class UserService:
    def __init__(self, db: AsyncSession):
        self.repo = UserRepository(db)

    async def get_users(self, page: int = 1, page_size: int = 20) -> dict:
        skip = (page - 1) * page_size
        limit = page_size
        
        users = await self.repo.get_users(skip=skip, limit=limit)
        total = await self.repo.count_users()
        
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        
        return {
            "items": users,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages
            }
        }

    async def get_user(self, user_id: str) -> User:
        user = await self.repo.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user

    async def create_user(self, user_in: UserCreate, current_user: User | None = None) -> User:
        # Check if email exists
        existing_user = await self.repo.get_user_by_email(user_in.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The user with this email already exists in the system.",
            )

        # RBAC checks
        if current_user is None:
            # Public registration - only BUYER allowed, no gas_station/company association
            if set(user_in.role) != {UserRole.BUYER}:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Public registration can only create BUYER accounts")
            user_in.company_id = None
            user_in.gas_station_id = None
        else:
            if has_role(current_user, UserRole.SUPERADMIN):
                pass # Can create any role
            elif has_role(current_user, UserRole.ADMIN_GAS_STATION):
                if UserRole.SALES_OFFICER not in user_in.role:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Gas Station Admin can only create SALES_OFFICER accounts")
                # Force link to their gas station
                user_in.gas_station_id = current_user.gas_station_id
                user_in.company_id = None
            elif has_role(current_user, UserRole.ADMIN_COMPANY):
                if UserRole.BUYER not in user_in.role:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Company Admin can only create BUYER accounts")
                # Force link to their company
                user_in.company_id = current_user.company_id
                user_in.gas_station_id = None
            else:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough privileges to create users")

        db_user = User(
            email=user_in.email,
            name=user_in.name,
            password=get_password_hash(user_in.password),
            role=user_in.role,
            is_active=user_in.is_active,
            employee_id=user_in.employee_id,
            gas_station_id=user_in.gas_station_id,
            company_id=user_in.company_id
        )
        return await self.repo.create_user(db_user)

    async def update_user(self, user_id: str, user_in: UserUpdate, current_user: User) -> User:
        user = await self.get_user(user_id)

        # RBAC checks
        is_superuser = has_role(current_user, UserRole.SUPERADMIN)
        is_self = str(current_user.id) == user_id
        is_gas_station_admin = has_role(current_user, UserRole.ADMIN_GAS_STATION)
        
        if not (is_superuser or is_self or is_gas_station_admin):
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough privileges to edit this user")

        if is_gas_station_admin and not is_superuser:
            # "Admin gas station bisa link akun buyer agar menjadi sales_officer"
            # They can only modify a BUYER, add SALES_OFFICER, and set gas_station_id
            if UserRole.BUYER not in user.role:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Gas Station Admin can only modify BUYER accounts")
            
            # Ensure they are only adding SALES_OFFICER and linking to their station
            if user_in.role is not None and UserRole.SALES_OFFICER in user_in.role:
                user_in.gas_station_id = current_user.gas_station_id
            else:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Gas Station Admin can only grant SALES_OFFICER role")

        # Prevent normal users from escalating roles
        if not is_superuser and not is_gas_station_admin and user_in.role is not None:
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough privileges to modify roles")

        update_data = user_in.model_dump(exclude_unset=True)
        if "password" in update_data:
            update_data["password"] = get_password_hash(update_data["password"])
            
        for field, value in update_data.items():
            setattr(user, field, value)

        return await self.repo.update_user(user)

    async def delete_user(self, user_id: str, current_user: User) -> None:
        if not has_role(current_user, UserRole.SUPERADMIN):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only superadmin can delete users")
            
        user = await self.get_user(user_id)
        await self.repo.delete_user(user)

    async def create_buyer_profile(self, user_id: str, profile_in: BuyerProfileCreate) -> BuyerProfile:
        # Validate User exists and is BUYER
        user = await self.get_user(user_id)
        if UserRole.BUYER not in user.role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only users with BUYER role can have a buyer profile."
            )

        # Check for duplicate
        existing = await self.repo.get_buyer_profile_by_user_id(user_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Buyer profile already exists for this user."
            )

        # Validate kk_id exists
        kk = await self.repo.get_kk_by_id(str(profile_in.kk_id))
        if not kk:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The provided KK ID does not exist."
            )

        profile = BuyerProfile(
            nik_snapshot=profile_in.nik_snapshot,
            ktp_nfc_id_snapshot=profile_in.ktp_nfc_id_snapshot,
            kk_id=profile_in.kk_id,
            user_id=UUID(user_id) if isinstance(user_id, str) else user_id,
            verification_status=VerificationStatus.UNVERIFIED
        )
        return await self.repo.create_buyer_profile(profile)

    async def update_buyer_profile(self, user_id: str, profile_in: BuyerProfileUpdate) -> BuyerProfile:
        profile = await self.repo.get_buyer_profile_by_user_id(user_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Buyer profile not found."
            )

        # Validate kk_id if updated
        if profile_in.kk_id is not None:
            kk = await self.repo.get_kk_by_id(str(profile_in.kk_id))
            if not kk:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The provided KK ID does not exist."
                )

        update_data = profile_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(profile, field, value)

        return await self.repo.update_buyer_profile(profile)

    async def get_buyer_profile(self, user_id: str) -> BuyerProfile:
        profile = await self.repo.get_buyer_profile_by_user_id(user_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Buyer profile not found."
            )
        return profile

    async def check_buyer_profile(self, user_id: str) -> dict:
        profile = await self.repo.get_buyer_profile_by_user_id(user_id)
        if profile:
            return {
                "has_buyer_profile": True,
                "buyer_profile_id": profile.id,
                "verification_status": profile.verification_status.value
            }
        return {
            "has_buyer_profile": False,
            "buyer_profile_id": None,
            "verification_status": None
        }