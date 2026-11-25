"""Transcribe the spoken parts of recordings with faster-whisper.

Transcripts are ``auto_*`` data: they can be recomputed at any time.
faster-whisper is an optional dependency (``pip install -e .[transcribe]``);
audio is decoded with the ``ffmpeg`` command.
"""

import subprocess
from collections.abc import Callable, Iterable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from fretgrep import search
from fretgrep.models import AutoFile, AutoTranscript, Recording

SAMPLE_RATE = 16000


class MissingDependencyError(RuntimeError):
    """faster-whisper is not installed."""


def load_model(name: str):
    """Load a Whisper model for CPU use; downloads it on first use."""
    try:
        # pylint: disable-next=import-outside-toplevel
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise MissingDependencyError(str(error)) from error
    return WhisperModel(name, device="cpu", compute_type="int8")


def decode_audio(path: Path):
    """Decode a file to mono 16 kHz float samples using ffmpeg."""
    import numpy  # pylint: disable=import-outside-toplevel

    command = [
        "ffmpeg", "-v", "error", "-i", str(path),
        "-f", "f32le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-",
    ]
    raw = subprocess.run(command, capture_output=True, check=True).stdout
    return numpy.frombuffer(raw, dtype=numpy.float32)


def transcribe_file(model, path: Path, language: str | None) -> tuple[str, str]:
    """Return the recognised text and the language of one file.

    The voice activity filter skips the guitar-only parts, which Whisper
    would otherwise fill with invented text.
    """
    segments, info = model.transcribe(
        decode_audio(path),
        language=language,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    parts = (segment.text.strip() for segment in segments)
    return " ".join(part for part in parts if part), info.language


def pending(
    session: Session, model_name: str, ids: Iterable[int] = (), redo: bool = False
) -> list[Recording]:
    """Return the recordings that still need a transcript from this model."""
    query = (
        select(Recording)
        .join(AutoFile)
        .where(~AutoFile.missing)
        .options(selectinload(Recording.file), selectinload(Recording.transcript))
        .order_by(AutoFile.rel_path)
    )
    ids = list(ids)
    if ids:
        query = query.where(Recording.id.in_(ids))
    return [
        recording
        for recording in session.scalars(query)
        if redo
        or recording.transcript is None
        or recording.transcript.model != model_name
    ]


def transcribe_recordings(  # pylint: disable=too-many-arguments
    session: Session,
    library: Path,
    model,
    model_name: str,
    recordings: list[Recording],
    *,
    language: str | None = None,
    report: Callable[[Recording, str | None], None] = lambda *_: None,
) -> int:
    """Transcribe recordings one by one; return how many succeeded.

    Each result is committed on its own, so an interrupted run can simply
    be started again. ``report`` gets the recording and an error message
    (None on success).
    """
    done = 0
    for recording in recordings:
        path = library / recording.file.rel_path
        try:
            text, detected = transcribe_file(model, path, language)
        except (OSError, subprocess.CalledProcessError) as error:
            report(recording, str(error))
            continue
        if recording.transcript is None:
            recording.transcript = AutoTranscript()
        recording.transcript.text = text
        recording.transcript.language = detected
        recording.transcript.model = model_name
        search.refresh(session, recording)
        session.commit()
        done += 1
        report(recording, None)
    return done
