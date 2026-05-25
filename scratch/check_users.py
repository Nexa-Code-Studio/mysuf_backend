import asyncio
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.core.database import AsyncSessionLocal
from app.modules.users.models import BuyerProfile, User

async def main():
    async with AsyncSessionLocal() as session:
        # Search all BuyerProfiles for Eky's NIK
        stmt = select(BuyerProfile).options(selectinload(BuyerProfile.user)).filter(BuyerProfile.nik_snapshot == "3511111411040003")
        res = await session.execute(stmt)
        profiles = res.scalars().all()
        
        print("=== Duplicate Profiles for NIK 3511111411040003 ===")
        for p in profiles:
            print(f"Profile ID: {p.id}")
            print(f"  User ID: {p.user_id}")
            print(f"  User Name: {p.user.name}")
            print(f"  User Email: {p.user.email}")
            print(f"  KTP NFC ID: {p.ktp_nfc_id_snapshot}")
            print(f"  Verification Status: {p.verification_status}")
            print(f"  Risk Score: {p.risk_score}")

if __name__ == "__main__":
    asyncio.run(main())
