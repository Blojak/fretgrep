"""Add the transcript column to the FTS5 search index.

FTS5 tables cannot be altered, so the index is dropped and recreated. It
only holds derived text; ``fretgrep db upgrade`` rebuilds it afterwards.

Revision ID: 0008
Revises: 0007
"""
# pylint: disable=invalid-name,no-member,duplicate-code

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_CREATE = """
    CREATE VIRTUAL TABLE search_index USING fts5(
        {columns},
        tokenize = 'unicode61 remove_diacritics 2'
    )
"""


def upgrade() -> None:
    """Apply the change."""
    op.execute("DROP TABLE search_index")
    op.execute(
        _CREATE.format(columns="name, auto_tags, user_tags, note, transcript")
    )


def downgrade() -> None:
    """Revert the change."""
    op.execute("DROP TABLE search_index")
    op.execute(_CREATE.format(columns="name, auto_tags, user_tags, note"))
