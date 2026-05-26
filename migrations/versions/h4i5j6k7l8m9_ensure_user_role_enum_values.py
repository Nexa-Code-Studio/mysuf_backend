"""ensure user_role_enum has all required values

Revision ID: h4i5j6k7l8m9
Revises: g3h4i5j6k7l8
Create Date: 2026-05-26 18:30:00.000000

Ensures user_role_enum contains all required role values.
This migration is idempotent - it only adds values that are missing.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "h4i5j6k7l8m9"
down_revision: Union[str, Sequence[str], None] = "g3h4i5j6k7l8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_REQUIRED_ROLES = (
    "SUPER_ADMIN",
    "SPBU_ADMIN",
    "GOV_ADMIN",
    "COMPANY_ADMIN",
    "SALES_OFFICER",
    "BUYER",
)


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        text("SELECT enumlabel FROM pg_enum WHERE enumtypid = 'user_role_enum'::regtype")
    ).fetchall()
    existing = {r[0] for r in rows}

    for role in _REQUIRED_ROLES:
        if role not in existing:
            bind.execute(text(f"ALTER TYPE user_role_enum ADD VALUE '{role}'"))


def downgrade() -> None:
    # Enum values cannot be dropped in PostgreSQL without recreating the type.
    pass
