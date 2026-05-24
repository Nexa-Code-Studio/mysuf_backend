from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.modules.gas_stations.models import GasStation
from app.modules.subsidies.models import SubsidyOwnerType, SubsidyQuota
from app.modules.transactions.models import FuelTransaction, WalletTransaction
from app.modules.users.models import BuyerProfile, User
from app.modules.vehicles.models import VehicleOwnership, VehicleUsageType
from app.modules.wallets.models import OwnerType, Wallet

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
        result = await self.db.execute(select(BuyerProfile).filter(BuyerProfile.user_id == user_id))
        return result.scalars().first()

    async def get_vehicle_ownerships_by_ktp_nfc_id_snapshot(self, ktp_nfc_id_snapshot: str) -> list[VehicleOwnership]:
        result = await self.db.execute(
            select(VehicleOwnership)
            .filter(VehicleOwnership.ktp_nfc_id_snapshot == ktp_nfc_id_snapshot)
            .order_by(VehicleOwnership.created_at.desc(), VehicleOwnership.id.desc())
        )
        return list(result.scalars().all())

    async def get_wallet_by_owner_user_id(self, user_id: str) -> Wallet | None:
        result = await self.db.execute(
            select(Wallet).filter(Wallet.owner_type == OwnerType.USER, Wallet.owner_id == user_id)
        )
        return result.scalars().first()

    async def get_recent_wallet_transactions(self, wallet_id, limit: int = 10) -> list[WalletTransaction]:
        result = await self.db.execute(
            select(WalletTransaction)
            .options(
                selectinload(WalletTransaction.fuel_transactions).selectinload(FuelTransaction.gas_station),
                selectinload(WalletTransaction.fuel_transactions).selectinload(FuelTransaction.fuel_type),
            )
            .filter(WalletTransaction.wallet_id == wallet_id)
            .order_by(WalletTransaction.created_at.desc(), WalletTransaction.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_recent_fuel_transactions(self, buyer_profile_id, limit: int = 10) -> list[FuelTransaction]:
        result = await self.db.execute(
            select(FuelTransaction)
            .options(
                selectinload(FuelTransaction.gas_station),
                selectinload(FuelTransaction.fuel_type),
                selectinload(FuelTransaction.wallet_transaction),
            )
            .filter(FuelTransaction.buyer_profile_id == buyer_profile_id)
            .order_by(FuelTransaction.created_at.desc(), FuelTransaction.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_gas_stations(self) -> list[GasStation]:
        result = await self.db.execute(select(GasStation).order_by(GasStation.name.asc(), GasStation.id.asc()))
        return list(result.scalars().all())

    async def get_subsidy_quota_by_owner(self, owner_id, month: int, year: int) -> SubsidyQuota | None:
        result = await self.db.execute(
            select(SubsidyQuota).filter(
                SubsidyQuota.owner_type == SubsidyOwnerType.BUYER_PROFILE,
                SubsidyQuota.owner_id == owner_id,
                SubsidyQuota.month == month,
                SubsidyQuota.year == year,
            )
        )
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
