from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.modules.wallets.models import Wallet, OwnerType

class WalletRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_wallet_by_owner(self, owner_id: UUID, owner_type: OwnerType) -> Wallet | None:
        result = await self.db.execute(
            select(Wallet).filter(Wallet.owner_id == owner_id, Wallet.owner_type == owner_type)
        )
        return result.scalars().first()

    async def create_wallet(self, wallet: Wallet) -> Wallet:
        self.db.add(wallet)
        await self.db.commit()
        await self.db.refresh(wallet)
        return wallet
