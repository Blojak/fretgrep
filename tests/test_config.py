"""Tests for the settings, including the names from before the rename."""
# pylint: disable=missing-function-docstring

from pathlib import Path

from fretgrep import config


def test_new_name_wins_over_old(monkeypatch):
    monkeypatch.setenv("WOODSHED_EMBED_MODEL", "old")
    assert config.embed_model() == "old"
    monkeypatch.setenv(config.ENV_EMBED_MODEL, "new")
    assert config.embed_model() == "new"


def test_old_ollama_urls_still_work(monkeypatch):
    monkeypatch.setenv("WOODSHED_OLLAMA_URL", "http://a:1/")
    assert config.ollama_urls()[0] == "http://a:1"


def test_old_database_is_used_until_a_new_one_exists(tmp_path, monkeypatch):
    new = tmp_path / "fretgrep" / "fretgrep.db"
    old = tmp_path / "woodshed" / "woodshed.db"
    monkeypatch.setattr(config, "DEFAULT_DB_PATH", new)
    monkeypatch.setattr(config, "LEGACY_DB_PATH", old)
    assert config.database_path() == new

    old.parent.mkdir()
    old.write_bytes(b"")
    assert config.database_path() == old

    new.parent.mkdir()
    new.write_bytes(b"")
    assert config.database_path() == new


def test_database_setting_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("WOODSHED_DB", str(tmp_path / "x.db"))
    assert config.database_path() == Path(tmp_path / "x.db")
