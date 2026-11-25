"""Create the auto_notes table.

Revision ID: 0010
Revises: 0009
"""
# pylint: disable=invalid-name,no-member,duplicate-code

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the change."""
    op.create_table(
        "auto_notes",
        sa.Column("recording_id", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("notes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["recording.id"],
            name=op.f("fk_auto_notes_recording_id_recording"),
        ),
        sa.PrimaryKeyConstraint("recording_id", name=op.f("pk_auto_notes")),
    )


def downgrade() -> None:
    """Revert the change."""
    op.drop_table("auto_notes")
