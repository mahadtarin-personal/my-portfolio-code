"""add RESCHEDULED to reminder_status/calendar_sync_action

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-08-28 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4c5d6e7f8a9'
down_revision: Union[str, None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Same rename-recreate-cast pattern as e1f2a3b4c5d6 — Postgres won't
    # let ALTER TYPE ... ADD VALUE be used in the same transaction it's
    # added in.
    op.execute("ALTER TYPE reminder_status RENAME TO reminder_status_old")
    reminder_status = sa.Enum('SCHEDULED', 'SENT', 'SKIPPED', 'RESCHEDULED', name='reminder_status')
    reminder_status.create(op.get_bind())
    op.execute(
        "ALTER TABLE reminder_log ALTER COLUMN status TYPE reminder_status "
        "USING status::text::reminder_status"
    )
    op.execute("DROP TYPE reminder_status_old")

    op.execute("ALTER TYPE calendar_sync_action RENAME TO calendar_sync_action_old")
    calendar_sync_action = sa.Enum('SYNCED', 'REVERTED', 'RESCHEDULED', name='calendar_sync_action')
    calendar_sync_action.create(op.get_bind())
    op.execute(
        "ALTER TABLE calendar_sync_log ALTER COLUMN action TYPE calendar_sync_action "
        "USING action::text::calendar_sync_action"
    )
    op.execute("DROP TYPE calendar_sync_action_old")

    # RESCHEDULED is exempt from the once-per-appointment uniqueness that
    # still applies to SYNCED/REVERTED — see CalendarSyncLog's docstring.
    op.drop_constraint(
        'uq_calendar_sync_log_appointment_action', 'calendar_sync_log', type_='unique'
    )
    op.create_index(
        'uq_calendar_sync_log_appointment_action',
        'calendar_sync_log',
        ['appointment_id', 'action'],
        unique=True,
        postgresql_where=sa.text("action != 'RESCHEDULED'"),
    )


def downgrade() -> None:
    op.drop_index('uq_calendar_sync_log_appointment_action', table_name='calendar_sync_log')
    op.create_unique_constraint(
        'uq_calendar_sync_log_appointment_action', 'calendar_sync_log', ['appointment_id', 'action']
    )

    op.execute("ALTER TYPE calendar_sync_action RENAME TO calendar_sync_action_old")
    calendar_sync_action = sa.Enum('SYNCED', 'REVERTED', name='calendar_sync_action')
    calendar_sync_action.create(op.get_bind())
    op.execute(
        "ALTER TABLE calendar_sync_log ALTER COLUMN action TYPE calendar_sync_action "
        "USING action::text::calendar_sync_action"
    )
    op.execute("DROP TYPE calendar_sync_action_old")

    op.execute("ALTER TYPE reminder_status RENAME TO reminder_status_old")
    reminder_status = sa.Enum('SCHEDULED', 'SENT', 'SKIPPED', name='reminder_status')
    reminder_status.create(op.get_bind())
    op.execute(
        "ALTER TABLE reminder_log ALTER COLUMN status TYPE reminder_status "
        "USING status::text::reminder_status"
    )
    op.execute("DROP TYPE reminder_status_old")
