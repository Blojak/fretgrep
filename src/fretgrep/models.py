"""Database models.

Tables prefixed with ``auto_`` hold data that can be recomputed from the
audio files at any time. Tables prefixed with ``user_`` hold what the user
entered; they only reference ``recording.id`` and are never recomputed.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, ForeignKey, MetaData, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    """Return the current UTC time without tzinfo (SQLite stores it naive)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    """Declarative base with stable constraint names for migrations."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Recording(Base):
    """Stable identity of one recording, keyed by its content hash."""

    __tablename__ = "recording"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    file: Mapped["AutoFile"] = relationship(back_populates="recording")
    tags: Mapped[list["AutoTag"]] = relationship(
        back_populates="recording", cascade="all, delete-orphan"
    )
    transcript: Mapped["AutoTranscript | None"] = relationship(
        back_populates="recording", cascade="all, delete-orphan"
    )
    embedding: Mapped["AutoEmbedding | None"] = relationship(
        back_populates="recording", cascade="all, delete-orphan"
    )
    notes: Mapped["AutoNotes | None"] = relationship(
        back_populates="recording", cascade="all, delete-orphan"
    )
    user_tags: Mapped[list["UserTag"]] = relationship(
        back_populates="recording", cascade="all, delete-orphan"
    )
    note: Mapped["UserNote | None"] = relationship(
        back_populates="recording", cascade="all, delete-orphan"
    )


class AutoFile(Base):
    """Recomputable facts about the file that holds a recording."""

    __tablename__ = "auto_file"

    recording_id: Mapped[int] = mapped_column(
        ForeignKey("recording.id"), primary_key=True
    )
    rel_path: Mapped[str]
    filename_norm: Mapped[str]
    size_bytes: Mapped[int]
    mtime: Mapped[float]
    duration_s: Mapped[float | None]
    sample_rate: Mapped[int | None]
    channels: Mapped[int | None]
    bitrate: Mapped[int | None]
    unparsed: Mapped[str] = mapped_column(default="")
    missing: Mapped[bool] = mapped_column(default=False)
    scanned_at: Mapped[datetime] = mapped_column(default=utcnow)

    recording: Mapped[Recording] = relationship(back_populates="file")


class AutoTag(Base):
    """A tag suggested by the parser; never a confirmed fact."""

    __tablename__ = "auto_tag"
    __table_args__ = (
        UniqueConstraint(
            "recording_id",
            "category",
            "value",
            "source",
            name="uq_auto_tag_recording_category_value_source",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recording_id: Mapped[int] = mapped_column(ForeignKey("recording.id"))
    category: Mapped[str]
    value: Mapped[str]
    confidence: Mapped[float]
    source: Mapped[str]
    raw_token: Mapped[str]
    parser_version: Mapped[int]

    recording: Mapped[Recording] = relationship(back_populates="tags")


class AutoTranscript(Base):
    """Speech recognised in a recording; empty text means no speech."""

    __tablename__ = "auto_transcript"

    recording_id: Mapped[int] = mapped_column(
        ForeignKey("recording.id"), primary_key=True
    )
    text: Mapped[str]
    language: Mapped[str | None]
    model: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    recording: Mapped[Recording] = relationship(back_populates="transcript")


class AutoEmbedding(Base):
    """Embedding vector of a recording's text, as float32 bytes.

    ``text_hash`` identifies the text that was embedded, so a changed tag,
    note or transcript shows up as an outdated vector.
    """

    __tablename__ = "auto_embedding"

    recording_id: Mapped[int] = mapped_column(
        ForeignKey("recording.id"), primary_key=True
    )
    model: Mapped[str]
    text_hash: Mapped[str] = mapped_column(String(64))
    vector: Mapped[bytes]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    recording: Mapped[Recording] = relationship(back_populates="embedding")


class AutoNotes(Base):
    """Notes recognised in a recording.

    ``notes`` is a list of ``[start_s, end_s, midi_pitch, amplitude]``.
    """

    __tablename__ = "auto_notes"

    recording_id: Mapped[int] = mapped_column(
        ForeignKey("recording.id"), primary_key=True
    )
    model: Mapped[str]
    notes: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    recording: Mapped[Recording] = relationship(back_populates="notes")


class UserTag(Base):
    """A tag assigned by the user."""

    __tablename__ = "user_tag"
    __table_args__ = (
        UniqueConstraint("recording_id", "tag", name="uq_user_tag_recording_tag"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recording_id: Mapped[int] = mapped_column(ForeignKey("recording.id"))
    tag: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    recording: Mapped[Recording] = relationship(back_populates="user_tags")


class UserNote(Base):
    """The user's note on a recording."""

    __tablename__ = "user_note"

    recording_id: Mapped[int] = mapped_column(
        ForeignKey("recording.id"), primary_key=True
    )
    text: Mapped[str]
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    recording: Mapped[Recording] = relationship(back_populates="note")


class UserPlaylist(Base):
    """A playlist made by the user; each recording appears at most once."""

    __tablename__ = "user_playlist"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    entries: Mapped[list["UserPlaylistEntry"]] = relationship(
        back_populates="playlist",
        cascade="all, delete-orphan",
        order_by="UserPlaylistEntry.position",
    )


class UserPlaylistEntry(Base):
    """One recording in a playlist; ``position`` gives the order."""

    __tablename__ = "user_playlist_entry"
    __table_args__ = (
        UniqueConstraint(
            "playlist_id",
            "recording_id",
            name="uq_user_playlist_entry_playlist_recording",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    playlist_id: Mapped[int] = mapped_column(ForeignKey("user_playlist.id"))
    recording_id: Mapped[int] = mapped_column(ForeignKey("recording.id"))
    position: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    playlist: Mapped[UserPlaylist] = relationship(back_populates="entries")
    recording: Mapped[Recording] = relationship()
