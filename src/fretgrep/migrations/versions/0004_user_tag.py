"""Create the user_tag table.

Revision ID: 0004
Revises: 0003
"""
# pylint: disable=invalid-name,no-member,duplicate-code

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def _refuse_if_not_empty(table: str) -> None:
    """User data must never be dropped by a migration."""
    count = op.get_bind().scalar(sa.text(f"SELECT count(*) FROM {table}"))
    if count:
        raise RuntimeError(
            f"Refusing to drop {table}: it holds {count} rows of user data."
        )


def upgrade() -> None:
    """Apply the change."""
    op.create_table(
        "user_tag",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recording_id", sa.Integer(), nullable=False),
        sa.Column("tag", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["recording.id"],
            name=op.f("fk_user_tag_recording_id_recording"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_tag")),
        sa.UniqueConstraint("recording_id", "tag", name="uq_user_tag_recording_tag"),
    )


def downgrade() -> None:
    """Revert the change; only possible while the table is empty."""
    _refuse_if_not_empty("user_tag")
    op.drop_table("user_tag")
