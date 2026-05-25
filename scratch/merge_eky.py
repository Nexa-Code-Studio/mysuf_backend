import asyncio
from sqlalchemy.future import select
from app.core.database import AsyncSessionLocal
from app.modules.users.models import BuyerProfile, User
from app.modules.vehicles.models import VehicleOwnership

async def main():
    async with AsyncSessionLocal() as session:
        # 1. Get ekyamuhammad@gmail.com profile
        res = await session.execute(
            select(BuyerProfile).join(User).filter(User.email == "ekyamuhammad@gmail.com")
        )
        ekya_gmail_profile = res.scalars().first()

        # 2. Get ekya@mysuf.com profile
        res_seed = await session.execute(
            select(BuyerProfile).join(User).filter(User.email == "ekya@mysuf.com")
        )
        ekya_seed_profile = res_seed.scalars().first()

        if ekya_gmail_profile and ekya_seed_profile:
            print("Found both profiles. Merging...")
            # 2a. Re-assign ekya@mysuf.com's vehicle ownerships to ekyamuhammad@gmail.com
            res_vehs = await session.execute(
                select(VehicleOwnership).filter(VehicleOwnership.owner_id == ekya_seed_profile.id)
            )
            seed_vehs = res_vehs.scalars().all()
            for veh in seed_vehs:
                print(f"Re-assigning vehicle {veh.plate_number_snapshot} to ekyamuhammad@gmail.com profile")
                veh.owner_id = ekya_gmail_profile.id
                veh.ktp_nfc_id_snapshot = "04290CEA936C80"
            
            # 2b. Re-assign ekyamuhammad@gmail.com's own vehicles to have NFC id "04290CEA936C80"
            res_own_vehs = await session.execute(
                select(VehicleOwnership).filter(VehicleOwnership.owner_id == ekya_gmail_profile.id)
            )
            own_vehs = res_own_vehs.scalars().all()
            for veh in own_vehs:
                veh.ktp_nfc_id_snapshot = "04290CEA936C80"

            # 2c. Update ekyamuhammad@gmail.com profile's NFC ID to "04290CEA936C80"
            ekya_gmail_profile.ktp_nfc_id_snapshot = "04290CEA936C80"

            # 2d. Delete duplicate ekya@mysuf.com buyer profile to avoid future database conflicts
            await session.delete(ekya_seed_profile)
            
            await session.commit()
            print("Successfully merged profiles and vehicles!")
        else:
            print("Could not find both profiles for merge.")

if __name__ == "__main__":
    asyncio.run(main())
