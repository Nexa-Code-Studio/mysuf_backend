"""restructure vehicle_usage_type_enum

Revision ID: g3h4i5j6k7l8
Revises: f2c3d4e5f6g7
Create Date: 2026-05-26 18:00:00.000000

Renames OJOL -> COMMERCIAL_MOTORCYCLE, adds COMMERCIAL_CAR and COMMERCIAL_TRUCK,
and removes obsolete values UMKM and COMPANY_OPERATIONAL by recreating the enum
as a fresh type. This migration is idempotent: it checks the current enum labels
before performing any DDL so it is safe to run on databases that are already
partially or fully migrated.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "g3h4i5j6k7l8"
down_revision: Union[str, Sequence[str], None] = "f2c3d4e5f6g7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TARGET_VALUES = ("PERSONAL", "COMMERCIAL_MOTORCYCLE", "COMMERCIAL_CAR", "COMMERCIAL_TRUCK")


def _current_enum_labels(bind) -> set[str]:
    rows = bind.execute(
        text("SELECT enumlabel FROM pg_enum WHERE enumtypid = 'vehicle_usage_type_enum'::regtype ORDER BY enumsortorder")
    ).fetchall()
    return {r[0] for r in rows}


def upgrade() -> None:
    bind = op.get_bind()
    labels = _current_enum_labels(bind)

    # ------------------------------------------------------------------ #
    # Step 1 – Rename legacy values that map 1-to-1 to new names           #
    # Each ALTER TYPE ... RENAME VALUE must be its own statement and       #
    # committed before any DML that references the new name (asyncpg       #
    # validates enum values at prepare time).                              #
    # ------------------------------------------------------------------ #
    if "OJOL" in labels and "COMMERCIAL_MOTORCYCLE" not in labels:
        bind.execute(text("ALTER TYPE vehicle_usage_type_enum RENAME VALUE 'OJOL' TO 'COMMERCIAL_MOTORCYCLE'"))
        labels = _current_enum_labels(bind)  # refresh

    # Step 2 – ADD missing new values
    for val in ("COMMERCIAL_MOTORCYCLE", "COMMERCIAL_CAR", "COMMERCIAL_TRUCK"):
        if val not in labels:
            bind.execute(text(f"ALTER TYPE vehicle_usage_type_enum ADD VALUE '{val}'"))

    # Step 3 – Migrate data: remap obsolete values to nearest equivalent
    # UMKM -> COMMERCIAL_MOTORCYCLE (closest business intent)
    # COMPANY_OPERATIONAL -> COMMERCIAL_MOTORCYCLE (closest business intent)
    for table in ("vehicle_ownerships", "vehicle_ownership_requests"):
        bind.execute(
            text(f"UPDATE {table} SET usage_type = 'COMMERCIAL_MOTORCYCLE' WHERE usage_type::text = 'UMKM'")
        )
        bind.execute(
            text(f"UPDATE {table} SET usage_type = 'COMMERCIAL_MOTORCYCLE' WHERE usage_type::text = 'COMPANY_OPERATIONAL'")
        )

    # For subsidy_policies, handle the unique constraint by merging obsolete rows
    commercial_motorcycle_policy_id = bind.execute(
        text("SELECT id FROM subsidy_policies WHERE usage_type::text = 'COMMERCIAL_MOTORCYCLE'")
    ).scalar()

    if commercial_motorcycle_policy_id:
        obsolete_policy_ids = [
            r[0] for r in bind.execute(
                text("SELECT id FROM subsidy_policies WHERE usage_type::text IN ('UMKM', 'COMPANY_OPERATIONAL')")
            ).fetchall()
        ]
        if obsolete_policy_ids:
            # Update references in subsidy_quotas
            bind.execute(
                text("UPDATE subsidy_quotas SET subsidy_policy_id = :new_id WHERE subsidy_policy_id = ANY(:old_ids)"),
                {"new_id": commercial_motorcycle_policy_id, "old_ids": obsolete_policy_ids}
            )
            # Delete obsolete policies
            bind.execute(
                text("DELETE FROM subsidy_policies WHERE id = ANY(:old_ids)"),
                {"old_ids": obsolete_policy_ids}
            )
    else:
        # Fallback if COMMERCIAL_MOTORCYCLE policy doesn't exist
        bind.execute(
            text("UPDATE subsidy_policies SET usage_type = 'COMMERCIAL_MOTORCYCLE' WHERE usage_type::text = 'UMKM'")
        )
        bind.execute(
            text("UPDATE subsidy_policies SET usage_type = 'COMMERCIAL_MOTORCYCLE' WHERE usage_type::text = 'COMPANY_OPERATIONAL'")
        )

    # Step 4 – Remove obsolete enum values by recreating the type.
    # PostgreSQL has no DROP VALUE, so we rename the old type, create a new
    # one with the correct values, alter all columns, then drop the old type.
    labels = _current_enum_labels(bind)
    obsolete = labels - set(_TARGET_VALUES)
    if obsolete:
        # Rename old enum so we can create the new one under the canonical name
        bind.execute(text("ALTER TYPE vehicle_usage_type_enum RENAME TO vehicle_usage_type_enum_old"))

        # Create the canonical enum with only the desired values
        bind.execute(text(
            "CREATE TYPE vehicle_usage_type_enum AS ENUM ('PERSONAL', 'COMMERCIAL_MOTORCYCLE', 'COMMERCIAL_CAR', 'COMMERCIAL_TRUCK')"
        ))

        # Alter each column that uses this type
        for table, col in [
            ("vehicle_ownerships", "usage_type"),
            ("vehicle_ownership_requests", "usage_type"),
            ("subsidy_policies", "usage_type"),
        ]:
            bind.execute(text(
                f"ALTER TABLE {table} "
                f"ALTER COLUMN {col} TYPE vehicle_usage_type_enum "
                f"USING {col}::text::vehicle_usage_type_enum"
            ))

        # Drop the old enum
        bind.execute(text("DROP TYPE vehicle_usage_type_enum_old"))


def downgrade() -> None:
    # Reverting a destructive enum restructure is inherently lossy.
    # We re-add the old values but cannot restore deleted rows.
    bind = op.get_bind()
    labels = _current_enum_labels(bind)
    for val in ("OJOL", "UMKM", "COMPANY_OPERATIONAL"):
        if val not in labels:
            bind.execute(text(f"ALTER TYPE vehicle_usage_type_enum ADD VALUE '{val}'"))
