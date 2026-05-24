"""add buyer profile risk score

Revision ID: f1b2c3d4e5f6
Revises: c3b4a6f8d912
Create Date: 2026-05-24 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "c3b4a6f8d912"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "buyer_profiles",
        sa.Column("risk_score", sa.Numeric(precision=5, scale=2), nullable=True, server_default="0"),
    )
    op.alter_column("buyer_profiles", "risk_score", nullable=False, server_default=None)


def downgrade() -> None:
    op.drop_column("buyer_profiles", "risk_score")
