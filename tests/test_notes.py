"""Tests for storing and printing notes; basic-pitch itself is not run."""
# pylint: disable=missing-function-docstring,redefined-outer-name

import pytest
from sqlalchemy import select

from fretgrep import notes
from fretgrep.models import AutoNotes, Recording
from fretgrep.notes import Note
from fretgrep.scanner import scan_library

LINE = [
    Note(1.0, 1.2, 60, 0.7),
    Note(1.2, 1.4, 63, 0.7),
    Note(1.4, 2.0, 70, 0.8),
    # after a pause: a chord, with a quiet overtone on top
    Note(3.0, 3.5, 48, 0.6),
    Note(3.02, 3.5, 64, 0.6),
    Note(3.02, 3.2, 76, 0.3),
    Note(3.5, 3.8, 66, 0.9),
]


@pytest.fixture
def recording(session, library):
    """Return one scanned recording."""
    (library / "a lick.mp3").write_bytes(b"one")
    scan_library(session, library)
    return session.scalars(select(Recording)).one()


def test_note_names():
    assert [notes.note_name(pitch) for pitch in (40, 60, 61, 66, 70, 83)] == [
        "E2", "C4", "Db4", "F#4", "Bb4", "B5",
    ]


def test_store_and_read_back(session, recording):
    assert notes.stored(recording) is None

    notes.store(recording, LINE, "fake 1")
    session.commit()
    session.expire_all()

    assert notes.stored(recording) == LINE
    assert recording.notes.model == "fake 1"

    notes.store(recording, LINE[:1], "fake 2")
    session.commit()

    assert notes.stored(recording) == LINE[:1]
    assert len(session.scalars(select(AutoNotes)).all()) == 1


def test_phrases_split_at_pauses_and_group_chords():
    lines = [notes.format_phrase(phrase) for phrase in notes.phrases(LINE, 0.5)]

    assert lines == ["   1.0s  C4 Eb4 Bb4", "   3.0s  [C3 E4] F#4"]


def test_threshold_hides_quiet_notes():
    assert "[C3 E4 E5]" in notes.format_phrase(notes.phrases(LINE, 0.0)[1])
    assert [notes.format_phrase(p) for p in notes.phrases(LINE, 0.75)] == [
        "   1.4s  Bb4",
        "   3.5s  F#4",
    ]
    assert not notes.phrases(LINE, 1.0)


def test_long_note_keeps_phrase_together():
    held = [Note(0.0, 3.0, 40, 0.9), Note(0.2, 0.4, 60, 0.9), Note(2.5, 2.7, 62, 0.9)]

    assert len(notes.phrases(held, 0.5)) == 1


def test_unsorted_input():
    assert notes.phrases(LINE[::-1], 0.5) == notes.phrases(LINE, 0.5)


def test_long_phrases_wrap_without_splitting_chords():
    chords = [Note(i, i + 0.5, 60, 0.9) for i in range(8)]
    chords += [Note(i, i + 0.5, 64, 0.9) for i in range(8)]

    lines = notes.format_phrase(notes.phrases(chords, 0.5)[0], width=30).splitlines()

    assert lines[0] == "   0.0s  [C4 E4] [C4 E4]"
    assert set(lines[1:]) == {"         [C4 E4] [C4 E4]"}
    assert len(lines) == 4


def test_write_midi(tmp_path):
    pretty_midi = pytest.importorskip("pretty_midi")
    path = tmp_path / "lick.mid"

    assert notes.write_midi(LINE, 0.5, path) == 6

    written = pretty_midi.PrettyMIDI(str(path)).instruments[0]
    assert written.program == notes.MIDI_PROGRAM
    assert [note.pitch for note in written.notes] == [60, 63, 70, 48, 64, 66]
    assert written.notes[0].start == pytest.approx(1.0, abs=0.01)
    assert written.notes[0].end == pytest.approx(1.2, abs=0.01)
