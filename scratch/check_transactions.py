import asyncio
from app.core.database import AsyncSessionLocal
from app.modules.transactions.models import FuelTransaction, FuelTransactionStatus
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as db:
        stmt = select(FuelTransaction)
        res = await db.execute(stmt)
        transactions = res.scalars().all()
        print(f"Total transactions in DB: {len(transactions)}")
        for tx in transactions:
            print(f"ID: {tx.id}, Station: {tx.gas_station_id}, Status: {tx.transaction_status}, Fuel ID: {tx.fuel_type_id}, Liters: {tx.liters}, Total Amount: {tx.total_amount}, Plate: {tx.plate_number_snapshot}")

if __name__ == "__main__":
    asyncio.run(main())
