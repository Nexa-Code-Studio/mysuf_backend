from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.modules.users.models import User

class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self.db.execute(
            select(User).options(selectinload(User.buyer_profile)).filter(User.email == email)
        )
        return result.scalars().first()

    async def get_user_by_id(self, user_id: str) -> User | None:
        result = await self.db.execute(
            select(User).options(selectinload(User.buyer_profile)).filter(User.id == user_id)
        )
        return result.scalars().first()

    async def get_users(self, skip: int = 0, limit: int = 100) -> List[User]:
        result = await self.db.execute(
            select(User).options(selectinload(User.buyer_profile)).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def count_users(self) -> int:
        from sqlalchemy import func
        result = await self.db.execute(select(func.count()).select_from(User))
        return result.scalar() or 0

    async def create_user(self, user: User) -> User:
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_user(self, user: User) -> User:
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def delete_user(self, user: User) -> None:
        await self.db.delete(user)
        await self.db.commit()

    async def get_kk_by_id(self, kk_id: str) -> Optional[object]:
        from app.modules.registries.models import KK
        result = await self.db.execute(select(KK).filter(KK.id == kk_id))
        return result.scalars().first()

    async def get_buyer_profile_by_user_id(self, user_id: str) -> Optional[object]:
        from app.modules.users.models import BuyerProfile
        result = await self.db.execute(select(BuyerProfile).filter(BuyerProfile.user_id == user_id))
        return result.scalars().first()

    async def create_buyer_profile(self, profile: object) -> object:
        self.db.add(profile)
        await self.db.commit()
        await self.db.refresh(profile)
        return profile

    async def update_buyer_profile(self, profile: object) -> object:
        await self.db.commit()
        await self.db.refresh(profile)
        return profile