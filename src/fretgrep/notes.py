"""Recognise the notes played in a recording with basic-pitch.

Notes are ``auto_*`` data: they can be recomputed at any time. All
recognised notes are stored; quiet ones are only hidden when printing, so
the threshold can change without a new recognition run.

basic-pitch and its ONNX runtime are optional dependencies; audio is
decoded with the ``ffmpeg`` command.
"""

import contextlib
import io
import logging
import subprocess
import tempfile
import textwrap
import warnings
from collections.abc import Callable
from dataclasses import astuple, dataclass
from importlib import metadata
from pathlib import Path

from fretgrep.models import AutoNotes, Recording

SAMPLE_RATE = 22050
# Range of the guitar, with some room: below the low E, above the top fret.
MIN_FREQUENCY_HZ = 80
MAX_FREQUENCY_HZ = 1400

DEFAULT_MIN_AMPLITUDE = 0.5
# Notes starting this close together are shown as played together.
CHORD_WINDOW_S = 0.05
# A longer silence starts a new phrase.
PHRASE_GAP_S = 0.75

# General MIDI program "Electric Guitar (jazz)", counted from 0.
MIDI_PROGRAM = 26

_PITCH_NAMES = ("C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")


class MissingDependencyError(RuntimeError):
    """basic-pitch or one of its libraries is not installed."""


@dataclass(frozen=True, order=True)
class Note:
    """One recognised note; ``pitch`` is a MIDI note number."""

    start: float
    end: float
    pitch: int
    amplitude: float


Detector = Callable[[Path], list[Note]]


def note_name(pitch: int) -> str:
    """Return the name of a MIDI note number, e.g. 60 -> "C4"."""
    return f"{_PITCH_NAMES[pitch % 12]}{pitch // 12 - 1}"


def load_detector() -> tuple[Detector, str]:
    """Return a function that recognises notes, and the name of its model."""
    try:
        # basic-pitch warns about every runtime it does not find.
        logging.disable(logging.WARNING)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # pylint: disable=import-outside-toplevel
            from basic_pitch import FilenameSuffix, build_icassp_2022_model_path
            from basic_pitch.inference import Model, predict

            model = Model(build_icassp_2022_model_path(FilenameSuffix.onnx))
    except (ImportError, ValueError) as error:
        raise MissingDependencyError(str(error)) from error
    finally:
        logging.disable(logging.NOTSET)

    def detect(path: Path) -> list[Note]:
        with tempfile.TemporaryDirectory() as folder:
            wav = Path(folder) / "audio.wav"
            decode_audio(path, wav)
            with contextlib.redirect_stdout(io.StringIO()):
                _, _, events = predict(
                    wav,
                    model,
                    minimum_frequency=MIN_FREQUENCY_HZ,
                    maximum_frequency=MAX_FREQUENCY_HZ,
                )
        return sorted(
            Note(round(float(start), 3), round(float(end), 3), int(pitch),
                 round(float(amplitude), 3))
            for start, end, pitch, amplitude, _bends in events
        )

    return detect, f"basic-pitch {metadata.version('basic-pitch')}"


def decode_audio(source: Path, target: Path) -> None:
    """Decode a file to a mono WAV file using ffmpeg."""
    command = [
        "ffmpeg", "-v", "error", "-i", str(source),
        "-ac", "1", "-ar", str(SAMPLE_RATE), str(target),
    ]
    subprocess.run(command, capture_output=True, check=True)


def store(recording: Recording, notes: list[Note], model_name: str) -> None:
    """Replace the stored notes of a recording."""
    if recording.notes is None:
        recording.notes = AutoNotes()
    recording.notes.model = model_name
    recording.notes.notes = [list(astuple(note)) for note in notes]


def stored(recording: Recording) -> list[Note] | None:
    """Return the stored notes of a recording, None if there are none yet."""
    if recording.notes is None:
        return None
    return [Note(*values) for values in recording.notes.notes]


def write_midi(notes: list[Note], min_amplitude: float, path: Path) -> int:
    """Write the notes that are loud enough as a MIDI file; return how many."""
    try:
        import pretty_midi  # pylint: disable=import-outside-toplevel
    except ImportError as error:
        raise MissingDependencyError(str(error)) from error
    guitar = pretty_midi.Instrument(program=MIDI_PROGRAM)
    guitar.notes = [
        pretty_midi.Note(
            velocity=max(1, min(127, round(note.amplitude * 127))),
            pitch=note.pitch,
            start=note.start,
            end=note.end,
        )
        for note in sorted(notes)
        if note.amplitude >= min_amplitude
    ]
    midi = pretty_midi.PrettyMIDI()
    midi.instruments.append(guitar)
    midi.write(str(path))
    return len(guitar.notes)


def phrases(notes: list[Note], min_amplitude: float) -> list[list[list[Note]]]:
    """Group the notes that are loud enough into phrases of chords.

    A chord is a list of notes that start together, lowest first; a single
    note is a chord of one. A phrase ends where nothing sounds for a while.
    """
    result: list[list[list[Note]]] = []
    phrase_end = 0.0
    for note in sorted(n for n in notes if n.amplitude >= min_amplitude):
        if not result or note.start - phrase_end > PHRASE_GAP_S:
            result.append([[note]])
            phrase_end = note.end
            continue
        chord = result[-1][-1]
        if note.start - chord[0].start <= CHORD_WINDOW_S:
            chord.append(note)
            chord.sort(key=lambda n: n.pitch)
        else:
            result[-1].append([note])
        phrase_end = max(phrase_end, note.end)
    return result


def format_phrase(phrase: list[list[Note]], width: int = 80) -> str:
    """Format one phrase: start time, then note names, wrapped to ``width``."""
    parts = []
    for chord in phrase:
        names = "\u00a0".join(note_name(note.pitch) for note in chord)
        parts.append(f"[{names}]" if len(chord) > 1 else names)
    text = textwrap.fill(
        " ".join(parts),
        width=max(width, 30),
        initial_indent=f"{phrase[0][0].start:6.1f}s  ",
        subsequent_indent=" " * 9,
        break_on_hyphens=False,
    )
    return text.replace("\u00a0", " ")
