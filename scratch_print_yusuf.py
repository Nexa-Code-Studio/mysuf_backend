import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.database import AsyncSessionLocal
from sqlalchemy import select
from app.modules.users.models import User, BuyerProfile

async def main():
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(BuyerProfile))
        bps = res.scalars().all()
        print(f"Total profiles: {len(bps)}")
        for bp in bps:
            print(f"  nik: {bp.nik_snapshot}, risk: {bp.risk_score}")

if __name__ == "__main__":
    asyncio.run(main())
