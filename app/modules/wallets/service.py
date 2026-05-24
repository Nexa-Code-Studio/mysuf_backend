from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.wallets.models import Wallet, OwnerType
from app.modules.wallets.repository import WalletRepository

class WalletService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = WalletRepository(db)

    async def get_or_create_user_wallet(self, user_id: str | UUID) -> Wallet:
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        
        wallet = await self.repo.get_wallet_by_owner(user_id, OwnerType.USER)
        if not wallet:
            new_wallet = Wallet(
                owner_id=user_id,
                owner_type=OwnerType.USER,
                balance=0.0,
                is_active=True
            )
            wallet = await self.repo.create_wallet(new_wallet)
        
        return wallet

    async def get_balance(self, user_id: str | UUID) -> Wallet:
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        
        wallet = await self.get_or_create_user_wallet(user_id)

        # Local imports to prevent circular references
        from app.modules.users.models import BuyerProfile
        from sqlalchemy import select
        
        profile_res = await self.db.execute(
            select(BuyerProfile).filter(BuyerProfile.user_id == user_id)
        )
        buyer_profile = profile_res.scalars().first()
        nik_masked = None
        if buyer_profile and buyer_profile.nik_snapshot:
            nik = buyer_profile.nik_snapshot
            if len(nik) >= 8:
                nik_masked = f"{nik[:4]}****{nik[-4:]}"
            else:
                nik_masked = nik

        wallet.nik_masked = nik_masked
        wallet.nik = buyer_profile.nik_snapshot if buyer_profile else None
        return wallet
