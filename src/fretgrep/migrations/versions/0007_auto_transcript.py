"""Create the auto_transcript table.

Revision ID: 0007
Revises: 0006
"""
# pylint: disable=invalid-name,no-member,duplicate-code

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the change."""
    op.create_table(
        "auto_transcript",
        sa.Column("recording_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("language", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["recording.id"],
            name=op.f("fk_auto_transcript_recording_id_recording"),
        ),
        sa.PrimaryKeyConstraint("recording_id", name=op.f("pk_auto_transcript")),
    )


def downgrade() -> None:
    """Revert the change."""
    op.drop_table("auto_transcript")
