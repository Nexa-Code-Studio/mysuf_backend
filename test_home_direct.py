import asyncio
import os
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal
from app.modules.users.service import UserService
from app.modules.users.models import User
from sqlalchemy.future import select

async def main():
    async with AsyncSessionLocal() as session:
        # Get buyer
        result = await session.execute(select(User).filter(User.email == "buyer@mysuf.com"))
        user = result.scalars().first()
        if not user:
            print("Buyer not found")
            return
        
        print(f"User ID: {user.id}")
        service = UserService(session)
        try:
            home = await service.get_buyer_home(user_id=str(user.id), latitude=-6.2, longitude=106.8)
            print("Home data:", home)
        except Exception as e:
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
