import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.config import settings

async def main():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.begin() as conn:
        print("Dropping NOT NULL constraint for plate_number_snapshot in fuel_transactions...")
        await conn.execute(text("ALTER TABLE fuel_transactions ALTER COLUMN plate_number_snapshot DROP NOT NULL;"))
        print("Dropping NOT NULL constraint for plate_number_snapshot in fraud_logs...")
        await conn.execute(text("ALTER TABLE fraud_logs ALTER COLUMN plate_number_snapshot DROP NOT NULL;"))
        print("Done!")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
