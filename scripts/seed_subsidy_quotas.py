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


async def main() -> None:
    async with AsyncSessionLocal() as session:
        summary = await seed_subsidy_quotas(session)

    logger.info(
        "Seeded subsidy quotas: created=%s existing=%s processed=%s month=%s year=%s usage_types=%s",
        summary["created"],
        summary["existing"],
        summary["processed"],
        summary["month"],
        summary["year"],
        summary["usage_types"],
    )


if __name__ == "__main__":
    asyncio.run(main())
