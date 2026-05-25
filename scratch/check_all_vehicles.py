import asyncio
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.core.database import AsyncSessionLocal
from app.modules.users.models import BuyerProfile, User
from app.modules.vehicles.models import VehicleOwnership

async def main():
    async with AsyncSessionLocal() as session:
        print("=== ALL BUYER PROFILES IN THE DB ===")
        stmt_profiles = select(BuyerProfile).options(selectinload(BuyerProfile.user))
        res_profiles = await session.execute(stmt_profiles)
        profiles = res_profiles.scalars().all()
        for p in profiles:
            email = p.user.email if p.user else "NO USER"
            name = p.user.name if p.user else "NO USER"
            print(f"Profile ID: {p.id} | Email: {email} | Name: {name} | NIK: {p.nik_snapshot} | NFC: {p.ktp_nfc_id_snapshot}")

        print("\n=== ALL VEHICLE OWNERSHIPS IN THE DB ===")
        stmt_vehicles = select(VehicleOwnership)
        res_vehicles = await session.execute(stmt_vehicles)
        vehicles = res_vehicles.scalars().all()
        for v in vehicles:
            # Let's find owner profile
            stmt_o = select(BuyerProfile).options(selectinload(BuyerProfile.user)).filter(BuyerProfile.id == v.owner_id)
            res_o = await session.execute(stmt_o)
            o = res_o.scalars().first()
            o_email = o.user.email if (o and o.user) else "UNKNOWN"
            print(f"Ownership ID: {v.id} | Plate: {v.plate_number_snapshot} | NFC Snap: {v.ktp_nfc_id_snapshot} | Owner Profile ID: {v.owner_id} ({o_email})")

if __name__ == "__main__":
    asyncio.run(main())
