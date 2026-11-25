"""Tests for user tags and notes and their protection."""
# pylint: disable=missing-function-docstring

import pytest
from alembic import command
from sqlalchemy import select

from fretgrep import db, user_meta
from fretgrep.models import Recording, UserNote, UserTag
from fretgrep.scanner import scan_library


def one_recording(session, library, name="251 moll 1.mp3"):
    (library / name).write_bytes(b"one")
    scan_library(session, library)
    return session.scalars(select(Recording)).one()


def test_tags_are_added_once_and_removed(session, library):
    recording = one_recording(session, library)

    assert user_meta.add_tags(recording, ["Favorit", " üben  bald ", "Favorit"]) == [
        "Favorit",
        "üben bald",
    ]
    assert not user_meta.add_tags(recording, ["Favorit"])
    session.commit()
    assert user_meta.remove_tags(recording, ["Favorit", "unbekannt"]) == ["Favorit"]
    session.commit()

    assert [row.tag for row in session.scalars(select(UserTag))] == ["üben bald"]


def test_note_is_set_replaced_and_cleared(session, library):
    recording = one_recording(session, library)

    user_meta.set_note(recording, "erste Fassung")
    session.commit()
    user_meta.set_note(recording, "Fingersatz ändern")
    session.commit()
    assert session.scalars(select(UserNote)).one().text == "Fingersatz ändern"

    user_meta.set_note(recording, "  ")
    session.commit()
    assert session.scalars(select(UserNote)).first() is None


def test_rescan_keeps_user_data(session, library):
    recording = one_recording(session, library)
    user_meta.add_tags(recording, ["Favorit"])
    user_meta.set_note(recording, "langsam üben")
    session.commit()

    (library / "251 moll 1.mp3").rename(library / "251 dur wes.mp3")
    scan_library(session, library)
    (library / "251 dur wes.mp3").unlink()
    scan_library(session, library)

    session.expire_all()
    recording = session.scalars(select(Recording)).one()
    assert recording.file.missing
    assert [row.tag for row in recording.user_tags] == ["Favorit"]
    assert recording.note.text == "langsam üben"


@pytest.mark.parametrize("target", ["0003", "0004"])
def test_downgrade_refuses_to_drop_user_data(db_path, library, target):
    with db.open_session(db_path) as session:
        recording = one_recording(session, library)
        user_meta.add_tags(recording, ["Favorit"])
        user_meta.set_note(recording, "wichtig")
        session.commit()

    with pytest.raises(RuntimeError, match="user data"):
        command.downgrade(db.alembic_config(db_path), target)

    engine = db.create_db_engine(db_path)
    with engine.connect() as connection:
        tags = connection.exec_driver_sql("SELECT count(*) FROM user_tag").scalar()
    engine.dispose()
    assert tags == 1
