import asyncio
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import AsyncSessionLocal
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main() -> None:
    logger.info("Connecting to database to drop and recreate public schema...")
    
    async with AsyncSessionLocal() as session:
        # Drop public schema
        logger.info("Dropping public schema...")
        await session.execute(text("DROP SCHEMA public CASCADE;"))
        # Recreate public schema
        logger.info("Recreating public schema...")
        await session.execute(text("CREATE SCHEMA public;"))
        await session.execute(text("GRANT ALL ON SCHEMA public TO public;"))
        await session.commit()
        
    logger.info("SUCCESS: Database schema has been completely reset and cleaned!")

if __name__ == "__main__":
    asyncio.run(main())
