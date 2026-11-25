"""Create the auto_tag table.

Revision ID: 0003
Revises: 0002
"""
# pylint: disable=invalid-name,no-member,duplicate-code

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the change."""
    op.create_table(
        "auto_tag",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recording_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("confidence", sa.Double(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("raw_token", sa.String(), nullable=False),
        sa.Column("parser_version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["recording.id"],
            name=op.f("fk_auto_tag_recording_id_recording"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auto_tag")),
        sa.UniqueConstraint(
            "recording_id",
            "category",
            "value",
            "source",
            name="uq_auto_tag_recording_category_value_source",
        ),
    )


def downgrade() -> None:
    """Revert the change."""
    op.drop_table("auto_tag")
