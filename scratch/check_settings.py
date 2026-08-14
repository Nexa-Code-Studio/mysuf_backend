import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import AsyncSessionLocal
from app.modules.subsidies.models import SubsidySetting
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(SubsidySetting))
        setting = result.scalars().first()
        if setting:
            print("income_threshold:", setting.income_threshold)
            print("default_quota_liters:", setting.default_quota_liters)
            print("occupation_bonuses:", setting.occupation_bonuses)
        else:
            print("No SubsidySetting found!")

if __name__ == "__main__":
    asyncio.run(main())
