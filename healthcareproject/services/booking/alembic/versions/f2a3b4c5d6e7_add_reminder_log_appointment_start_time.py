"""add reminder_log appointment_start_time

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-08-27 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('reminder_log', sa.Column('appointment_start_time', sa.DateTime(timezone=True), nullable=True))

    # Backfill from appointments -> slots (the appointment's own start
    # time never changes after booking, so the current slot's start_time
    # is exactly the value each existing row's own scheduling moment used).
    op.execute(
        """
        UPDATE reminder_log
        SET appointment_start_time = slots.start_time
        FROM appointments
        JOIN slots ON slots.id = appointments.slot_id
        WHERE reminder_log.appointment_id = appointments.id
        """
    )

    op.alter_column('reminder_log', 'appointment_start_time', nullable=False)


def downgrade() -> None:
    op.drop_column('reminder_log', 'appointment_start_time')
