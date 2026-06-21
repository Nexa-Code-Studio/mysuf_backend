import random
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.modules.gas_stations.models import GasStation

GAS_STATIONS_SEED_DATA = [
    # === SURABAYA & EAST JAVA (18 stations) ===
    {"name": "SPBU Pertamina 44.501.01 (Surabaya Pusat)", "latitude": -7.2575, "longitude": 112.7521},
    {"name": "SPBU Pertamina 44.501.02 (Surabaya Timur)", "latitude": -7.2875, "longitude": 112.7921},
    {"name": "SPBU Pertamina 44.501.03 (Surabaya Barat)", "latitude": -7.2475, "longitude": 112.7221},
    {"name": "SPBU Pertamina 44.501.04 (Surabaya Selatan)", "latitude": -7.3075, "longitude": 112.7421},
    {"name": "SPBU Pertamina 44.501.05 (Surabaya Utara)", "latitude": -7.2175, "longitude": 112.7321},
    {"name": "SPBU Pertamina 44.502.01 (Sidoarjo)", "latitude": -7.4525, "longitude": 112.7175},
    {"name": "SPBU Pertamina 44.503.01 (Gresik)", "latitude": -7.1575, "longitude": 112.6521},
    {"name": "SPBU Pertamina 44.504.01 (Mojokerto)", "latitude": -7.4725, "longitude": 112.4321},
    {"name": "SPBU Pertamina 44.505.01 (Malang)", "latitude": -7.9775, "longitude": 112.6321},
    {"name": "SPBU Pertamina 44.506.01 (Pasuruan)", "latitude": -7.6425, "longitude": 112.9021},
    {"name": "SPBU Pertamina 44.507.01 (Probolinggo)", "latitude": -7.7525, "longitude": 113.2121},
    {"name": "SPBU Pertamina 44.508.01 (Lumajang)", "latitude": -8.1325, "longitude": 113.2221},
    {"name": "SPBU Pertamina 44.509.01 (Jember)", "latitude": -8.1725, "longitude": 113.7021},
    {"name": "SPBU Pertamina 44.510.01 (Bondowoso)", "latitude": -7.9425, "longitude": 113.8221},
    {"name": "SPBU Pertamina 44.511.01 (Situbondo)", "latitude": -7.7025, "longitude": 114.0021},
    {"name": "SPBU Pertamina 44.512.01 (Banyuwangi Kota)", "latitude": -8.2125, "longitude": 114.3721},
    {"name": "SPBU Pertamina 44.512.02 (Banyuwangi Ketapang)", "latitude": -8.1475, "longitude": 114.4221},
    {"name": "SPBU Pertamina 44.513.01 (Kediri)", "latitude": -7.8225, "longitude": 112.0121},

    # === JAKARTA & BANTEN (10 stations) ===
    {"name": "SPBU Pertamina 31.101.01 (Jakarta Pusat)", "latitude": -6.1825, "longitude": 106.8321},
    {"name": "SPBU Pertamina 31.101.02 (Jakarta Selatan)", "latitude": -6.2625, "longitude": 106.8121},
    {"name": "SPBU Pertamina 31.101.03 (Jakarta Timur)", "latitude": -6.2949, "longitude": 106.9394},
    {"name": "SPBU Pertamina 31.101.04 (Jakarta Barat)", "latitude": -6.1675, "longitude": 106.7421},
    {"name": "SPBU Pertamina 31.101.05 (Jakarta Utara)", "latitude": -6.1225, "longitude": 106.8821},
    {"name": "SPBU Pertamina 31.102.01 (Tangerang)", "latitude": -6.1775, "longitude": 106.6321},
    {"name": "SPBU Pertamina 31.103.01 (Bekasi)", "latitude": -6.2375, "longitude": 106.9921},
    {"name": "SPBU Pertamina 31.104.01 (Depok)", "latitude": -6.3925, "longitude": 106.8221},
    {"name": "SPBU Pertamina 31.105.01 (Bogor)", "latitude": -6.5975, "longitude": 106.7921},
    {"name": "SPBU Pertamina 31.106.01 (Cibinong)", "latitude": -6.4825, "longitude": 106.8521},

    # === WEST JAVA (8 stations) ===
    {"name": "SPBU Pertamina 32.201.01 (Bandung)", "latitude": -6.9175, "longitude": 107.6021},
    {"name": "SPBU Pertamina 32.202.01 (Cimahi)", "latitude": -6.8725, "longitude": 107.5421},
    {"name": "SPBU Pertamina 32.203.01 (Cirebon)", "latitude": -6.7225, "longitude": 108.5621},
    {"name": "SPBU Pertamina 32.204.01 (Karawang)", "latitude": -6.3225, "longitude": 107.3021},
    {"name": "SPBU Pertamina 32.205.01 (Purwakarta)", "latitude": -6.5575, "longitude": 107.4521},
    {"name": "SPBU Pertamina 32.206.01 (Subang)", "latitude": -6.5625, "longitude": 107.7021},
    {"name": "SPBU Pertamina 32.207.01 (Sukabumi)", "latitude": -6.9225, "longitude": 106.9221},
    {"name": "SPBU Pertamina 32.208.01 (Tasikmalaya)", "latitude": -7.3275, "longitude": 108.2121},

    # === CENTRAL JAVA (8 stations) ===
    {"name": "SPBU Pertamina 33.301.01 (Semarang)", "latitude": -7.0025, "longitude": 110.4221},
    {"name": "SPBU Pertamina 33.302.01 (Solo)", "latitude": -7.5625, "longitude": 110.8221},
    {"name": "SPBU Pertamina 33.303.01 (Salatiga)", "latitude": -7.3325, "longitude": 110.5021},
    {"name": "SPBU Pertamina 33.304.01 (Purwokerto)", "latitude": -7.4225, "longitude": 109.2321},
    {"name": "SPBU Pertamina 33.305.01 (Tegal)", "latitude": -6.8625, "longitude": 109.1321},
    {"name": "SPBU Pertamina 33.306.01 (Pekalongan)", "latitude": -6.8825, "longitude": 109.6721},
    {"name": "SPBU Pertamina 33.307.01 (Kudus)", "latitude": -6.8025, "longitude": 110.8421},
    {"name": "SPBU Pertamina 33.308.01 (Cilacap)", "latitude": -7.7425, "longitude": 109.0121},

    # === YOGYAKARTA (3 stations) ===
    {"name": "SPBU Pertamina 34.401.01 (Yogyakarta Kota)", "latitude": -7.7975, "longitude": 110.3721},
    {"name": "SPBU Pertamina 34.402.01 (Sleman)", "latitude": -7.7125, "longitude": 110.3921},
    {"name": "SPBU Pertamina 34.403.01 (Bantul)", "latitude": -7.8925, "longitude": 110.3321},

    # === MADURA (3 stations) ===
    {"name": "SPBU Pertamina 35.601.01 (Bangkalan)", "latitude": -7.0325, "longitude": 112.7421},
    {"name": "SPBU Pertamina 35.602.01 (Sampang)", "latitude": -7.1925, "longitude": 113.2421},
    {"name": "SPBU Pertamina 35.603.01 (Pamekasan)", "latitude": -7.1625, "longitude": 113.4721},
]


def generate_java_gas_stations(count: int = 50) -> list[dict]:
    return GAS_STATIONS_SEED_DATA[:count]


async def seed_gas_stations(session: AsyncSession, seed_data: list[dict] = None) -> dict[str, int]:
    dataset = seed_data or GAS_STATIONS_SEED_DATA
    summary = {"created": 0, "existing": 0}

    for item in dataset:
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
    dataset = seed_data or GAS_STATIONS_SEED_DATA
    summary = {"created": 0, "existing": 0}

    for item in dataset:
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
