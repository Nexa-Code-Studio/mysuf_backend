import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.modules.users.models import User, BuyerProfile
from app.modules.registries.models import KK

async def main():
    target_email = "ekyamuhammad@gmail.com"
    new_kk_code = "1234567890123456"
    
    async with AsyncSessionLocal() as session:
        stmt = (
            select(KK)
            .join(BuyerProfile, BuyerProfile.kk_id == KK.id)
            .join(User, User.id == BuyerProfile.user_id)
            .filter(User.email == target_email)
        )
        result = await session.execute(stmt)
        kk = result.scalars().first()
        
        if not kk:
            print(f"Error: KK entry not found for email '{target_email}'")
            return
            
        print(f"Current KK Code in database: {kk.code}")
        print(f"Updating KK Code to: {new_kk_code}...")
        
        kk.code = new_kk_code
        await session.commit()
        
        print("Commit successful!")
        
        stmt_verify = (
            select(KK.code)
            .filter(KK.id == kk.id)
        )
        result_verify = await session.execute(stmt_verify)
        verified_code = result_verify.scalar()
        print(f"Verified KK Code in database now: {verified_code}")

if __name__ == "__main__":
    asyncio.run(main())
