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
    logger.info("Connecting to database to clear test data...")
    
    # Tables to clear in order or with CASCADE
    tables = [
        "buyer_profile_documents",
        "buyer_profiles",
        "buyer_registration_documents",
        "buyer_registration_attempts",
        "users"
    ]
    
    async with AsyncSessionLocal() as session:
        # We run TRUNCATE with CASCADE to cleanly wipe all records and handle foreign key constraints
        truncate_query = f"TRUNCATE TABLE {', '.join(tables)} CASCADE;"
        logger.info(f"Executing: {truncate_query}")
        await session.execute(text(truncate_query))
        await session.commit()
        
    logger.info("SUCCESS: All user data, buyer profiles, and registration attempts have been successfully cleared!")
    logger.info("You can now test registrations again from scratch without any duplicate errors.")


if __name__ == "__main__":
    asyncio.run(main())
