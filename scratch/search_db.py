import asyncio
from sqlalchemy.future import select
from app.core.database import AsyncSessionLocal
from app.modules.users.models import BuyerProfile
from app.modules.vehicles.models import VehicleOwnership

async def main():
    async with AsyncSessionLocal() as session:
        # Search by NFC ID
        stmt = select(BuyerProfile).filter(BuyerProfile.ktp_nfc_id_snapshot == "04290CEA936C80")
        res = await session.execute(stmt)
        profile = res.scalars().first()
        if profile:
            print(f"BuyerProfile found for 04290CEA936C80: id={profile.id}, NIK={profile.nik_snapshot}")
        else:
            print("No BuyerProfile found for 04290CEA936C80")

        # Search VehicleOwnership by Plate
        stmt_veh = select(VehicleOwnership).filter(VehicleOwnership.plate_number_snapshot == "B 3511 EKY")
        res_veh = await session.execute(stmt_veh)
        vehs = res_veh.scalars().all()
        print(f"VehicleOwnership records for 'B 3511 EKY': {len(vehs)}")
        for veh in vehs:
            print(f"  ID: {veh.id}, owner_id: {veh.owner_id}, NFC Snapshot: {veh.ktp_nfc_id_snapshot}")

if __name__ == "__main__":
    asyncio.run(main())
