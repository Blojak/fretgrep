"""Database access and schema migrations."""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class SchemaOutdatedError(RuntimeError):
    """The database is missing or not migrated to the latest revision."""


def sqlite_url(db_path: Path) -> str:
    """Return the SQLAlchemy URL for a SQLite file."""
    return f"sqlite:///{db_path}"


def create_db_engine(db_path: Path) -> Engine:
    """Create an engine with foreign key enforcement switched on."""
    engine = create_engine(sqlite_url(db_path))

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


def alembic_config(db_path: Path) -> Config:
    """Build the Alembic configuration for the given database file."""
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    # "%" is the interpolation character of configparser.
    cfg.set_main_option("sqlalchemy.url", sqlite_url(db_path).replace("%", "%%"))
    return cfg


def upgrade(db_path: Path) -> None:
    """Migrate the database to the latest revision, creating it if needed."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(alembic_config(db_path), "head")


def is_current(engine: Engine, db_path: Path) -> bool:
    """Return True if the database is at the latest revision."""
    head = ScriptDirectory.from_config(alembic_config(db_path)).get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    return current == head


@contextmanager
def open_session(db_path: Path) -> Generator[Session, None, None]:
    """Open a session; refuse to work on a missing or outdated schema."""
    if not db_path.exists():
        raise SchemaOutdatedError(db_path)
    engine = create_db_engine(db_path)
    try:
        if not is_current(engine, db_path):
            raise SchemaOutdatedError(db_path)
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()
