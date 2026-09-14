"""add reminder_log appointment_status

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-08-27 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('reminder_log', sa.Column('appointment_status', sa.String(length=32), nullable=True))

    # Backfill from appointments' CURRENT status — the best available
    # approximation for rows written before this column existed (all of
    # which recorded status='SENT', so the observed status at the time
    # was, at minimum, CONFIRMED; a later cancellation would just make
    # this backfilled value diverge from that historical moment, same
    # caveat as the patient_id/provider_id backfill in c9d0e1f2a3b4).
    op.execute(
        """
        UPDATE reminder_log
        SET appointment_status = lower(appointments.status::text)
        FROM appointments
        WHERE reminder_log.appointment_id = appointments.id
        """
    )

    op.alter_column('reminder_log', 'appointment_status', nullable=False)


def downgrade() -> None:
    op.drop_column('reminder_log', 'appointment_status')
