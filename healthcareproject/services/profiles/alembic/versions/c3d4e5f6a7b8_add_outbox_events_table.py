"""add outbox_events table

Revision ID: c3d4e5f6a7b8
Revises: b2a7e4c9f1d3
Create Date: 2026-08-25 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2a7e4c9f1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'outbox_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event_id', sa.String(length=64), nullable=False),
        sa.Column('topic', sa.String(length=64), nullable=False),
        sa.Column('actor', sa.String(length=255), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_outbox_events_event_id'), 'outbox_events', ['event_id'], unique=True)
    op.create_index(
        'ix_outbox_events_unpublished', 'outbox_events', ['published_at'], unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_outbox_events_unpublished', table_name='outbox_events')
    op.drop_index(op.f('ix_outbox_events_event_id'), table_name='outbox_events')
    op.drop_table('outbox_events')
