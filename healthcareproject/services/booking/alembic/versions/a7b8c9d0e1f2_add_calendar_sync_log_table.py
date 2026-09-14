"""add calendar_sync_log table

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'calendar_sync_log',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('appointment_id', sa.Uuid(), nullable=False),
        sa.Column('provider_id', sa.Uuid(), nullable=False),
        sa.Column('action', sa.Enum('SYNCED', 'REVERTED', name='calendar_sync_action'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'appointment_id', 'action', name='uq_calendar_sync_log_appointment_action'
        ),
    )
    op.create_index(
        op.f('ix_calendar_sync_log_appointment_id'), 'calendar_sync_log', ['appointment_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_calendar_sync_log_appointment_id'), table_name='calendar_sync_log')
    op.drop_table('calendar_sync_log')
