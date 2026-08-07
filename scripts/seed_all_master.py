import asyncio
import argparse
import logging
import sys
from pathlib import Path

# Resolve project root dynamically
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import AsyncSessionLocal
from app.modules.registries.seed_data import seed_registry_mockups
from app.modules.gas_stations.seed_data import seed_gas_stations
from app.modules.fuels.seed_data import seed_fuel_types
from app.modules.subsidies.seed_data import seed_subsidy_policies, seed_subsidy_quotas
from app.modules.users.seed_data import seed_users, seed_buyer_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed all MySuf backend master data.")
    parser.add_argument("--month", type=int, help="Quota month to seed (1-12). Defaults to current month.")
    parser.add_argument("--year", type=int, help="Quota year to seed. Defaults to current year.")
    args = parser.parse_args()
    if args.month is not None and not 1 <= args.month <= 12:
        parser.error("--month must be between 1 and 12")
    if args.year is not None and args.year <= 0:
        parser.error("--year must be a positive integer")
    return args


async def main(month: int | None = None, year: int | None = None) -> None:
    logger.info("==================================================")
    logger.info("STARTING MASTER DATA ALL-IN-ONE SEEDING PROCESS...")
    logger.info("==================================================")

    async with AsyncSessionLocal() as session:
        # 1. Government Registries Mockup (KK, Citizen, Vehicle)
        logger.info("1/7 Seeding Government Registry Mockups...")
        reg_summary = await seed_registry_mockups(session)
        logger.info(
            "   [OK] KK seeded/existing: %s, Citizens: %s",
            reg_summary["kk"],
            reg_summary["citizens"]
        )

        # 2. Gas Stations
        logger.info("2/7 Seeding Gas Stations...")
        gs_summary = await seed_gas_stations(session)
        logger.info(
            "   [OK] Created: %s, Existing: %s",
            gs_summary["created"],
            gs_summary["existing"]
        )

        # 3. Fuel Types
        logger.info("3/7 Seeding Fuel Types...")
        fuel_summary = await seed_fuel_types(session)
        logger.info(
            "   [OK] Created: %s, Existing: %s",
            fuel_summary["created"],
            fuel_summary["existing"]
        )

        # 4. Subsidy Policies
        logger.info("4/7 Seeding Subsidy Policies...")
        policy_summary = await seed_subsidy_policies(session)
        logger.info(
            "   [OK] Created: %s, Updated: %s, Active: %s",
            policy_summary["created"],
            policy_summary["updated"],
            policy_summary["active"]
        )

        # 5. Non-BUYER System Users (SA, AC, AGS, SO)
        logger.info("5/7 Seeding Non-BUYER System Users...")
        user_summary = await seed_users(session)
        logger.info(
            "   [OK] Created: %s, Existing: %s",
            user_summary["created"],
            user_summary["existing"]
        )

        # 6. Verified Buyer Users
        logger.info("6/7 Seeding Verified BUYER Users...")
        buyer_summary = await seed_buyer_user(session)
        logger.info(
            "   [OK] Created: %s, Repaired: %s, Existing: %s, Skipped: %s",
            buyer_summary["created"],
            buyer_summary["repaired"],
            buyer_summary["existing"],
            buyer_summary["skipped"],
        )

        # 7. Subsidy Quotas
        logger.info("7/7 Seeding Subsidy Quotas...")
        quota_summary = await seed_subsidy_quotas(session, month=month, year=year)
        logger.info(
            "   [OK] Created: %s, Existing: %s, Processed: %s, Period: %s/%s",
            quota_summary["created"],
            quota_summary["existing"],
            quota_summary["processed"],
            quota_summary["month"],
            quota_summary["year"],
        )

    logger.info("==================================================")
    logger.info("MASTER DATA SEEDING COMPLETED SUCCESSFULLY!")
    logger.info("All seeded accounts use default password: Password123")
    logger.info("==================================================")

if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(month=args.month, year=args.year))
