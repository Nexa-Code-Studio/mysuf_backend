"""remove kk vehicles and add vehicle indexes

Revision ID: 0f1c5f4b2d1a
Revises: 26a18b757f54
Create Date: 2026-05-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0f1c5f4b2d1a"
down_revision: Union[str, Sequence[str], None] = "26a18b757f54"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


kk_vehicle_ownership_status_enum = postgresql.ENUM(
    "OWNED",
    "FAMILY_OWNED",
    "COMPANY_OWNED",
    name="kk_vehicle_ownership_status_enum",
    create_type=False,
)


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table("kk_vehicles"):
        op.drop_table("kk_vehicles")

    kk_vehicle_ownership_status_enum.drop(bind, checkfirst=True)

    vehicle_registry_indexes = _index_names(inspector, "vehicle_registry_mockup")
    if "ix_vehicle_registry_mockup_plate_number" not in vehicle_registry_indexes:
        op.create_index(
            "ix_vehicle_registry_mockup_plate_number",
            "vehicle_registry_mockup",
            ["plate_number"],
            unique=False,
        )
    if "ix_vehicle_registry_mockup_registration_number" not in vehicle_registry_indexes:
        op.create_index(
            "ix_vehicle_registry_mockup_registration_number",
            "vehicle_registry_mockup",
            ["registration_number"],
            unique=False,
        )
    if "ix_vehicle_registry_mockup_owner_nik" not in vehicle_registry_indexes:
        op.create_index(
            "ix_vehicle_registry_mockup_owner_nik",
            "vehicle_registry_mockup",
            ["owner_nik"],
            unique=False,
        )

    vehicle_ownership_indexes = _index_names(inspector, "vehicle_ownerships")
    if "ix_vehicle_ownerships_vehicle_id" not in vehicle_ownership_indexes:
        op.create_index(
            "ix_vehicle_ownerships_vehicle_id",
            "vehicle_ownerships",
            ["vehicle_id"],
            unique=False,
        )
    if "ix_vehicle_ownerships_ktp_nfc_id_snapshot" not in vehicle_ownership_indexes:
        op.create_index(
            "ix_vehicle_ownerships_ktp_nfc_id_snapshot",
            "vehicle_ownerships",
            ["ktp_nfc_id_snapshot"],
            unique=False,
        )
    if "ix_vehicle_ownerships_owner_type_owner_id" not in vehicle_ownership_indexes:
        op.create_index(
            "ix_vehicle_ownerships_owner_type_owner_id",
            "vehicle_ownerships",
            ["owner_type", "owner_id"],
            unique=False,
        )

    buyer_profile_indexes = _index_names(inspector, "buyer_profiles")
    if "ix_buyer_profiles_kk_id" not in buyer_profile_indexes:
        op.create_index("ix_buyer_profiles_kk_id", "buyer_profiles", ["kk_id"], unique=False)

    kk_eligibility_indexes = _index_names(inspector, "kk_subsidy_eligibilities")
    if "ix_kk_subsidy_eligibilities_kk_id" not in kk_eligibility_indexes:
        op.create_index(
            "ix_kk_subsidy_eligibilities_kk_id",
            "kk_subsidy_eligibilities",
            ["kk_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    kk_eligibility_indexes = _index_names(inspector, "kk_subsidy_eligibilities")
    if "ix_kk_subsidy_eligibilities_kk_id" in kk_eligibility_indexes:
        op.drop_index("ix_kk_subsidy_eligibilities_kk_id", table_name="kk_subsidy_eligibilities")

    buyer_profile_indexes = _index_names(inspector, "buyer_profiles")
    if "ix_buyer_profiles_kk_id" in buyer_profile_indexes:
        op.drop_index("ix_buyer_profiles_kk_id", table_name="buyer_profiles")

    vehicle_ownership_indexes = _index_names(inspector, "vehicle_ownerships")
    if "ix_vehicle_ownerships_owner_type_owner_id" in vehicle_ownership_indexes:
        op.drop_index("ix_vehicle_ownerships_owner_type_owner_id", table_name="vehicle_ownerships")
    if "ix_vehicle_ownerships_ktp_nfc_id_snapshot" in vehicle_ownership_indexes:
        op.drop_index("ix_vehicle_ownerships_ktp_nfc_id_snapshot", table_name="vehicle_ownerships")
    if "ix_vehicle_ownerships_vehicle_id" in vehicle_ownership_indexes:
        op.drop_index("ix_vehicle_ownerships_vehicle_id", table_name="vehicle_ownerships")

    vehicle_registry_indexes = _index_names(inspector, "vehicle_registry_mockup")
    if "ix_vehicle_registry_mockup_owner_nik" in vehicle_registry_indexes:
        op.drop_index("ix_vehicle_registry_mockup_owner_nik", table_name="vehicle_registry_mockup")
    if "ix_vehicle_registry_mockup_registration_number" in vehicle_registry_indexes:
        op.drop_index(
            "ix_vehicle_registry_mockup_registration_number",
            table_name="vehicle_registry_mockup",
        )
    if "ix_vehicle_registry_mockup_plate_number" in vehicle_registry_indexes:
        op.drop_index("ix_vehicle_registry_mockup_plate_number", table_name="vehicle_registry_mockup")

    kk_vehicle_ownership_status_enum.create(bind, checkfirst=True)
    op.create_table(
        "kk_vehicles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("kk_id", sa.UUID(), nullable=False),
        sa.Column("vehicle_id", sa.UUID(), nullable=False),
        sa.Column("ownership_status", kk_vehicle_ownership_status_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["kk_id"], ["kk.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
