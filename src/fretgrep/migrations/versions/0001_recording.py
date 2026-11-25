"""Create the recording table.

Revision ID: 0001
Revises:
"""
# pylint: disable=invalid-name,no-member,duplicate-code

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the change."""
    op.create_table(
        "recording",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recording")),
        sa.UniqueConstraint("content_hash", name=op.f("uq_recording_content_hash")),
    )


def downgrade() -> None:
    """Revert the change."""
    op.drop_table("recording")
