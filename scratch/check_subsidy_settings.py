import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import select
from app.core.config import settings
from app.modules.subsidies.models import SubsidySetting, SubsidyPolicy

async def main():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        res_settings = await conn.execute(select(SubsidySetting))
        print("Subsidy Settings:")
        for s in res_settings.all():
            print(f"  id={s.id}, income_threshold={s.income_threshold}, default_quota={s.default_quota_liters}, bonuses={s.occupation_bonuses}")
            
        res_policies = await conn.execute(select(SubsidyPolicy))
        print("\nSubsidy Policies:")
        for p in res_policies.all():
            print(f"  id={p.id}, name={p.name}, usage_type={p.usage_type}, monthly_quota={p.monthly_quota_liters}, max_allowed_njkb={p.max_allowed_njkb}, is_active={p.is_active}")
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
