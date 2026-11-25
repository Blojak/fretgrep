"""Tests for transcription, with a stand-in for the Whisper model."""
# pylint: disable=missing-function-docstring,redefined-outer-name

import subprocess
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from fretgrep import search, transcribe
from fretgrep.models import AutoTranscript, Recording
from fretgrep.scanner import scan_library


class FakeModel:
    """Returns a fixed text and records how it was called."""

    def __init__(self, texts=(" Hier gehe ich ", "", " auf den HM5. ")):
        self.texts = texts
        self.calls = []

    def transcribe(self, audio, **options):
        self.calls.append((audio, options))
        segments = (SimpleNamespace(text=text) for text in self.texts)
        return segments, SimpleNamespace(language="de")


@pytest.fixture
def scanned(session, library, monkeypatch):
    """Return a session with two scanned files; decoding is faked."""
    (library / "a lick.mp3").write_bytes(b"one")
    (library / "b lick.mp3").write_bytes(b"two")
    scan_library(session, library)
    monkeypatch.setattr(transcribe, "decode_audio", lambda path: path.name)
    return session


def run(session, library, model, **options):
    todo = transcribe.pending(session, "fake", **options)
    return transcribe.transcribe_recordings(session, library, model, "fake", todo)


def test_transcripts_are_stored_and_searchable(scanned, library):
    model = FakeModel()

    assert run(scanned, library, model) == 2

    transcripts = scanned.scalars(select(AutoTranscript)).all()
    assert {row.text for row in transcripts} == {"Hier gehe ich auf den HM5."}
    assert {(row.language, row.model) for row in transcripts} == {("de", "fake")}
    assert model.calls[0][0] == "a lick.mp3"
    assert model.calls[0][1]["vad_filter"] is True
    assert len(search.search(scanned, "hm5 gehe")) == 2


def test_done_recordings_are_skipped_unless_redo(scanned, library):
    run(scanned, library, FakeModel())

    assert not transcribe.pending(scanned, "fake")
    assert len(transcribe.pending(scanned, "fake", redo=True)) == 2
    assert len(transcribe.pending(scanned, "other-model")) == 2
    assert run(scanned, library, FakeModel(["neu"]), redo=True, ids=[1]) == 1
    assert scanned.get(Recording, 1).transcript.text == "neu"
    assert scanned.get(Recording, 2).transcript.text != "neu"


def test_silence_is_stored_as_empty_text(scanned, library):
    run(scanned, library, FakeModel(texts=()))

    assert {row.text for row in scanned.scalars(select(AutoTranscript))} == {""}
    assert not transcribe.pending(scanned, "fake")


def test_missing_files_are_not_pending(scanned, library):
    (library / "a lick.mp3").unlink()
    scan_library(scanned, library)

    assert [r.file.rel_path for r in transcribe.pending(scanned, "fake")] == [
        "b lick.mp3"
    ]


def test_failed_file_is_reported_and_others_continue(scanned, library, monkeypatch):
    def decode(path):
        if path.name.startswith("a"):
            raise subprocess.CalledProcessError(1, "ffmpeg")
        return path.name

    monkeypatch.setattr(transcribe, "decode_audio", decode)
    reports = []
    todo = transcribe.pending(scanned, "fake")

    done = transcribe.transcribe_recordings(
        scanned, library, FakeModel(), "fake", todo,
        report=lambda recording, error: reports.append(
            (recording.file.rel_path, error is None)
        ),
    )

    assert done == 1
    assert reports == [("a lick.mp3", False), ("b lick.mp3", True)]
    assert len(transcribe.pending(scanned, "fake")) == 1


def test_rescan_keeps_transcript(scanned, library):
    run(scanned, library, FakeModel())
    (library / "a lick.mp3").rename(library / "renamed.mp3")

    scan_library(scanned, library)

    assert scanned.scalars(select(AutoTranscript)).first().text
    assert not transcribe.pending(scanned, "fake")
