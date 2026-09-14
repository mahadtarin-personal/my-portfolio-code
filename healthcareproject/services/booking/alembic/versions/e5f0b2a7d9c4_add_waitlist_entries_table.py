"""add waitlist_entries table

Revision ID: e5f0b2a7d9c4
Revises: d4e9a1f6c2b8
Create Date: 2026-08-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f0b2a7d9c4'
down_revision: Union[str, None] = 'd4e9a1f6c2b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'waitlist_entries',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('patient_id', sa.Uuid(), nullable=False),
        sa.Column('provider_id', sa.Uuid(), nullable=False),
        sa.Column('slot_id', sa.Uuid(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('WAITING', 'FULFILLED', 'CANCELLED', name='waitlist_status'),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_waitlist_entries_patient_id'), 'waitlist_entries', ['patient_id'], unique=False
    )
    op.create_index(
        op.f('ix_waitlist_entries_provider_id'), 'waitlist_entries', ['provider_id'], unique=False
    )
    op.create_index(
        op.f('ix_waitlist_entries_slot_id'), 'waitlist_entries', ['slot_id'], unique=False
    )
    op.create_index(
        'uq_waitlist_patient_slot_active',
        'waitlist_entries',
        ['patient_id', 'slot_id'],
        unique=True,
        postgresql_where=sa.text("status = 'WAITING'"),
    )


def downgrade() -> None:
    op.drop_index('uq_waitlist_patient_slot_active', table_name='waitlist_entries')
    op.drop_index(op.f('ix_waitlist_entries_slot_id'), table_name='waitlist_entries')
    op.drop_index(op.f('ix_waitlist_entries_provider_id'), table_name='waitlist_entries')
    op.drop_index(op.f('ix_waitlist_entries_patient_id'), table_name='waitlist_entries')
    op.drop_table('waitlist_entries')
