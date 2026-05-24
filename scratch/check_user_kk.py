import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.modules.users.models import User, BuyerProfile
from app.modules.registries.models import KK

async def main():
    async with AsyncSessionLocal() as session:
        stmt = (
            select(User, BuyerProfile, KK)
            .join(BuyerProfile, BuyerProfile.user_id == User.id)
            .join(KK, KK.id == BuyerProfile.kk_id)
        )
        result = await session.execute(stmt)
        rows = result.all()
        
        print("\n=== USER BUYER PROFILES & KK DATA IN DATABASE ===")
        if not rows:
            print("No buyer profiles found in database.")
            return
            
        for user, profile, kk in rows:
            print(f"\nUser ID: {user.id}")
            print(f"Name   : {user.name}")
            print(f"Email  : {user.email}")
            print(f"NIK    : {profile.nik_snapshot}")
            print(f"KK ID  : {profile.kk_id}")
            print(f"KK Code: {kk.code}")
        print("=================================================\n")

if __name__ == "__main__":
    asyncio.run(main())
