"""initial schema

Revision ID: b1c2d3e4f5a6
Revises:
Create Date: 2026-08-25 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event_id', sa.String(length=64), nullable=False),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('actor', sa.String(length=255), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('prev_hash', sa.String(length=64), nullable=False),
        sa.Column('hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_audit_log_event_id'), 'audit_log', ['event_id'], unique=True)
    op.create_index(op.f('ix_audit_log_hash'), 'audit_log', ['hash'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_audit_log_hash'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_event_id'), table_name='audit_log')
    op.drop_table('audit_log')
