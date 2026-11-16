"""job description title and company

Revision ID: 319d33f05a24
Revises: 739663d8d20d
Create Date: 2026-11-16 11:04:52.807091

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '319d33f05a24'
down_revision: Union[str, None] = '739663d8d20d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('job_descriptions', sa.Column('title', sa.String(length=255), nullable=True))
    op.add_column('job_descriptions', sa.Column('company', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('job_descriptions', 'company')
    op.drop_column('job_descriptions', 'title')
