"""add_qris_payment_transaction_fields

Revision ID: 3e4a9b7c1d2f
Revises: e20f8282e1f2
Create Date: 2026-05-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3e4a9b7c1d2f'
down_revision: Union[str, Sequence[str], None] = 'e20f8282e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('payment_transactions', sa.Column('fuel_transaction_id', sa.UUID(), nullable=True))
    op.add_column('payment_transactions', sa.Column('qr_string', sa.String(), nullable=True))
    op.add_column('payment_transactions', sa.Column('expires_at', sa.DateTime(), nullable=True))
    op.create_foreign_key(
        None,
        'payment_transactions',
        'fuel_transactions',
        ['fuel_transaction_id'],
        ['id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(None, 'payment_transactions', type_='foreignkey')
    op.drop_column('payment_transactions', 'expires_at')
    op.drop_column('payment_transactions', 'qr_string')
    op.drop_column('payment_transactions', 'fuel_transaction_id')
