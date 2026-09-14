"""add reminder_log patient_id/provider_id/status

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-08-27 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # add_column doesn't auto-create the backing enum type the way
    # create_table does — create it explicitly first, then reference it
    # without asking SQLAlchemy to create it again.
    reminder_status = sa.Enum('SENT', 'SKIPPED', name='reminder_status')
    reminder_status.create(op.get_bind(), checkfirst=True)

    op.add_column('reminder_log', sa.Column('patient_id', sa.Uuid(), nullable=True))
    op.add_column('reminder_log', sa.Column('provider_id', sa.Uuid(), nullable=True))
    op.add_column(
        'reminder_log',
        sa.Column('status', sa.Enum('SENT', 'SKIPPED', name='reminder_status', create_type=False), nullable=True),
    )

    # Backfill existing rows (all pre-date this column and represent
    # actual sends, the only outcome the old code ever recorded) from
    # appointments — reminder_log.appointment_id already points there.
    op.execute(
        """
        UPDATE reminder_log
        SET patient_id = appointments.patient_id,
            provider_id = appointments.provider_id,
            status = 'SENT'
        FROM appointments
        WHERE reminder_log.appointment_id = appointments.id
        """
    )

    op.alter_column('reminder_log', 'patient_id', nullable=False)
    op.alter_column('reminder_log', 'provider_id', nullable=False)
    op.alter_column('reminder_log', 'status', nullable=False)


def downgrade() -> None:
    op.drop_column('reminder_log', 'status')
    op.drop_column('reminder_log', 'provider_id')
    op.drop_column('reminder_log', 'patient_id')
    sa.Enum(name='reminder_status').drop(op.get_bind(), checkfirst=True)
