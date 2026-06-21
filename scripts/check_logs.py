import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import AsyncSessionLocal
from app.modules.transactions.models import FraudLog
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as session:
        stmt = select(FraudLog).order_by(FraudLog.created_at.desc()).limit(15)
        res = await session.execute(stmt)
        logs = res.scalars().all()
        
        print(f"=== TOTAL FRAUD LOGS: {len(logs)} (LAST 15) ===")
        for index, log in enumerate(logs, 1):
            print(f"[{index}] Case ID: {log.case_id} | Created At: {log.created_at} UTC")
            print(f"    - ID: {log.id}")
            print(f"    - NIK: {log.nik_snapshot} | Plate: {log.plate_number_snapshot}")
            print(f"    - Risk Score: {log.risk_score} | Level: {log.risk_level.name if hasattr(log.risk_level, 'name') else log.risk_level}")
            print(f"    - Action Taken: {log.action_taken.name if hasattr(log.action_taken, 'name') else log.action_taken} | Status: {log.status.name if hasattr(log.status, 'name') else log.status}")
            print(f"    - Detected Frauds: {log.detected_frauds}")
            print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
