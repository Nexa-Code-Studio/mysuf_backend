from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.modules.fuels.models import FuelType, FuelCategory, SubsidyType

# Indonesia Real-world Fuel Types Data
FUEL_TYPES_SEED_DATA = [
    {
        "name": "Pertalite",
        "octane": "90",
        "category": FuelCategory.GASOLINE,
        "price_per_liter": Decimal("10000.00"),
        "subsidy_price_per_liter": Decimal("10000.00"),
        "subsidy_type": SubsidyType.SUBSIDIZED,
    },
    {
        "name": "Pertamax",
        "octane": "92",
        "category": FuelCategory.GASOLINE,
        "price_per_liter": Decimal("12950.00"),
        "subsidy_price_per_liter": None,
        "subsidy_type": SubsidyType.NON_SUBSIDIZED,
    },
    {
        "name": "Pertamax Turbo",
        "octane": "98",
        "category": FuelCategory.GASOLINE,
        "price_per_liter": Decimal("14400.00"),
        "subsidy_price_per_liter": None,
        "subsidy_type": SubsidyType.NON_SUBSIDIZED,
    },
    {
        "name": "Solar Subsidi / Biosolar",
        "octane": "CN 48",
        "category": FuelCategory.DIESEL,
        "price_per_liter": Decimal("6800.00"),
        "subsidy_price_per_liter": Decimal("6800.00"),
        "subsidy_type": SubsidyType.SUBSIDIZED,
    },
    {
        "name": "Dexlite",
        "octane": "CN 51",
        "category": FuelCategory.DIESEL,
        "price_per_liter": Decimal("14550.00"),
        "subsidy_price_per_liter": None,
        "subsidy_type": SubsidyType.NON_SUBSIDIZED,
    },
    {
        "name": "Pertamina Dex",
        "octane": "CN 53",
        "category": FuelCategory.DIESEL,
        "price_per_liter": Decimal("15100.00"),
        "subsidy_price_per_liter": None,
        "subsidy_type": SubsidyType.NON_SUBSIDIZED,
    },
]

async def seed_fuel_types(session: AsyncSession, seed_data: list[dict] = None) -> dict[str, int]:
    """
    Asynchronous seeder to match the existing async session patterns of the project.
    """
    dataset = seed_data or FUEL_TYPES_SEED_DATA
    summary = {"created": 0, "existing": 0}

    for item in dataset:
        # Check if the fuel type already exists by name
        result = await session.execute(
            select(FuelType).filter(FuelType.name == item["name"])
        )
        existing = result.scalars().first()

        if existing is None:
            fuel = FuelType(
                name=item["name"],
                octane=item["octane"],
                category=item["category"],
                price_per_liter=item["price_per_liter"],
                subsidy_price_per_liter=item["subsidy_price_per_liter"],
                subsidy_type=item["subsidy_type"],
            )
            session.add(fuel)
            summary["created"] += 1
        else:
            summary["existing"] += 1

    await session.commit()
    return summary

def seed_fuel_types_sync(db: Session, seed_data: list[dict] = None) -> dict[str, int]:
    """
    Synchronous seeder as requested in the prompt using a standard SQLAlchemy Session.
    """
    dataset = seed_data or FUEL_TYPES_SEED_DATA
    summary = {"created": 0, "existing": 0}

    for item in dataset:
        # Check if the fuel type already exists by name
        existing = db.query(FuelType).filter(FuelType.name == item["name"]).first()

        if existing is None:
            fuel = FuelType(
                name=item["name"],
                octane=item["octane"],
                category=item["category"],
                price_per_liter=item["price_per_liter"],
                subsidy_price_per_liter=item["subsidy_price_per_liter"],
                subsidy_type=item["subsidy_type"],
            )
            db.add(fuel)
            summary["created"] += 1
        else:
            summary["existing"] += 1

    db.commit()
    return summary
