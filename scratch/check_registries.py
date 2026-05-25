import asyncio
from sqlalchemy.future import select
from app.core.database import AsyncSessionLocal
from app.modules.registries.models import CitizenRegistryMockup, VehicleRegistryMockup

async def main():
    async with AsyncSessionLocal() as session:
        # 1. Citizen Registry
        stmt = select(CitizenRegistryMockup).filter(CitizenRegistryMockup.nik == "3511111411040003")
        res = await session.execute(stmt)
        citizen = res.scalars().first()
        if citizen:
            print("=== Citizen Registry Mockup ===")
            print(f"NIK: {citizen.nik}")
            print(f"Name: {citizen.nama}")
            print(f"KTP NFC ID: {citizen.ktp_nfc_id}")
            print(f"KK ID: {citizen.kk_id}")
        else:
            print("Citizen not found in mockup registry.")
            
        # 2. Vehicle Registry
        stmt_veh = select(VehicleRegistryMockup).filter(VehicleRegistryMockup.owner_nik == "3511111411040003")
        res_veh = await session.execute(stmt_veh)
        vehs = res_veh.scalars().all()
        print("\n=== Vehicle Registry Mockup ===")
        for veh in vehs:
            print(f"Plate: {veh.plate_number}, brand: {veh.brand}, owner: {veh.owner_name}, owner_nik: {veh.owner_nik}")

if __name__ == "__main__":
    asyncio.run(main())
