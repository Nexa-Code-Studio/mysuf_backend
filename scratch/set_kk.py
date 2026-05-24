import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.modules.registries.models import KK
from app.modules.users.models import User, BuyerProfile

async def main():
    target_email = "ekyamuhammad@gmail.com"
    new_kk_code = "1234567890123456"
    
    async with AsyncSessionLocal() as session:
        # Find Eky's buyer profile
        profile_stmt = (
            select(BuyerProfile)
            .join(User, User.id == BuyerProfile.user_id)
            .filter(User.email == target_email)
        )
        profile_res = await session.execute(profile_stmt)
        buyer_profile = profile_res.scalars().first()
        
        if not buyer_profile:
            print("ERROR: Eky's BuyerProfile not found.")
            return
            
        # Check if new_kk_code already exists in the KK table
        kk_stmt = select(KK).filter(KK.code == new_kk_code)
        kk_res = await session.execute(kk_stmt)
        existing_kk = kk_res.scalars().first()
        
        if existing_kk:
            print(f"INFO: KK with code {new_kk_code} already exists (ID: {existing_kk.id}).")
            print("Linking Eky's BuyerProfile to this existing KK...")
            buyer_profile.kk_id = existing_kk.id
            await session.commit()
            print("SUCCESS: Linked buyer profile to existing KK!")
        else:
            print(f"INFO: KK with code {new_kk_code} does not exist.")
            # Get Eky's current KK to update its code
            current_kk_stmt = select(KK).filter(KK.id == buyer_profile.kk_id)
            current_kk_res = await session.execute(current_kk_stmt)
            current_kk = current_kk_res.scalars().first()
            
            if current_kk:
                print(f"Updating current KK (ID: {current_kk.id}) code from {current_kk.code} to {new_kk_code}...")
                current_kk.code = new_kk_code
                await session.commit()
                print("SUCCESS: Updated current KK code!")
            else:
                print("ERROR: Current KK record not found.")

if __name__ == "__main__":
    asyncio.run(main())
