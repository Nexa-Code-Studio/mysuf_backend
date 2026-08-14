import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import select
from app.core.config import settings
from app.modules.users.models import User, BuyerProfile
from app.modules.users.service import UserService
from app.core.database import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as session:
        # Get Ekya
        res = await session.execute(select(User).filter(User.email == 'ekya@sidia.com'))
        user = res.scalars().first()
        if not user:
            print("Ekya not found")
            return
        
        service = UserService(session)
        profile_detail = await service.get_user_profile_detail(user_id=str(user.id))
        print("Profile Detail from API:")
        for k, v in profile_detail.items():
            print(f"  {k}: {v}")
            
        home_detail = await service.get_buyer_home(user_id=str(user.id), latitude=None, longitude=None)
        print("\nHome Detail from API:")
        print(f"  personal_quota: {home_detail.get('personal_quota')}")
        print(f"  risk_status: {home_detail.get('risk_status')}")

if __name__ == "__main__":
    asyncio.run(main())
