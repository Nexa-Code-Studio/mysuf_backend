import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import AsyncSessionLocal
from app.modules.fuels.seed_data import seed_fuel_types

async def run_seeder_demo():
    print("Initializing async database session for seeding...")
    async with AsyncSessionLocal() as session:
        summary = await seed_fuel_types(session)
        print("\n=== FUEL TYPES SEEDING COMPLETE ===")
        print(f"Created  : {summary['created']} new record(s)")
        print(f"Existing : {summary['existing']} record(s) already existed")
        print("===================================\n")

if __name__ == "__main__":
    asyncio.run(run_seeder_demo())
