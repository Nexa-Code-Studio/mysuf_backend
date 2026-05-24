import asyncio
import logging
import sys
from pathlib import Path

# Resolve project root dynamically
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import AsyncSessionLocal
from app.modules.fuels.seed_data import seed_fuel_types

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main() -> None:
    logger.info("Starting fuel types seeding process...")
    async with AsyncSessionLocal() as session:
        summary = await seed_fuel_types(session)

    logger.info(
        "Seeded fuel types summary: created=%s existing=%s",
        summary["created"],
        summary["existing"],
    )

if __name__ == "__main__":
    asyncio.run(main())
