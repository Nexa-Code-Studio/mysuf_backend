"""update gas station coords and wallet transaction types

Revision ID: 9c1d7b4a2f10
Revises: e20f8282e1f2
Create Date: 2026-05-24 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9c1d7b4a2f10"
down_revision: Union[str, Sequence[str], None] = "e20f8282e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "gas_stations",
        "latitude",
        type_=sa.Float(),
        postgresql_using="latitude::double precision",
        existing_nullable=False,
    )
    op.alter_column(
        "gas_stations",
        "longitude",
        type_=sa.Float(),
        postgresql_using="longitude::double precision",
        existing_nullable=False,
    )

    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'FUEL_PURCHASE'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'ADMIN_ADJUSTMENT'")


def downgrade() -> None:
    op.alter_column(
        "gas_stations",
        "longitude",
        type_=sa.String(),
        postgresql_using="longitude::text",
        existing_nullable=False,
    )
    op.alter_column(
        "gas_stations",
        "latitude",
        type_=sa.String(),
        postgresql_using="latitude::text",
        existing_nullable=False,
    )
