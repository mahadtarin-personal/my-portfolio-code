"""initial schema

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-08-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notifications',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('event_id', sa.String(length=64), nullable=False),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('recipient', sa.String(length=255), nullable=False),
        sa.Column('channel', sa.Enum('EMAIL', 'SMS', name='notification_channel'), nullable=False),
        sa.Column('status', sa.Enum('SENT', 'FAILED', name='notification_status'), nullable=False),
        sa.Column('message', sa.String(length=1000), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id', name='uq_notifications_event_id'),
    )
    op.create_index(op.f('ix_notifications_event_id'), 'notifications', ['event_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_notifications_event_id'), table_name='notifications')
    op.drop_table('notifications')
