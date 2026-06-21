import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.database import AsyncSessionLocal
from sqlalchemy import select
from app.modules.gas_stations.models import GasStation
from app.modules.users.models import BuyerProfile
from app.modules.vehicles.models import VehicleOwnership

SURABAYA_STATION_NAMES = [
    "SPBU Pertamina 44.501.01 (Surabaya Pusat)",
    "SPBU Pertamina 44.501.02 (Surabaya Timur)",
    "SPBU Pertamina 44.501.04 (Surabaya Selatan)",
    "SPBU Pertamina 44.509.01 (Jember)",
    "SPBU Pertamina 44.512.02 (Banyuwangi Ketapang)",
    "SPBU Pertamina 44.505.01 (Malang)",
]

async def main():
    async with AsyncSessionLocal() as session:
        stations = (await session.execute(select(GasStation))).scalars().all()
        buyers = (await session.execute(select(BuyerProfile))).scalars().all()
        vehicles = (await session.execute(select(VehicleOwnership))).scalars().all()
        
        surabaya_stations = [s for s in stations if s.name in SURABAYA_STATION_NAMES]
        
        buyer_vehicles_map = {}
        for v in vehicles:
            bid = str(v.owner_id)
            buyer_vehicles_map.setdefault(bid, []).append(v)
            
        fraud_buyers = [bp for bp in buyers if str(bp.id) in buyer_vehicles_map and len(buyer_vehicles_map[str(bp.id)]) > 0]
        
        print(f"Total stations: {len(stations)}")
        print(f"Surabaya stations: {len(surabaya_stations)}")
        print(f"Total buyers: {len(buyers)}")
        print(f"Total vehicles: {len(vehicles)}")
        print(f"Fraud buyers (buyers with vehicles): {len(fraud_buyers)}")
        
        # Print first few buyer IDs and vehicle owner_ids to see if there's a mismatch
        if buyers:
            print(f"First buyer ID: {buyers[0].id} (type: {type(buyers[0].id)})")
        if vehicles:
            print(f"First vehicle owner_id: {vehicles[0].owner_id} (type: {type(vehicles[0].owner_id)})")

if __name__ == "__main__":
    asyncio.run(main())
