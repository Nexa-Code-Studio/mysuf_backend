"""add_cashier_scan_events

Revision ID: d4e5f6a7b8c9
Revises: 3e4a9b7c1d2f
Create Date: 2026-05-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "3e4a9b7c1d2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


cashier_scan_method_enum = ENUM(
    "NFC",
    "NIK",
    "QR",
    name="cashier_scan_method_enum",
    create_type=False,
)
cashier_scan_result_enum = ENUM(
    "SUCCESS",
    "FAILED",
    name="cashier_scan_result_enum",
    create_type=False,
)


def upgrade() -> None:
    cashier_scan_method_enum.create(op.get_bind(), checkfirst=True)
    cashier_scan_result_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "cashier_scan_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cashier_user_id", sa.UUID(), nullable=False),
        sa.Column("gas_station_id", sa.UUID(), nullable=True),
        sa.Column("lookup_method", cashier_scan_method_enum, nullable=False),
        sa.Column("lookup_value", sa.String(), nullable=False),
        sa.Column("result", cashier_scan_result_enum, nullable=False),
        sa.Column("buyer_profile_id", sa.UUID(), nullable=True),
        sa.Column("vehicle_ownership_id", sa.UUID(), nullable=True),
        sa.Column("fuel_transaction_id", sa.UUID(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["buyer_profile_id"], ["buyer_profiles.id"]),
        sa.ForeignKeyConstraint(["cashier_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["fuel_transaction_id"], ["fuel_transactions.id"]),
        sa.ForeignKeyConstraint(["gas_station_id"], ["gas_stations.id"]),
        sa.ForeignKeyConstraint(["vehicle_ownership_id"], ["vehicle_ownerships.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cashier_scan_events_cashier_created_at",
        "cashier_scan_events",
        ["cashier_user_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_cashier_scan_events_gas_station_created_at",
        "cashier_scan_events",
        ["gas_station_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_cashier_scan_events_gas_station_created_at", table_name="cashier_scan_events")
    op.drop_index("ix_cashier_scan_events_cashier_created_at", table_name="cashier_scan_events")
    op.drop_table("cashier_scan_events")
    cashier_scan_result_enum.drop(op.get_bind(), checkfirst=True)
    cashier_scan_method_enum.drop(op.get_bind(), checkfirst=True)
