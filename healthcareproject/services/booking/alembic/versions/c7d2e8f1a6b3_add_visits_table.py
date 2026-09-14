"""add visits table

Revision ID: c7d2e8f1a6b3
Revises: a3f9c1d2e4b5
Create Date: 2026-08-17 00:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d2e8f1a6b3'
down_revision: Union[str, None] = 'a3f9c1d2e4b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'visits',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('appointment_id', sa.Uuid(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('CHECKED_IN', 'IN_PROGRESS', 'COMPLETED', name='visit_status'),
            nullable=False,
        ),
        sa.Column('checked_in_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('appointment_id'),
    )


def downgrade() -> None:
    op.drop_table('visits')
    op.execute("DROP TYPE IF EXISTS visit_status")
