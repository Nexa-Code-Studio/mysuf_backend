import asyncio
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import AsyncSessionLocal
from app.modules.registries.seed_data import seed_registry_mockups


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    async with AsyncSessionLocal() as session:
        summary = await seed_registry_mockups(session)

    logger.info(
        "Seeded registry mockups: kk=%s citizens=%s vehicles=%s",
        summary["kk"],
        summary["citizens"],
        summary["vehicles"],
    )


if __name__ == "__main__":
    asyncio.run(main())
