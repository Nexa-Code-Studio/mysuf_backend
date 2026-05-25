from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import settings


def upgrade_database() -> None:
    base_dir = Path(__file__).resolve().parents[2]
    alembic_config = Config(str(base_dir / "alembic.ini"))
    alembic_config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    command.upgrade(alembic_config, "head")


async def ensure_database_schema() -> None:
    await asyncio.to_thread(upgrade_database)