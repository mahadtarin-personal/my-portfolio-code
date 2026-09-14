"""add unique constraint on slots(provider_id, start_time)

Revision ID: d4e9a1f6c2b8
Revises: c7d2e8f1a6b3
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd4e9a1f6c2b8'
down_revision: Union[str, None] = 'c7d2e8f1a6b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint("uq_slots_provider_start", "slots", ["provider_id", "start_time"])


def downgrade() -> None:
    op.drop_constraint("uq_slots_provider_start", "slots", type_="unique")
