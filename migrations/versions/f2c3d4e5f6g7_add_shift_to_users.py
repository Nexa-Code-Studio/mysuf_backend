"""add shift to users

Revision ID: f2c3d4e5f6g7
Revises: 7ab922849297
Create Date: 2026-05-26 15:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2c3d4e5f6g7'
down_revision: Union[str, Sequence[str], None] = '7ab922849297'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('shift', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'shift')
