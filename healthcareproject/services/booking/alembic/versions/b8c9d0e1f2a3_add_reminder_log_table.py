"""add reminder_log table

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-08-27 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'reminder_log',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('appointment_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('appointment_id', name='uq_reminder_log_appointment_id'),
    )
    op.create_index(op.f('ix_reminder_log_appointment_id'), 'reminder_log', ['appointment_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_reminder_log_appointment_id'), table_name='reminder_log')
    op.drop_table('reminder_log')
