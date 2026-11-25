"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
"""
# pylint: disable=invalid-name,no-member,duplicate-code

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    """Apply the change."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Revert the change."""
    ${downgrades if downgrades else "pass"}
