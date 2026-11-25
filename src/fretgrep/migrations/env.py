"""Alembic environment for the fretgrep database."""
# pylint: disable=no-member

from alembic import context
from sqlalchemy import create_engine

from fretgrep import config as app_config
from fretgrep.db import sqlite_url
from fretgrep.models import Base
from fretgrep.search import SEARCH_INDEX

config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    """Use the URL passed in programmatically, else the app configuration."""
    return config.get_main_option("sqlalchemy.url") or sqlite_url(
        app_config.database_path()
    )


def _include_name(name, type_, _parent_names) -> bool:
    """Hide the FTS5 index and its shadow tables from autogenerate."""
    return not (type_ == "table" and name.startswith(SEARCH_INDEX))


def run_migrations_offline() -> None:
    """Emit the migration SQL without connecting to a database."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run the migrations against the configured database."""
    engine = create_engine(_database_url())
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            include_name=_include_name,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
