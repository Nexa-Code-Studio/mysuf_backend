"""add buyer registration verification fields

Revision ID: 26a18b757f54
Revises: a97d72891e92
Create Date: 2026-05-23 07:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '26a18b757f54'
down_revision: Union[str, Sequence[str], None] = 'a97d72891e92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('buyer_registration_attempts', sa.Column('ocr_raw_text', sa.Text(), nullable=True))
    op.add_column('buyer_registration_attempts', sa.Column('verification_detail', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('buyer_registration_attempts', 'verification_detail')
    op.drop_column('buyer_registration_attempts', 'ocr_raw_text')
