import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import select
from app.core.config import settings
from app.modules.registries.models import CitizenRegistryMockup

async def main():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        res = await conn.execute(select(CitizenRegistryMockup).filter(CitizenRegistryMockup.nik == '3511111411040003'))
        row = res.first()
        if row:
            print(f"CitizenRegistryMockup: id={row.id}, nik={row.nik}, nama={row.nama}, pekerjaan={row.pekerjaan}, penghasilan={row.penghasilan}")
        else:
            print("CitizenRegistryMockup NOT FOUND for NIK 3511111411040003")
            
        # Let's print all citizen mockups to see what is seeded
        res_all = await conn.execute(select(CitizenRegistryMockup))
        print("All CitizenRegistryMockups in db:")
        for r in res_all.all():
            print(f"  - nik={r.nik}, nama={r.nama}, pekerjaan={r.pekerjaan}, penghasilan={r.penghasilan}")
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
