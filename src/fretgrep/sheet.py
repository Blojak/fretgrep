"""Draw recognised notes as sheet music with LilyPond.

By default only pitches and their order are drawn, as note heads without
stems: the recognition gives times in seconds, not note values. With an
estimated rhythm (see ``rhythm``) a phrase is drawn with note values,
beamed by beat, still without bars. Each phrase gets its own line,
labelled with its start time.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from fretgrep.notes import Note
from fretgrep.rhythm import Event, Rhythm

ENGRAVER = "lilypond"
# Programs that open a file in the desktop's default viewer.
VIEWERS = ("xdg-open", "open")
SHOW_SUFFIX = ".pdf"
SOURCE_SUFFIX = ".ly"
# File suffix -> LilyPond option for that output format.
FORMATS = {".pdf": "--pdf", ".svg": "--svg", ".png": "--png"}

_PITCH_NAMES = (
    "c", "des", "d", "ees", "e", "f", "fis", "g", "aes", "a", "bes", "b",
)

# Lengths in sixteenths -> LilyPond durations, longest first.
_DURATIONS = (
    (16, "1"), (12, "2."), (8, "2"), (6, "4."), (4, "4"), (3, "8."), (2, "8"),
    (1, "16"),
)
_BEAT = 4  # sixteenths
_BREAK_HERE = ' \\bar ""'

# The guitar clef: written an octave above the sounding pitch.
_TEMPLATE = r"""\version "2.24.0"
\header {
  title = "%(title)s"
  subtitle = "%(subtitle)s"
  tagline = ##f
}
\paper {
  indent = 0
  ragged-right = ##t
}
\score {
  \new Staff \with {
    \remove "Time_signature_engraver"
  } {
    \clef "treble_8"
    \cadenzaOn
    \accidentalStyle forget
%(phrases)s
  }
  \layout {
    \context {
      \Score
      \override SpacingSpanner.shortest-duration-space = #3.0
    }
  }
}
"""


class EngraverMissingError(RuntimeError):
    """LilyPond is not installed."""


class EngraverError(RuntimeError):
    """LilyPond could not draw the notes."""


class ViewerMissingError(RuntimeError):
    """No program is there to open the sheet in a window."""


def pitch(midi_pitch: int) -> str:
    """Return the LilyPond name of a MIDI note number, e.g. 60 -> "c'"."""
    octave = midi_pitch // 12 - 1
    marks = "'" * (octave - 3) if octave >= 3 else "," * (3 - octave)
    return _PITCH_NAMES[midi_pitch % 12] + marks


def _quote(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _chord(chord) -> str:
    names = [pitch(note.pitch) for note in chord]
    return f"<{' '.join(names)}>" if len(names) > 1 else names[0]


def _label(phrase: list[list[Note]], rhythm: Rhythm | None) -> str:
    text = f"{phrase[0][0].start:.1f}s"
    if rhythm is not None:
        text += f", Tempo {rhythm.bpm:.0f}"
    return f'^\\markup \\small "{text}"'


def _heads(phrase: list[list[Note]]) -> str:
    """Write a phrase as note heads; an invisible bar line allows a break."""
    parts = [_chord(chord) + "4" for chord in phrase]
    parts[0] += _label(phrase, None)
    line = (_BREAK_HERE + " ").join(parts)
    return f"    \\omit Stem {line} \\undo \\omit Stem"


def _durations(length: int) -> list[str]:
    result = []
    for size, name in _DURATIONS:
        while length >= size:
            result.append(name)
            length -= size
    return result


def _beamed(events: tuple[Event, ...]) -> set[tuple[int, int]]:
    """Return (first, last) index pairs of the notes to beam: runs within a beat."""
    pairs = set()
    run: list[int] = []
    for index, event in enumerate([*events, Event(-_BEAT, _BEAT)]):
        short = bool(event.chord) and event.length < _BEAT
        beat = event.position // _BEAT
        inside = (event.position + event.length - 1) // _BEAT == beat
        if run and not (
            short and inside and beat == events[run[0]].position // _BEAT
        ):
            if len(run) > 1:
                pairs.add((run[0], run[-1]))
            run = []
        if short and inside:
            run.append(index)
    return pairs


def _values(phrase: list[list[Note]], rhythm: Rhythm) -> str:
    """Write a phrase with note values, beamed by beat, without bars."""
    beams = _beamed(rhythm.events)
    opening = {first for first, _ in beams}
    closing = {last for _, last in beams}
    parts = []
    for index, event in enumerate(rhythm.events):
        names = _durations(event.length)
        if event.chord:
            text = "~ ".join(_chord(event.chord) + name for name in names)
        else:
            text = " ".join("r" + name for name in names)
        if index == 0:
            head, _, tail = text.partition(" ")
            text = head + _label(phrase, rhythm) + (" " + tail if tail else "")
        text += "[" if index in opening else "]" if index in closing else ""
        if (event.position + event.length) % _BEAT == 0:
            text += _BREAK_HERE  # a line may break between beats
        parts.append(text)
    return "    " + " ".join(parts)


def source(
    phrases: list[list[list[Note]]],
    title: str,
    subtitle: str = "",
    rhythms: list[Rhythm | None] | None = None,
) -> str:
    """Return the LilyPond source for phrases as built by ``notes.phrases``.

    ``rhythms`` holds one estimate per phrase; phrases without one are
    drawn as note heads.
    """
    rhythms = rhythms or [None] * len(phrases)
    lines = [
        (_heads(phrase) if rhythm is None else _values(phrase, rhythm))
        + ' \\bar "|" \\break'
        for phrase, rhythm in zip(phrases, rhythms)
    ]
    return _TEMPLATE % {
        "title": _quote(title),
        "subtitle": _quote(subtitle),
        "phrases": "\n".join(lines) or "    s4",
    }


def write(text: str, path: Path) -> None:
    """Write the sheet to ``path``; the suffix selects the format.

    ``.ly`` stores the LilyPond source itself, the other suffixes in
    ``FORMATS`` are drawn by LilyPond. Raises ValueError for anything else.
    """
    suffix = path.suffix.lower()
    if suffix == SOURCE_SUFFIX:
        path.write_text(text, encoding="utf-8")
        return
    if suffix not in FORMATS:
        raise ValueError(suffix)
    with tempfile.TemporaryDirectory() as folder:
        source_path = Path(folder) / "sheet.ly"
        source_path.write_text(text, encoding="utf-8")
        command = [
            ENGRAVER, "--silent", FORMATS[suffix],
            "-o", str(Path(folder) / "sheet"), str(source_path),
        ]
        try:
            done = subprocess.run(command, capture_output=True, text=True, check=False)
        except FileNotFoundError as error:
            raise EngraverMissingError(str(error)) from error
        drawn = Path(folder) / ("sheet" + suffix)
        if done.returncode != 0 or not drawn.is_file():
            raise EngraverError(done.stderr.strip())
        path.write_bytes(drawn.read_bytes())


def viewer() -> str | None:
    """Return the program that opens files in the default viewer, if any."""
    candidates = ("open",) if sys.platform == "darwin" else VIEWERS
    return next(filter(None, map(shutil.which, candidates)), None)


def show(text: str, path: Path) -> None:
    """Draw the sheet to ``path`` and open it in a window.

    The viewer runs on its own, so the terminal is free at once and the
    window stays open after fretgrep ends.
    """
    program = viewer()
    if program is None:
        raise ViewerMissingError(", ".join(VIEWERS))
    path.parent.mkdir(parents=True, exist_ok=True)
    write(text, path)
    subprocess.Popen(  # pylint: disable=consider-using-with
        [program, str(path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
