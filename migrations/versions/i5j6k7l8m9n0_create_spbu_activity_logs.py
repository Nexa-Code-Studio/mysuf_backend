"""create spbu activity logs

Revision ID: i5j6k7l8m9n0
Revises: h4i5j6k7l8m9
Create Date: 2026-06-13 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM, UUID

# revision identifiers, used by Alembic.
revision: str = 'i5j6k7l8m9n0'
down_revision: Union[str, Sequence[str], None] = 'h4i5j6k7l8m9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

spbu_activity_category_enum = ENUM(
    'Sistem',
    'Penjualan',
    'Keamanan',
    name='spbu_activity_category_enum',
    create_type=False,
)

def upgrade() -> None:
    # Create enum type if it does not exist
    spbu_activity_category_enum.create(op.get_bind(), checkfirst=True)

    # Create table
    op.create_table(
        'spbu_activity_logs',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('gas_station_id', UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), nullable=True),
        sa.Column('category', spbu_activity_category_enum, nullable=False),
        sa.Column('detail', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['gas_station_id'], ['gas_stations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    # Create index on gas_station_id
    op.create_index('ix_spbu_activity_logs_gas_station_id', 'spbu_activity_logs', ['gas_station_id'], unique=False)


def downgrade() -> None:
    # Drop index
    op.drop_index('ix_spbu_activity_logs_gas_station_id', table_name='spbu_activity_logs')
    # Drop table
    op.drop_table('spbu_activity_logs')
    # Drop enum
    spbu_activity_category_enum.drop(op.get_bind(), checkfirst=True)
