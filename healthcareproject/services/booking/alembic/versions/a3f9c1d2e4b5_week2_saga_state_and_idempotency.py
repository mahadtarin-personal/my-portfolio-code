"""week2: saga states, active-only slot uniqueness, idempotency keys

Revision ID: a3f9c1d2e4b5
Revises: 05b00519cb7b
Create Date: 2026-08-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f9c1d2e4b5'
down_revision: Union[str, None] = '05b00519cb7b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres native enums require ADD VALUE to run outside a wrapped
    # transaction (Alembic normally wraps every migration in one).
    #
    # Values are uppercase to match the original migration's convention —
    # sa.Enum(PythonEnumClass) stores the member's .name (e.g. "CONFIRMED"),
    # not .value ("confirmed"). Postgres has no ALTER TYPE ... DROP VALUE,
    # so getting this wrong here would permanently pollute the enum type.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE appointment_status ADD VALUE IF NOT EXISTS 'PENDING'")
        op.execute("ALTER TYPE appointment_status ADD VALUE IF NOT EXISTS 'RESERVED'")
        op.execute("ALTER TYPE appointment_status ADD VALUE IF NOT EXISTS 'PAYMENT_PENDING'")
        op.execute("ALTER TYPE appointment_status ADD VALUE IF NOT EXISTS 'FAILED'")

    # The original migration created this via `sa.UniqueConstraint('slot_id')`
    # with no explicit name, so Postgres assigned its default
    # `<table>_<column>_key` naming convention.
    op.drop_constraint("appointments_slot_id_key", "appointments", type_="unique")
    op.create_index(
        "uq_appointments_slot_id_active",
        "appointments",
        ["slot_id"],
        unique=True,
        postgresql_where=sa.text("status NOT IN ('CANCELLED', 'FAILED')"),
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("patient_id", "key", name="uq_idempotency_patient_key"),
    )
    op.create_index(
        op.f("ix_idempotency_keys_patient_id"), "idempotency_keys", ["patient_id"], unique=False
    )
    op.create_index(
        op.f("ix_idempotency_keys_appointment_id"),
        "idempotency_keys",
        ["appointment_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_idempotency_keys_appointment_id"), table_name="idempotency_keys")
    op.drop_index(op.f("ix_idempotency_keys_patient_id"), table_name="idempotency_keys")
    op.drop_table("idempotency_keys")

    op.drop_index("uq_appointments_slot_id_active", table_name="appointments")
    op.create_unique_constraint("appointments_slot_id_key", "appointments", ["slot_id"])

    # Postgres has no ALTER TYPE ... DROP VALUE — downgrading the enum
    # itself would require recreating the type and rewriting the column,
    # which is disproportionate for a dev migration. Left as a no-op; the
    # extra enum values simply remain unused after downgrade.
