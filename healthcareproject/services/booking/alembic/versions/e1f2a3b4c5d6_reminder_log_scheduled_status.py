"""reminder_log: add SCHEDULED status + updated_at

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-08-27 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = 'd0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres can't ALTER TYPE ... ADD VALUE and use that value in the
    # same transaction Alembic wraps migrations in — rename the old type
    # out of the way, create a new one with all 3 members, cast the
    # column across via text, drop the old type.
    op.execute("ALTER TYPE reminder_status RENAME TO reminder_status_old")
    new_type = sa.Enum('SCHEDULED', 'SENT', 'SKIPPED', name='reminder_status')
    new_type.create(op.get_bind())
    op.execute(
        "ALTER TABLE reminder_log ALTER COLUMN status TYPE reminder_status "
        "USING status::text::reminder_status"
    )
    op.execute("DROP TYPE reminder_status_old")

    op.add_column('reminder_log', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('reminder_log', 'updated_at')

    op.execute("ALTER TYPE reminder_status RENAME TO reminder_status_old")
    old_type = sa.Enum('SENT', 'SKIPPED', name='reminder_status')
    old_type.create(op.get_bind())
    op.execute(
        "ALTER TABLE reminder_log ALTER COLUMN status TYPE reminder_status "
        "USING status::text::reminder_status"
    )
    op.execute("DROP TYPE reminder_status_old")
