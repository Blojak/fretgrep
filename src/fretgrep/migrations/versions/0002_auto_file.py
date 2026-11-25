"""Create the auto_file table.

Revision ID: 0002
Revises: 0001
"""
# pylint: disable=invalid-name,no-member,duplicate-code

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the change."""
    op.create_table(
        "auto_file",
        sa.Column("recording_id", sa.Integer(), nullable=False),
        sa.Column("rel_path", sa.String(), nullable=False),
        sa.Column("filename_norm", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("mtime", sa.Double(), nullable=False),
        sa.Column("duration_s", sa.Double(), nullable=True),
        sa.Column("sample_rate", sa.Integer(), nullable=True),
        sa.Column("channels", sa.Integer(), nullable=True),
        sa.Column("bitrate", sa.Integer(), nullable=True),
        sa.Column("unparsed", sa.String(), nullable=False),
        sa.Column("missing", sa.Boolean(), nullable=False),
        sa.Column("scanned_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["recording.id"],
            name=op.f("fk_auto_file_recording_id_recording"),
        ),
        sa.PrimaryKeyConstraint("recording_id", name=op.f("pk_auto_file")),
    )


def downgrade() -> None:
    """Revert the change."""
    op.drop_table("auto_file")
