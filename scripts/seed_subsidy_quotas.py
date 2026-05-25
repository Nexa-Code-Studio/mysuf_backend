import argparse
import asyncio
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import AsyncSessionLocal
from app.modules.subsidies.seed_data import seed_subsidy_quotas


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed subsidy quotas for a target period.")
    parser.add_argument("--month", type=int, help="Quota month to seed (1-12). Defaults to current month.")
    parser.add_argument("--year", type=int, help="Quota year to seed. Defaults to current year.")
    args = parser.parse_args()
    if args.month is not None and not 1 <= args.month <= 12:
        parser.error("--month must be between 1 and 12")
    if args.year is not None and args.year <= 0:
        parser.error("--year must be a positive integer")
    return args


async def main(month: int | None = None, year: int | None = None) -> None:
    async with AsyncSessionLocal() as session:
        summary = await seed_subsidy_quotas(session, month=month, year=year)

    logger.info(
        "Seeded subsidy quotas: created=%s existing=%s processed=%s month=%s year=%s",
        summary["created"],
        summary["existing"],
        summary["processed"],
        summary["month"],
        summary["year"],
    )


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(month=args.month, year=args.year))
