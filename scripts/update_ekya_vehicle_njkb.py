import asyncio
import logging
import sys
from pathlib import Path

from sqlalchemy import select, delete

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import AsyncSessionLocal
from app.modules.registries.models import VehicleRegistryMockup, CitizenRegistryMockup
from app.modules.subsidies.models import KKSubsidyEligibility

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TARGET_PLATE = "B 3511 EKY"
NEW_NJKB = 200_000_000
NEW_PKB = 2_500_000


async def main() -> None:
    logger.info("Updating NJKB for vehicle: %s", TARGET_PLATE)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(VehicleRegistryMockup).filter(
                VehicleRegistryMockup.plate_number == TARGET_PLATE
            )
        )
        vehicle = result.scalars().first()

        if not vehicle:
            logger.error("Vehicle '%s' not found in registry. Has the seed been run?", TARGET_PLATE)
            return

        logger.info(
            "Current: NJKB=%s, PKB=%s  ->  New: NJKB=%.2f, PKB=%.2f",
            vehicle.njkb, vehicle.pkb, NEW_NJKB, NEW_PKB,
        )

        vehicle.njkb = NEW_NJKB
        vehicle.pkb = NEW_PKB

        citizen_result = await session.execute(
            select(CitizenRegistryMockup).filter(
                CitizenRegistryMockup.nik == vehicle.owner_nik
            )
        )
        citizen = citizen_result.scalars().first()
        if citizen:
            await session.execute(
                delete(KKSubsidyEligibility).filter(
                    KKSubsidyEligibility.kk_id == citizen.kk_id
                )
            )
            logger.info("Cleared cached subsidy eligibility for KK.")

        await session.commit()

    logger.info(
        "Vehicle '%s' NJKB updated to %.2f and cached eligibility cleared.",
        TARGET_PLATE, NEW_NJKB,
    )


if __name__ == "__main__":
    asyncio.run(main())
