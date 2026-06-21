import asyncio
import logging
import random
import sys
from pathlib import Path

from sqlalchemy.future import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import AsyncSessionLocal
from app.modules.gas_stations.models import GasStation

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

JAVA_POLYGON = [
    (-6.294942, 106.939415),
    (-7.058396, 106.576602),
    (-8.445465, 114.266608),
    (-7.950733, 114.377684),
]

def _point_in_polygon(lat: float, lng: float, polygon: list[tuple[float, float]]) -> bool:
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        lat_i, lng_i = polygon[i]
        lat_j, lng_j = polygon[j]
        if ((lat_i > lat) != (lat_j > lat)) and (lng < (lng_j - lng_i) * (lat - lat_i) / (lat_j - lat_i) + lng_i):
            inside = not inside
        j = i
    return inside

def random_java_coordinates() -> tuple[float, float]:
    lats = [p[0] for p in JAVA_POLYGON]
    lngs = [p[1] for p in JAVA_POLYGON]
    min_lat, max_lat = min(lats), max(lats)
    min_lng, max_lng = min(lngs), max(lngs)

    for _ in range(100):
        lat = random.uniform(min_lat, max_lat)
        lng = random.uniform(min_lng, max_lng)
        if _point_in_polygon(lat, lng, JAVA_POLYGON):
            return round(lat, 4), round(lng, 4)

    raise RuntimeError("Could not generate coordinates inside polygon after 100 attempts")

async def main() -> None:
    logger.info("Starting gas station relocation to Java island...")

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(GasStation))
        stations = result.scalars().all()

        if not stations:
            logger.info("No gas stations found in database. Nothing to update.")
            return

        logger.info("Found %s gas station(s) to relocate.", len(stations))

        for station in stations:
            old_lat, old_lng = station.latitude, station.longitude
            station.latitude, station.longitude = random_java_coordinates()
            logger.debug(
                "Relocated '%s': (%.4f, %.4f) -> (%.4f, %.4f)",
                station.name, old_lat, old_lng, station.latitude, station.longitude,
            )

        await session.commit()

    logger.info(
        "Successfully relocated %s gas station(s) to coordinates within Java island.",
        len(stations),
    )

if __name__ == "__main__":
    asyncio.run(main())
