"""Create the FTS5 search index.

Autogenerate cannot see FTS5 tables, so this is raw SQL. The index only
holds derived text and is rebuilt by the application.

Revision ID: 0006
Revises: 0005
"""
# pylint: disable=invalid-name,no-member,duplicate-code

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the change."""
    op.execute(
        """
        CREATE VIRTUAL TABLE search_index USING fts5(
            name, auto_tags, user_tags, note,
            tokenize = 'unicode61 remove_diacritics 2'
        )
        """
    )


def downgrade() -> None:
    """Revert the change."""
    op.execute("DROP TABLE search_index")
