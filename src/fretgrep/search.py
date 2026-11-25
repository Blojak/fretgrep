"""Keyword search over an FTS5 index.

The index row of a recording (``rowid`` = ``recording.id``) is derived
from its file name, tag suggestions, user tags, note and transcript. It can be rebuilt
at any time.
"""

import unicodedata
from pathlib import PurePosixPath

from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from fretgrep.filename_parser import load_vocabulary, suggest
from fretgrep.models import Recording

SEARCH_INDEX = "search_index"

# bm25 column weights: name, auto_tags, user_tags, note, transcript
_RANK = f"bm25({SEARCH_INDEX}, 3.0, 1.0, 4.0, 2.0, 1.5)"
_INSERT = text(
    f"INSERT INTO {SEARCH_INDEX}"
    "(rowid, name, auto_tags, user_tags, note, transcript) "
    "VALUES (:rowid, :name, :auto_tags, :user_tags, :note, :transcript)"
)
_DELETE = text(f"DELETE FROM {SEARCH_INDEX} WHERE rowid = :rowid")
_MATCH = text(
    f"SELECT rowid FROM {SEARCH_INDEX} WHERE {SEARCH_INDEX} MATCH :query "
    f"ORDER BY {_RANK} LIMIT :limit"
)

LOAD_ALL = (
    selectinload(Recording.file),
    selectinload(Recording.tags),
    selectinload(Recording.user_tags),
    selectinload(Recording.note),
    selectinload(Recording.transcript),
    selectinload(Recording.embedding),
)


def _document(recording: Recording) -> dict:
    """Build the index row of one recording."""
    path = PurePosixPath(unicodedata.normalize("NFC", recording.file.rel_path))
    return {
        "rowid": recording.id,
        "name": " ".join(path.with_suffix("").parts),
        "auto_tags": " ".join(
            f"{tag.value} {tag.raw_token}" for tag in recording.tags
        ),
        "user_tags": " ".join(tag.tag for tag in recording.user_tags),
        "note": recording.note.text if recording.note else "",
        "transcript": recording.transcript.text if recording.transcript else "",
    }


def rebuild(session: Session) -> None:
    """Rebuild the whole index from the tables."""
    session.execute(text(f"DELETE FROM {SEARCH_INDEX}"))
    recordings = session.scalars(select(Recording).options(*LOAD_ALL)).all()
    if recordings:
        session.execute(_INSERT, [_document(recording) for recording in recordings])


def refresh(session: Session, recording: Recording) -> None:
    """Update the index row of one recording."""
    session.flush()
    session.execute(_DELETE, {"rowid": recording.id})
    session.execute(_INSERT, _document(recording))


def _quote(term: str) -> str:
    """Quote a term as an FTS5 string."""
    return '"' + term.replace('"', '""') + '"'


def build_query(words: str, match_all: bool = True) -> str | None:
    """Translate search words into an FTS5 query; None if nothing is left.

    All words must match, or any one of them if ``match_all`` is False. A
    word also matches through its meaning in the vocabulary, so "moll"
    finds recordings tagged "minor".
    """
    stopwords = load_vocabulary().stopwords
    groups = []
    for term in unicodedata.normalize("NFC", words).lower().split():
        if term in stopwords:
            continue
        alternatives = [_quote(term) + "*"]
        alternatives += sorted({_quote(tag.value) for tag in suggest(term)})
        groups.append("(" + " OR ".join(alternatives) + ")")
    return (" AND " if match_all else " OR ").join(groups) or None


def search_ids(
    session: Session, words: str, limit: int = 20, match_all: bool = True
) -> list[int]:
    """Return the ids of the best matching recordings, best first."""
    query = build_query(words, match_all)
    if query is None:
        return []
    return list(session.scalars(_MATCH, {"query": query, "limit": limit}))


def load(session: Session, ids: list[int]) -> list[Recording]:
    """Load recordings with everything needed to print them, in id order given."""
    found = {
        recording.id: recording
        for recording in session.scalars(
            select(Recording).where(Recording.id.in_(ids)).options(*LOAD_ALL)
        )
    }
    return [found[recording_id] for recording_id in ids if recording_id in found]


def search(session: Session, words: str, limit: int = 20) -> list[Recording]:
    """Return the best matching recordings, best first."""
    return load(session, search_ids(session, words, limit))
