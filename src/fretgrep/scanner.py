"""Read a library folder into the database.

Only ``auto_*`` rows are written. A recording is identified by the hash of
its content, so renaming or moving a file keeps its identity.
"""

import hashlib
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from fretgrep.audio_info import AudioInfo, read_audio_info
from fretgrep.filename_parser import PARSER_VERSION, ParseResult, parse
from fretgrep.models import AutoFile, AutoTag, Recording, utcnow

AUDIO_SUFFIX = ".mp3"


@dataclass
class ScanSummary:
    """Counts and warnings of one scan."""

    new: int = 0
    updated: int = 0
    unchanged: int = 0
    missing: int = 0
    duplicates: list[tuple[str, str]] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class _ScannedFile:
    """What was read from disk; ``audio`` is None if the file was not reread."""

    rel_path: str
    content_hash: str
    size_bytes: int
    mtime: float
    audio: AudioInfo | None


def iter_audio_files(library: Path) -> list[str]:
    """Return the sorted relative paths of all audio files in the library."""
    found = []
    for folder, _, names in os.walk(library):
        for name in names:
            if name.lower().endswith(AUDIO_SUFFIX):
                found.append(Path(folder, name).relative_to(library).as_posix())
    return sorted(found)


def hash_file(path: Path) -> str:
    """Return the SHA-256 hex digest of the file content."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def scan_library(session: Session, library: Path) -> ScanSummary:
    """Synchronise the ``auto_*`` tables with the files in the library."""
    summary = ScanSummary()
    recordings = session.scalars(
        select(Recording).options(
            selectinload(Recording.file), selectinload(Recording.tags)
        )
    ).all()
    by_hash = {recording.content_hash: recording for recording in recordings}
    by_path = {
        recording.file.rel_path: recording
        for recording in recordings
        if not recording.file.missing
    }
    seen: dict[str, str] = {}

    for rel_path in iter_audio_files(library):
        try:
            scanned = _read_file(library, rel_path, by_path.get(rel_path))
        except (OSError, UnicodeError) as error:
            summary.errors.append((rel_path, str(error)))
            continue
        if scanned.content_hash in seen:
            summary.duplicates.append((rel_path, seen[scanned.content_hash]))
            continue
        seen[scanned.content_hash] = rel_path
        _store(session, by_hash, scanned, summary)

    for recording in recordings:
        if recording.content_hash not in seen:
            recording.file.missing = True
            summary.missing += 1
    session.commit()
    return summary


def _read_file(library: Path, rel_path: str, known: Recording | None) -> _ScannedFile:
    """Read one file; skip hashing if path, size and mtime are unchanged."""
    rel_path.encode("utf-8")  # reject names that cannot be stored
    path = library / rel_path
    stat = path.stat()
    if (
        known is not None
        and known.file.size_bytes == stat.st_size
        and known.file.mtime == stat.st_mtime
    ):
        return _ScannedFile(
            rel_path, known.content_hash, stat.st_size, stat.st_mtime, None
        )
    return _ScannedFile(
        rel_path, hash_file(path), stat.st_size, stat.st_mtime, read_audio_info(path)
    )


def _store(
    session: Session,
    by_hash: dict[str, Recording],
    scanned: _ScannedFile,
    summary: ScanSummary,
) -> None:
    """Insert or update the rows of one recording."""
    parsed = parse(scanned.rel_path)
    recording = by_hash.get(scanned.content_hash)
    if recording is None:
        recording = Recording(content_hash=scanned.content_hash, file=AutoFile())
        session.add(recording)
        by_hash[scanned.content_hash] = recording
        _update_file(recording.file, scanned, parsed)
        _update_tags(recording, parsed)
        summary.new += 1
        return
    file_changed = _update_file(recording.file, scanned, parsed)
    tags_changed = _update_tags(recording, parsed)
    if file_changed or tags_changed:
        summary.updated += 1
    else:
        summary.unchanged += 1


def _update_file(file: AutoFile, scanned: _ScannedFile, parsed: ParseResult) -> bool:
    """Write changed file facts; return True if anything changed."""
    values = {
        "rel_path": scanned.rel_path,
        "filename_norm": parsed.name,
        "size_bytes": scanned.size_bytes,
        "mtime": scanned.mtime,
        "unparsed": " ".join(parsed.unparsed),
        "missing": False,
    }
    if scanned.audio is not None:
        values.update(asdict(scanned.audio))
    changed = False
    for name, value in values.items():
        if getattr(file, name) != value:
            setattr(file, name, value)
            changed = True
    if changed:
        file.scanned_at = utcnow()
    return changed


def _update_tags(recording: Recording, parsed: ParseResult) -> bool:
    """Replace the tag suggestions if they differ; return True if changed."""
    wanted = {(tag.category, tag.value, tag.source): tag for tag in parsed.tags}
    existing = {(tag.category, tag.value, tag.source): tag for tag in recording.tags}
    changed = False
    for key, row in existing.items():
        if key not in wanted:
            recording.tags.remove(row)
            changed = True
    for key, tag in wanted.items():
        row = existing.get(key)
        if row is None:
            row = AutoTag(category=tag.category, value=tag.value, source=tag.source)
            recording.tags.append(row)
        elif (row.confidence, row.raw_token, row.parser_version) == (
            tag.confidence,
            tag.raw_token,
            PARSER_VERSION,
        ):
            continue
        row.confidence = tag.confidence
        row.raw_token = tag.raw_token
        row.parser_version = PARSER_VERSION
        changed = True
    return changed
