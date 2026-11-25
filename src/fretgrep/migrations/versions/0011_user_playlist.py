"""Create the user_playlist and user_playlist_entry tables.

Revision ID: 0011
Revises: 0010
"""
# pylint: disable=invalid-name,no-member,duplicate-code

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
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
        "user_playlist",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_playlist")),
        sa.UniqueConstraint("name", name=op.f("uq_user_playlist_name")),
    )
    op.create_table(
        "user_playlist_entry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("playlist_id", sa.Integer(), nullable=False),
        sa.Column("recording_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["playlist_id"],
            ["user_playlist.id"],
            name=op.f("fk_user_playlist_entry_playlist_id_user_playlist"),
        ),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["recording.id"],
            name=op.f("fk_user_playlist_entry_recording_id_recording"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_playlist_entry")),
        sa.UniqueConstraint(
            "playlist_id",
            "recording_id",
            name="uq_user_playlist_entry_playlist_recording",
        ),
    )


def downgrade() -> None:
    """Revert the change; only possible while the tables are empty."""
    _refuse_if_not_empty("user_playlist_entry")
    _refuse_if_not_empty("user_playlist")
    op.drop_table("user_playlist_entry")
    op.drop_table("user_playlist")
