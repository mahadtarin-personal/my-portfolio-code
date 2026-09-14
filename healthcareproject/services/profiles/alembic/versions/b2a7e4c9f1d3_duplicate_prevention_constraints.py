"""duplicate prevention: unique constraints on time_off and clinics

Revision ID: b2a7e4c9f1d3
Revises: bb1e368686bb
Create Date: 2026-08-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b2a7e4c9f1d3'
down_revision: Union[str, None] = 'bb1e368686bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_time_off_provider_range", "time_off", ["provider_id", "start_date", "end_date"]
    )
    op.create_unique_constraint("uq_clinics_name_address", "clinics", ["name", "address"])


def downgrade() -> None:
    op.drop_constraint("uq_clinics_name_address", "clinics", type_="unique")
    op.drop_constraint("uq_time_off_provider_range", "time_off", type_="unique")
