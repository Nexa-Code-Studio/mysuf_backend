"""add usage type policy edit support

Revision ID: 5f2f9f6d2c44
Revises: 0f1c5f4b2d1a
Create Date: 2026-05-23 13:30:00.000000

"""
from datetime import datetime
from decimal import Decimal
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "5f2f9f6d2c44"
down_revision: Union[str, Sequence[str], None] = "0f1c5f4b2d1a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


vehicle_usage_type_enum = postgresql.ENUM(
    "PERSONAL",
    "OJOL",
    "UMKM",
    "COMPANY_OPERATIONAL",
    name="vehicle_usage_type_enum",
    create_type=False,
)

vehicle_quota_mode_enum = postgresql.ENUM(
    "OWNER_PERSONAL_QUOTA",
    "DEDICATED_VEHICLE_QUOTA",
    name="vehicle_quota_mode_enum",
    create_type=False,
)

DEFAULT_POLICY_ROWS = [
    ("Quota Personal", "PERSONAL", Decimal("250.00"), Decimal("250000000.00")),
    ("Quota OJOL", "OJOL", Decimal("250.00"), Decimal("250000000.00")),
    ("Quota UMKM", "UMKM", Decimal("250.00"), Decimal("250000000.00")),
    ("Quota Company Operational", "COMPANY_OPERATIONAL", Decimal("250.00"), Decimal("250000000.00")),
]


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _backfill_subsidy_policies() -> None:
    bind = op.get_bind()
    rows = list(
        bind.execute(
            text(
                """
                SELECT id, monthly_quota_liters, max_allowed_njkb
                FROM subsidy_policies
                ORDER BY created_at NULLS FIRST, id
                """
            )
        ).mappings()
    )

    if len(rows) > len(DEFAULT_POLICY_ROWS):
        raise RuntimeError(
            "Expected at most four existing subsidy policies before usage-type migration."
        )

    if not rows:
        now = datetime.utcnow()
        for name, usage_type, monthly_quota_liters, max_allowed_njkb in DEFAULT_POLICY_ROWS:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO subsidy_policies (id, name, usage_type, monthly_quota_liters, max_allowed_njkb, is_active, created_at, updated_at)
                    VALUES (:id, :name, :usage_type, :monthly_quota_liters, :max_allowed_njkb, :is_active, :created_at, :updated_at)
                    """
                ),
                {
                    "id": uuid4(),
                    "name": name,
                    "usage_type": usage_type,
                    "monthly_quota_liters": monthly_quota_liters,
                    "max_allowed_njkb": max_allowed_njkb,
                    "is_active": True,
                    "created_at": now,
                    "updated_at": now,
                },
            )
        return

    for index, default_policy in enumerate(DEFAULT_POLICY_ROWS):
        name, usage_type, monthly_quota_liters, max_allowed_njkb = default_policy
        if index < len(rows):
            row = rows[index]
            bind.execute(
                sa.text(
                    """
                    UPDATE subsidy_policies
                    SET name = :name,
                        usage_type = :usage_type,
                        monthly_quota_liters = COALESCE(monthly_quota_liters, :monthly_quota_liters),
                        max_allowed_njkb = COALESCE(max_allowed_njkb, :max_allowed_njkb),
                        is_active = TRUE,
                        updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                {
                    "id": row["id"],
                    "name": name,
                    "usage_type": usage_type,
                    "monthly_quota_liters": monthly_quota_liters,
                    "max_allowed_njkb": max_allowed_njkb,
                    "updated_at": datetime.utcnow(),
                },
            )
        else:
            now = datetime.utcnow()
            bind.execute(
                sa.text(
                    """
                    INSERT INTO subsidy_policies (id, name, usage_type, monthly_quota_liters, max_allowed_njkb, is_active, created_at, updated_at)
                    VALUES (:id, :name, :usage_type, :monthly_quota_liters, :max_allowed_njkb, :is_active, :created_at, :updated_at)
                    """
                ),
                {
                    "id": uuid4(),
                    "name": name,
                    "usage_type": usage_type,
                    "monthly_quota_liters": monthly_quota_liters,
                    "max_allowed_njkb": max_allowed_njkb,
                    "is_active": True,
                    "created_at": now,
                    "updated_at": now,
                },
            )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    vehicle_usage_type_enum.create(bind, checkfirst=True)
    vehicle_quota_mode_enum.create(bind, checkfirst=True)

    op.add_column(
        "vehicle_ownerships",
        sa.Column(
            "usage_type",
            sa.Enum(
                "PERSONAL",
                "OJOL",
                "UMKM",
                "COMPANY_OPERATIONAL",
                name="vehicle_usage_type_enum",
                create_type=False,
            ),
            nullable=True,
            server_default="PERSONAL",
        ),
    )
    op.add_column(
        "vehicle_ownerships",
        sa.Column(
            "quota_mode",
            sa.Enum(
                "OWNER_PERSONAL_QUOTA",
                "DEDICATED_VEHICLE_QUOTA",
                name="vehicle_quota_mode_enum",
                create_type=False,
            ),
            nullable=True,
            server_default="OWNER_PERSONAL_QUOTA",
        ),
    )
    op.add_column("subsidy_policies", sa.Column("name", sa.String(), nullable=True))
    op.add_column(
        "subsidy_policies",
        sa.Column(
            "usage_type",
            sa.Enum(
                "PERSONAL",
                "OJOL",
                "UMKM",
                "COMPANY_OPERATIONAL",
                name="vehicle_usage_type_enum",
                create_type=False,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "subsidy_quotas",
        sa.Column("subsidy_policy_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        op.f("subsidy_quotas_subsidy_policy_id_fkey"),
        "subsidy_quotas",
        "subsidy_policies",
        ["subsidy_policy_id"],
        ["id"],
    )

    op.execute(
        text(
            "UPDATE vehicle_ownerships SET usage_type = 'PERSONAL' WHERE usage_type IS NULL"
        )
    )
    op.execute(
        text(
            "UPDATE vehicle_ownerships SET quota_mode = 'OWNER_PERSONAL_QUOTA' WHERE quota_mode IS NULL"
        )
    )

    _backfill_subsidy_policies()

    personal_policy_id = bind.execute(
        text(
            "SELECT id FROM subsidy_policies WHERE usage_type = 'PERSONAL'"
        )
    ).scalar_one()
    bind.execute(
        text(
            """
            UPDATE subsidy_quotas
            SET subsidy_policy_id = :personal_policy_id
            WHERE subsidy_policy_id IS NULL AND owner_type = 'BUYER_PROFILE'
            """
        ),
        {"personal_policy_id": personal_policy_id},
    )

    op.alter_column("vehicle_ownerships", "usage_type", nullable=False, server_default=None)
    op.alter_column("vehicle_ownerships", "quota_mode", nullable=False, server_default=None)
    op.alter_column("subsidy_policies", "name", nullable=False)
    op.alter_column("subsidy_policies", "usage_type", nullable=False)

    op.create_unique_constraint(
        "uq_subsidy_policies_usage_type",
        "subsidy_policies",
        ["usage_type"],
    )
    op.create_unique_constraint(
        "uq_subsidy_quotas_owner_month",
        "subsidy_quotas",
        ["owner_type", "owner_id", "month", "year"],
    )

    vehicle_ownership_indexes = _index_names(inspector, "vehicle_ownerships")
    if "ix_vehicle_ownerships_usage_type" not in vehicle_ownership_indexes:
        op.create_index("ix_vehicle_ownerships_usage_type", "vehicle_ownerships", ["usage_type"], unique=False)
    if "ix_vehicle_ownerships_quota_mode" not in vehicle_ownership_indexes:
        op.create_index("ix_vehicle_ownerships_quota_mode", "vehicle_ownerships", ["quota_mode"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    vehicle_ownership_indexes = _index_names(inspector, "vehicle_ownerships")
    if "ix_vehicle_ownerships_quota_mode" in vehicle_ownership_indexes:
        op.drop_index("ix_vehicle_ownerships_quota_mode", table_name="vehicle_ownerships")
    if "ix_vehicle_ownerships_usage_type" in vehicle_ownership_indexes:
        op.drop_index("ix_vehicle_ownerships_usage_type", table_name="vehicle_ownerships")

    op.drop_constraint("uq_subsidy_quotas_owner_month", "subsidy_quotas", type_="unique")
    op.drop_constraint("uq_subsidy_policies_usage_type", "subsidy_policies", type_="unique")
    op.drop_constraint(op.f("subsidy_quotas_subsidy_policy_id_fkey"), "subsidy_quotas", type_="foreignkey")
    op.drop_column("subsidy_quotas", "subsidy_policy_id")
    op.drop_column("subsidy_policies", "usage_type")
    op.drop_column("subsidy_policies", "name")
    op.drop_column("vehicle_ownerships", "quota_mode")
    op.drop_column("vehicle_ownerships", "usage_type")

    vehicle_quota_mode_enum.drop(bind, checkfirst=True)
    vehicle_usage_type_enum.drop(bind, checkfirst=True)
