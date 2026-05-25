"""add buyer profile nfc lookup index

Revision ID: 91b7f6e2a1c4
Revises: c576c7c7964f
Create Date: 2026-05-25 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "91b7f6e2a1c4"
down_revision: Union[str, Sequence[str], None] = "c576c7c7964f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_buyer_profiles_ktp_nfc_id_snapshot",
        "buyer_profiles",
        ["ktp_nfc_id_snapshot"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_buyer_profiles_ktp_nfc_id_snapshot", table_name="buyer_profiles")
