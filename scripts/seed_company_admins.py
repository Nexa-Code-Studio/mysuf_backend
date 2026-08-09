"""
Runner script: seed default company admin users.

Usage:
    python scripts/seed_company_admins.py

This is safe to run multiple times (idempotent).
All seeded accounts use the default password: mysuf123
"""
import asyncio
import logging
import sys
from pathlib import Path

# Resolve project root dynamically so the script can be run from any cwd
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import AsyncSessionLocal
from app.modules.companies.seed_data import seed_company_admins, COMPANY_ADMIN_DATA

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("=" * 56)
    logger.info("  SEEDING COMPANY ADMIN USERS")
    logger.info("=" * 56)

    async with AsyncSessionLocal() as session:
        summary = await seed_company_admins(session)

    logger.info("")
    logger.info("Results:")
    logger.info("  Companies created  : %s", summary["companies_created"])
    logger.info("  Companies existing : %s", summary["companies_existing"])
    logger.info("  Admins created     : %s", summary["admins_created"])
    logger.info("  Admins existing    : %s", summary["admins_existing"])
    logger.info("")
    logger.info("Seeded company admin accounts:")
    for entry in COMPANY_ADMIN_DATA:
        logger.info(
            "  %-35s  →  email: %-38s  pass: mysuf123",
            entry["company"]["name"],
            entry["admin"]["email"],
        )
    logger.info("=" * 56)
    logger.info("DONE")


if __name__ == "__main__":
    asyncio.run(main())
