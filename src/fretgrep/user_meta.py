"""Tags, notes and playlists made by the user.

Nothing in here is ever derived from the audio files, and nothing outside
this module writes to the ``user_*`` tables.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from fretgrep.filename_parser import normalize_name
from fretgrep.models import (
    Recording,
    UserNote,
    UserPlaylist,
    UserPlaylistEntry,
    UserTag,
)


def add_tags(recording: Recording, tags: list[str]) -> list[str]:
    """Add tags; return the ones that were new."""
    existing = {row.tag for row in recording.user_tags}
    added = []
    for tag in map(normalize_name, tags):
        if tag and tag not in existing:
            recording.user_tags.append(UserTag(tag=tag))
            existing.add(tag)
            added.append(tag)
    return added


def remove_tags(recording: Recording, tags: list[str]) -> list[str]:
    """Remove tags; return the ones that were present."""
    wanted = set(map(normalize_name, tags))
    removed = []
    for row in list(recording.user_tags):
        if row.tag in wanted:
            recording.user_tags.remove(row)
            removed.append(row.tag)
    return removed


def set_note(recording: Recording, text: str) -> None:
    """Set the note; an empty text removes it."""
    text = text.strip()
    if not text:
        recording.note = None
    elif recording.note is None:
        recording.note = UserNote(text=text)
    else:
        recording.note.text = text


def playlists(session: Session) -> list[UserPlaylist]:
    """Return all playlists, sorted by name."""
    found = session.scalars(select(UserPlaylist)).all()
    return sorted(found, key=lambda playlist: playlist.name.casefold())


def find_playlist(session: Session, name: str) -> UserPlaylist | None:
    """Return the playlist of that name; upper and lower case do not matter."""
    wanted = normalize_name(name).casefold()
    for playlist in session.scalars(select(UserPlaylist)):
        if playlist.name.casefold() == wanted:
            return playlist
    return None


def create_playlist(session: Session, name: str) -> UserPlaylist:
    """Create an empty playlist; the caller makes sure the name is free."""
    playlist = UserPlaylist(name=normalize_name(name))
    session.add(playlist)
    return playlist


def add_to_playlist(
    playlist: UserPlaylist, recordings: list[Recording]
) -> list[Recording]:
    """Append recordings at the end; return those that were not in it yet."""
    present = {entry.recording_id for entry in playlist.entries}
    position = max((entry.position for entry in playlist.entries), default=0)
    added = []
    for recording in recordings:
        if recording.id in present:
            continue
        position += 1
        playlist.entries.append(
            UserPlaylistEntry(recording=recording, position=position)
        )
        present.add(recording.id)
        added.append(recording)
    return added


def remove_from_playlist(playlist: UserPlaylist, ids: list[int]) -> list[int]:
    """Remove recordings; return the IDs that were in the playlist."""
    removed = []
    for entry in list(playlist.entries):
        if entry.recording_id in ids:
            playlist.entries.remove(entry)
            removed.append(entry.recording_id)
    return removed
