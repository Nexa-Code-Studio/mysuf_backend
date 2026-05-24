import random
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.modules.gas_stations.models import GasStation

# 4 Extremes / Edges of Java Island Bounding Box
JAVA_BOUNDS = {
    "west_lon": 105.1,   # Anyer / Ujung Kulon
    "east_lon": 114.6,   # Banyuwangi / Ketapang
    "north_lat": -5.9,   # Pantura / Jakarta Coast
    "south_lat": -8.5,   # Southern Coast (Pacitan/Pangandaran)
}

def generate_java_gas_stations(count: int = 15) -> list[dict]:
    """
    Generates distributed gas station coordinates across Java Island.
    Partitions the width (longitude) evenly and assigns a random latitude (length/depth) within Java bounds.
    """
    # Fix seed to ensure deterministic generation across seed runs
    rng = random.Random(42)
    
    stations = []
    lon_start = JAVA_BOUNDS["west_lon"]
    lon_end = JAVA_BOUNDS["east_lon"]
    lon_step = (lon_end - lon_start) / (count - 1)
    
    for i in range(count):
        # Evenly spaced longitude (West to East)
        lon = lon_start + (i * lon_step)
        
        # Random latitude (North to South depth of Java Island)
        lat = rng.uniform(JAVA_BOUNDS["south_lat"], JAVA_BOUNDS["north_lat"])
        
        # Categorize name based on longitude zones
        if lon < 106.8:
            zone_name = "Banten"
        elif lon < 108.5:
            zone_name = "Jawa Barat"
        elif lon < 111.0:
            zone_name = "Jawa Tengah / DIY"
        else:
            zone_name = "Jawa Timur"
            
        spbu_code = rng.randint(10000, 99999)
        name = f"SPBU Pertamina {spbu_code} ({zone_name} - Zone {i+1})"
        
        stations.append({
            "name": name,
            "latitude": round(lat, 4),
            "longitude": round(lon, 4)
        })
        
    return stations

# Generate the 15 distributed gas stations
GAS_STATIONS_SEED_DATA = generate_java_gas_stations(15)

async def seed_gas_stations(session: AsyncSession, seed_data: list[dict] = None) -> dict[str, int]:
    """
    Asynchronous seeder to match the existing async session patterns of the project.
    """
    dataset = seed_data or GAS_STATIONS_SEED_DATA
    summary = {"created": 0, "existing": 0}

    for item in dataset:
        # Check if the gas station already exists by name
        result = await session.execute(
            select(GasStation).filter(GasStation.name == item["name"])
        )
        existing = result.scalars().first()

        if existing is None:
            station = GasStation(
                name=item["name"],
                latitude=item["latitude"],
                longitude=item["longitude"],
            )
            session.add(station)
            summary["created"] += 1
        else:
            summary["existing"] += 1

    await session.commit()
    return summary

def seed_gas_stations_sync(db: Session, seed_data: list[dict] = None) -> dict[str, int]:
    """
    Synchronous seeder using standard SQLAlchemy Session.
    """
    dataset = seed_data or GAS_STATIONS_SEED_DATA
    summary = {"created": 0, "existing": 0}

    for item in dataset:
        # Check if the gas station already exists by name
        existing = db.query(GasStation).filter(GasStation.name == item["name"]).first()

        if existing is None:
            station = GasStation(
                name=item["name"],
                latitude=item["latitude"],
                longitude=item["longitude"],
            )
            db.add(station)
            summary["created"] += 1
        else:
            summary["existing"] += 1

    db.commit()
    return summary
