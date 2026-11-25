"""Tests for the keyword search."""
# pylint: disable=missing-function-docstring,redefined-outer-name

import pytest
from sqlalchemy import select

from fretgrep import search, user_meta
from fretgrep.models import Recording
from fretgrep.scanner import scan_library

NAMES = [
    "251/major/251 blues cmaj7.mp3",
    "251/major/G7 Cj7.mp3",
    "251/minor/dm7b5 chet baker.mp3",
    "251/unsortiert/251 moll 8 chet baker.mp3",
    "251/unsortiert/251 moll baker lick 1.mp3",
    "251/unsortiert/251 barry harris flüssig .mp3",
    "251/unsortiert/251 wes four on six lick.mp3",
    "251/unsortiert/251 dur A Wes.mp3",
]


@pytest.fixture
def indexed(session, library):
    """Return a session with a scanned and indexed small library."""
    for number, name in enumerate(NAMES):
        path = library / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes([number]))
    scan_library(session, library)
    search.rebuild(session)
    session.commit()
    return session


def names(session, words):
    return {
        recording.file.filename_norm for recording in search.search(session, words)
    }


def test_examples_from_the_brief(indexed):
    assert names(indexed, "Blues über 251") == {"251 blues cmaj7"}
    assert names(indexed, "Chet Baker moll") == {
        "dm7b5 chet baker",
        "251 moll 8 chet baker",
    }


def test_all_words_must_match(indexed):
    assert names(indexed, "baker") == {
        "dm7b5 chet baker",
        "251 moll 8 chet baker",
        "251 moll baker lick 1",
    }
    assert names(indexed, "baker wes") == set()


def test_vocabulary_bridges_spellings(indexed):
    assert names(indexed, "cmaj7") == {"251 blues cmaj7", "G7 Cj7"}
    assert names(indexed, "minor") >= {"251 moll 8 chet baker", "dm7b5 chet baker"}
    assert names(indexed, "dur") >= {"251 dur A Wes", "G7 Cj7"}


def test_any_word_may_match_on_request(indexed):
    ids = search.search_ids(indexed, "trauriger harris flüssig", match_all=False)

    assert [r.file.filename_norm for r in search.load(indexed, ids)] == [
        "251 barry harris flüssig"
    ]
    assert not search.search_ids(indexed, "trauriger harris flüssig")
    assert len(search.search_ids(indexed, "baker wes", match_all=False)) == 5


def test_prefix_and_diacritics(indexed):
    assert names(indexed, "flussig") == {"251 barry harris flüssig"}
    assert names(indexed, "harr") == {"251 barry harris flüssig"}


def test_special_characters_do_not_break_the_query(indexed):
    assert names(indexed, 'eb7 "#9" (x) -y *') == set()


def test_only_stopwords_gives_no_query(indexed):
    assert search.build_query("mit und über") is None
    assert not search.search(indexed, "mit und über")


def test_user_tags_and_notes_are_searchable(indexed):
    recording = indexed.scalars(select(Recording)).first()
    user_meta.add_tags(recording, ["Favorit"])
    user_meta.set_note(recording, "Fingersatz noch unklar")
    search.refresh(indexed, recording)
    indexed.commit()

    assert names(indexed, "favorit") == {recording.file.filename_norm}
    assert names(indexed, "fingersatz") == {recording.file.filename_norm}

    user_meta.remove_tags(recording, ["Favorit"])
    search.refresh(indexed, recording)
    assert names(indexed, "favorit") == set()


def test_limit(indexed):
    assert len(search.search(indexed, "251", limit=3)) == 3
