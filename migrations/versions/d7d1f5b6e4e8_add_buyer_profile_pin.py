"""add buyer profile pin

Revision ID: d7d1f5b6e4e8
Revises: 9c1d7b4a2f10
Create Date: 2026-05-24 13:02:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d7d1f5b6e4e8"
down_revision: Union[str, Sequence[str], None] = "9c1d7b4a2f10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "buyer_profiles",
        sa.Column("pin_hash", sa.String(), nullable=True),
    )
    op.add_column(
        "buyer_profiles",
        sa.Column("is_pin_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("buyer_profiles", "is_pin_active")
    op.drop_column("buyer_profiles", "pin_hash")
