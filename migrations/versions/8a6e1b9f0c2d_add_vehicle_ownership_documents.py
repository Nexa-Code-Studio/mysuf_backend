"""add vehicle ownership documents

Revision ID: 8a6e1b9f0c2d
Revises: 5f2f9f6d2c44
Create Date: 2026-05-23 14:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "8a6e1b9f0c2d"
down_revision: Union[str, Sequence[str], None] = "5f2f9f6d2c44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


vehicle_ownership_document_type_enum = postgresql.ENUM(
    "STNK_PHOTO",
    "VEHICLE_PHOTO",
    "PRODUCTIVE_BUSINESS_PROOF",
    name="vehicle_ownership_document_type_enum",
    create_type=False,
)


def upgrade() -> None:
    vehicle_ownership_document_type_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "vehicle_ownership_documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("vehicle_ownership_id", sa.UUID(), nullable=False),
        sa.Column("document_type", vehicle_ownership_document_type_enum, nullable=False),
        sa.Column("storage_key", sa.String(), nullable=False),
        sa.Column("original_filename", sa.String(), nullable=True),
        sa.Column("mime_type", sa.String(), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("checksum_sha256", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["vehicle_ownership_id"], ["vehicle_ownerships.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "vehicle_ownership_id",
            "document_type",
            name="uq_vehicle_ownership_document_type",
        ),
    )


def downgrade() -> None:
    op.drop_table("vehicle_ownership_documents")
    vehicle_ownership_document_type_enum.drop(op.get_bind(), checkfirst=True)
