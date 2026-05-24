"""add vehicle ownership requests

Revision ID: c3b4a6f8d912
Revises: 8a6e1b9f0c2d
Create Date: 2026-05-23 15:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c3b4a6f8d912"
down_revision: Union[str, Sequence[str], None] = "8a6e1b9f0c2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


vehicle_ownership_request_status_enum = postgresql.ENUM(
    "PENDING",
    "UNDER_REVIEW",
    "APPROVED",
    "REJECTED",
    name="vehicle_ownership_request_status_enum",
    create_type=False,
)

vehicle_ownership_status_enum = postgresql.ENUM(
    "PERSONAL",
    "COMPANY",
    name="vehicle_ownership_status_enum",
    create_type=False,
)

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

vehicle_ownership_document_type_enum = postgresql.ENUM(
    "STNK_PHOTO",
    "VEHICLE_PHOTO",
    "PRODUCTIVE_BUSINESS_PROOF",
    name="vehicle_ownership_document_type_enum",
    create_type=False,
)


def upgrade() -> None:
    vehicle_ownership_request_status_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "vehicle_ownership_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("buyer_profile_id", sa.UUID(), nullable=False),
        sa.Column("vehicle_id", sa.UUID(), nullable=False),
        sa.Column("ownership_status", vehicle_ownership_status_enum, nullable=False),
        sa.Column("usage_type", vehicle_usage_type_enum, nullable=False),
        sa.Column("quota_mode", vehicle_quota_mode_enum, nullable=False),
        sa.Column("plate_number_snapshot", sa.String(), nullable=False),
        sa.Column("ktp_nfc_id_snapshot", sa.String(), nullable=False),
        sa.Column("status", vehicle_ownership_request_status_enum, nullable=False),
        sa.Column("review_note", sa.String(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.UUID(), nullable=True),
        sa.Column("approved_vehicle_ownership_id", sa.UUID(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["approved_vehicle_ownership_id"], ["vehicle_ownerships.id"]),
        sa.ForeignKeyConstraint(["buyer_profile_id"], ["buyer_profiles.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vehicle_ownership_requests_buyer_profile_id", "vehicle_ownership_requests", ["buyer_profile_id"], unique=False)
    op.create_index("ix_vehicle_ownership_requests_vehicle_id", "vehicle_ownership_requests", ["vehicle_id"], unique=False)
    op.create_index("ix_vehicle_ownership_requests_usage_type", "vehicle_ownership_requests", ["usage_type"], unique=False)
    op.create_index("ix_vehicle_ownership_requests_status", "vehicle_ownership_requests", ["status"], unique=False)

    op.create_table(
        "vehicle_ownership_request_documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("vehicle_ownership_request_id", sa.UUID(), nullable=False),
        sa.Column("document_type", vehicle_ownership_document_type_enum, nullable=False),
        sa.Column("storage_key", sa.String(), nullable=False),
        sa.Column("original_filename", sa.String(), nullable=True),
        sa.Column("mime_type", sa.String(), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("checksum_sha256", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["vehicle_ownership_request_id"], ["vehicle_ownership_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "vehicle_ownership_request_id",
            "document_type",
            name="uq_vehicle_ownership_request_document_type",
        ),
    )


def downgrade() -> None:
    op.drop_table("vehicle_ownership_request_documents")
    op.drop_index("ix_vehicle_ownership_requests_status", table_name="vehicle_ownership_requests")
    op.drop_index("ix_vehicle_ownership_requests_usage_type", table_name="vehicle_ownership_requests")
    op.drop_index("ix_vehicle_ownership_requests_vehicle_id", table_name="vehicle_ownership_requests")
    op.drop_index("ix_vehicle_ownership_requests_buyer_profile_id", table_name="vehicle_ownership_requests")
    op.drop_table("vehicle_ownership_requests")
    vehicle_ownership_request_status_enum.drop(op.get_bind(), checkfirst=True)
