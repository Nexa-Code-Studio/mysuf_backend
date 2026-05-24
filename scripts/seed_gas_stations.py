import asyncio
import logging
import sys
from pathlib import Path

# Resolve project root dynamically
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import AsyncSessionLocal
from app.modules.gas_stations.seed_data import seed_gas_stations

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main() -> None:
    logger.info("Starting gas stations seeding process...")
    async with AsyncSessionLocal() as session:
        summary = await seed_gas_stations(session)

    logger.info(
        "Seeded gas stations summary: created=%s existing=%s",
        summary["created"],
        summary["existing"],
    )

if __name__ == "__main__":
    asyncio.run(main())
