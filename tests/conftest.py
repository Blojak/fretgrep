"""Shared fixtures. Test databases are always built by the migrations."""
# pylint: disable=redefined-outer-name

import os

import pytest

from fretgrep import config, db


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch, tmp_path):
    """Hide the settings of the shell that runs the tests and its cache."""
    for name in list(os.environ):
        if name.startswith(("FRETGREP_", config.LEGACY_PREFIX)):
            monkeypatch.delenv(name)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


@pytest.fixture
def db_path(tmp_path):
    """Return the path of a freshly migrated database."""
    path = tmp_path / "data" / "test.db"
    db.upgrade(path)
    return path


@pytest.fixture
def session(db_path):
    """Return a session on a freshly migrated database."""
    with db.open_session(db_path) as session:
        yield session


@pytest.fixture
def library(tmp_path):
    """Return an empty library folder."""
    folder = tmp_path / "library"
    folder.mkdir()
    return folder
