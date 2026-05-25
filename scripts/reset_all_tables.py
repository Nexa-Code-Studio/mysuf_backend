import asyncio
import logging
import sys
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import AsyncSessionLocal, Base


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


EXCLUDED_TABLES = {"alembic_version"}


def _quoted_table_names() -> list[str]:
    table_names = sorted(
        table.name
        for table in Base.metadata.sorted_tables
        if table.name not in EXCLUDED_TABLES
    )
    return [f'"{table_name}"' for table_name in table_names]


async def main() -> None:
    table_names = _quoted_table_names()
    if not table_names:
        logger.info("No application tables found to reset.")
        return

    truncate_query = f"TRUNCATE TABLE {', '.join(table_names)} RESTART IDENTITY CASCADE;"
    logger.info("Resetting %s tables...", len(table_names))

    async with AsyncSessionLocal() as session:
        await session.execute(text(truncate_query))
        await session.commit()

    logger.info("Database reset completed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
