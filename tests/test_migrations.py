"""Tests for the Alembic migrations."""
# pylint: disable=missing-function-docstring

import pytest
from alembic import command
from sqlalchemy import inspect

from fretgrep import db


def table_names(db_path):
    engine = db.create_db_engine(db_path)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_creates_all_tables(db_path):
    assert table_names(db_path) >= {
        "alembic_version", "recording", "auto_file", "auto_tag",
        "user_tag", "user_note", "search_index", "auto_transcript",
        "auto_embedding", "auto_notes", "user_playlist",
        "user_playlist_entry",
    }


def test_search_index_is_usable(db_path):
    engine = db.create_db_engine(db_path)
    with engine.connect() as connection:
        connection.exec_driver_sql(
            "INSERT INTO search_index(rowid, name) VALUES (7, 'chet baker')"
        )
        found = connection.exec_driver_sql(
            "SELECT rowid FROM search_index WHERE search_index MATCH 'baker'"
        ).scalar()
    engine.dispose()
    assert found == 7


def test_models_match_migrations(db_path):
    command.check(db.alembic_config(db_path))


def test_downgrade_to_base(db_path):
    command.downgrade(db.alembic_config(db_path), "base")
    assert table_names(db_path) == {"alembic_version"}


def test_session_refuses_missing_database(tmp_path):
    with pytest.raises(db.SchemaOutdatedError):
        with db.open_session(tmp_path / "missing.db"):
            pass


def test_session_refuses_outdated_schema(db_path):
    command.downgrade(db.alembic_config(db_path), "0002")
    with pytest.raises(db.SchemaOutdatedError):
        with db.open_session(db_path):
            pass
