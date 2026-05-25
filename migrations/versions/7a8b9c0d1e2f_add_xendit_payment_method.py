"""add_xendit_payment_method

Revision ID: 7a8b9c0d1e2f
Revises: d4e5f6a7b8c9
Create Date: 2026-05-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "7a8b9c0d1e2f"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE payment_method_enum ADD VALUE IF NOT EXISTS 'XENDIT'")


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely in-place.
    pass