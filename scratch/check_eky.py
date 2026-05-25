import asyncio
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.core.database import AsyncSessionLocal
from app.modules.users.models import BuyerProfile, User
from app.modules.vehicles.models import VehicleOwnership
from app.modules.registries.models import VehicleRegistryMockup

async def main():
    async with AsyncSessionLocal() as session:
        # 1. Find Eky's profile
        stmt_eky = select(BuyerProfile).options(selectinload(BuyerProfile.user)).filter(BuyerProfile.nik_snapshot == "3511111411040003")
        res_eky = await session.execute(stmt_eky)
        eky_profile = res_eky.scalars().first()
        
        if not eky_profile:
            print("Eky's profile not found by NIK 3511111411040003")
            return
            
        print("=== Eky Profile ===")
        print(f"ID: {eky_profile.id}")
        print(f"User ID: {eky_profile.user_id}")
        print(f"Name: {eky_profile.user.name}")
        print(f"NIK: {eky_profile.nik_snapshot}")
        print(f"NFC ID: {eky_profile.ktp_nfc_id_snapshot}")
        print(f"KK ID: {eky_profile.kk_id}")
        
        # 2. Get vehicle ownerships by Eky's profile ID
        stmt_own_profile = select(VehicleOwnership).filter(VehicleOwnership.owner_id == eky_profile.id)
        res_own_profile = await session.execute(stmt_own_profile)
        owns_profile = res_own_profile.scalars().all()
        
        print("\n=== Vehicle Ownerships by owner_id (buyer_profile.id) ===")
        for own in owns_profile:
            print(f"ID: {own.id}, Plate: {own.plate_number_snapshot}, NFC Snapshot: {own.ktp_nfc_id_snapshot}, owner_id: {own.owner_id}, usage_type: {own.usage_type}")
            
        # 3. Get vehicle ownerships by Eky's ktp_nfc_id_snapshot
        stmt_own_nfc = select(VehicleOwnership).filter(VehicleOwnership.ktp_nfc_id_snapshot == eky_profile.ktp_nfc_id_snapshot)
        res_own_nfc = await session.execute(stmt_own_nfc)
        owns_nfc = res_own_nfc.scalars().all()
        
        print(f"\n=== Vehicle Ownerships by ktp_nfc_id_snapshot ({eky_profile.ktp_nfc_id_snapshot}) ===")
        for own in owns_nfc:
            print(f"ID: {own.id}, Plate: {own.plate_number_snapshot}, NFC Snapshot: {own.ktp_nfc_id_snapshot}, owner_id: {own.owner_id}, usage_type: {own.usage_type}")

if __name__ == "__main__":
    asyncio.run(main())
