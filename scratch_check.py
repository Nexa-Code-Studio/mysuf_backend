import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.database import AsyncSessionLocal
from sqlalchemy import select, func
from app.modules.transactions.models import FraudLog, FuelTransaction
from app.modules.users.models import User, UserRole

async def main():
    async with AsyncSessionLocal() as session:
        logs_count = (await session.execute(select(func.count(FraudLog.id)))).scalar()
        print(f"Total FraudLog: {logs_count}")
        
        tx_count = (await session.execute(select(func.count(FuelTransaction.id)))).scalar()
        print(f"Total FuelTransaction: {tx_count}")
        
        users_count = (await session.execute(select(func.count(User.id)))).scalar()
        print(f"Total User: {users_count}")
        
        # print some log data if any
        res = await session.execute(select(FraudLog).limit(3))
        for log in res.scalars().all():
            print(f"FraudLog id: {log.id}, risk_score: {log.risk_score}, level: {log.risk_level}")

if __name__ == "__main__":
    asyncio.run(main())
