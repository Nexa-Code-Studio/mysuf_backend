import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.database import AsyncSessionLocal
from sqlalchemy import select
from app.modules.gas_stations.models import GasStation

async def main():
    async with AsyncSessionLocal() as session:
        stations = (await session.execute(select(GasStation))).scalars().all()
        print(f"Total stations in DB: {len(stations)}")
        for idx, s in enumerate(stations):
            print(f"{idx+1}. {s.name}")

if __name__ == "__main__":
    asyncio.run(main())
