"""Tests for the sheet music export; LilyPond runs only if installed."""
# pylint: disable=missing-function-docstring

import shutil

import pytest

from fretgrep import notes, sheet
from fretgrep.notes import Note
from fretgrep.rhythm import Event, Rhythm

LINE = [
    Note(1.0, 1.2, 60, 0.7),
    Note(1.2, 1.4, 63, 0.7),
    Note(3.0, 3.5, 40, 0.6),
    Note(3.02, 3.5, 66, 0.6),
]
PHRASES = notes.phrases(LINE, 0.5)


def test_pitch_names():
    assert [sheet.pitch(number) for number in (40, 48, 59, 60, 61, 66, 84)] == [
        "e,", "c", "b", "c'", "des'", "fis'", "c'''",
    ]


def test_source_has_one_line_per_phrase():
    lines = sheet.source(PHRASES, "a.mp3").splitlines()

    assert (
        r"""    \omit Stem c'4^\markup \small "1.0s" \bar "" ees'4"""
        r""" \undo \omit Stem \bar "|" \break"""
    ) in lines
    assert (
        r"""    \omit Stem <e, fis'>4^\markup \small "3.0s" \undo \omit Stem"""
        r""" \bar "|" \break"""
    ) in lines
    assert r'    \clef "treble_8"' in lines


def note(pitch):
    return (Note(0.0, 0.1, pitch, 0.9),)


def test_note_values_are_beamed_within_a_beat():
    events = (
        Event(2, 2, note(60)),             # eighth off the beat
        Event(4, 2, note(62)),             # two eighths in one beat: beamed
        Event(6, 2, note(64)),
        Event(8, 1, note(65)),             # two sixteenths and an eighth
        Event(9, 1, note(67)),
        Event(10, 2, note(69)),
        Event(12, 6, note(71)),            # dotted quarter
        Event(18, 2),                      # eighth rest
        Event(20, 10, note(72) + note(76)),  # half note tied to an eighth
    )
    rhythms = [Rhythm(events, 112.4, 0.1), None]

    lines = sheet.source(PHRASES, "a.mp3", rhythms=rhythms).splitlines()

    expected = " ".join([
        r"""    c'8^\markup \small "1.0s, Tempo 112" \bar "" d'8[ e'8] \bar""",
        '""',
        r"""f'16[ g'16 a'8] \bar "" b'4. r8 \bar "" <c'' e''>2~ <c'' e''>8""",
        r"""\bar "|" \break""",
    ])
    assert expected in lines
    assert any(line.startswith(r"    \omit Stem <e, fis'>4") for line in lines)


def test_title_is_escaped():
    text = sheet.source(PHRASES, 'a "b" \\ c.mp3', "x")

    assert r'title = "a \"b\" \\ c.mp3"' in text


def test_no_notes_still_gives_a_valid_score():
    assert "    s4" in sheet.source([], "a.mp3")


def test_write_source(tmp_path):
    path = tmp_path / "lick.ly"

    sheet.write(sheet.source(PHRASES, "a.mp3"), path)

    assert path.read_text(encoding="utf-8").startswith(r"\version")


def test_unknown_format(tmp_path):
    with pytest.raises(ValueError):
        sheet.write("x", tmp_path / "lick.docx")


def test_missing_engraver(tmp_path, monkeypatch):
    monkeypatch.setattr(sheet, "ENGRAVER", "lilypond-gibt-es-nicht")

    with pytest.raises(sheet.EngraverMissingError):
        sheet.write("x", tmp_path / "lick.pdf")


@pytest.mark.skipif(shutil.which(sheet.ENGRAVER) is None, reason="needs LilyPond")
def test_lilypond_draws_the_sheet(tmp_path):
    text = sheet.source(PHRASES, 'a "b".mp3', "sub")

    sheet.write(text, tmp_path / "lick.pdf")
    sheet.write(text, tmp_path / "lick.svg")

    assert (tmp_path / "lick.pdf").read_bytes().startswith(b"%PDF")
    assert "<svg" in (tmp_path / "lick.svg").read_text(encoding="utf-8")
    with pytest.raises(sheet.EngraverError):
        sheet.write(r'\version "2.24.0" { c4 ', tmp_path / "broken.pdf")


@pytest.mark.skipif(shutil.which(sheet.ENGRAVER) is None, reason="needs LilyPond")
def test_lilypond_draws_note_values(tmp_path):
    events = (
        Event(2, 2, note(60)), Event(4, 2, note(62)), Event(6, 2, note(64)),
        Event(8, 3, note(65)), Event(11, 1, note(67)), Event(12, 4),
        Event(16, 20, note(72)),
    )
    text = sheet.source(PHRASES, "a.mp3", rhythms=[Rhythm(events, 100, 0.1), None])

    sheet.write(text, tmp_path / "lick.pdf")

    assert (tmp_path / "lick.pdf").read_bytes().startswith(b"%PDF")


def test_show_draws_and_opens_without_waiting(tmp_path, monkeypatch):
    drawn, started = [], []
    monkeypatch.setattr(sheet, "viewer", lambda: "/usr/bin/xdg-open")
    monkeypatch.setattr(sheet, "write", lambda text, path: drawn.append((text, path)))
    def popen(command, **options):
        started.append((command, options))

    monkeypatch.setattr(sheet.subprocess, "Popen", popen)
    target = tmp_path / "sheets" / "notes-1.pdf"

    sheet.show("source", target)

    assert target.parent.is_dir() and drawn == [("source", target)]
    command, options = started[0]
    assert command == ["/usr/bin/xdg-open", str(target)]
    assert options["start_new_session"] is True


def test_show_without_viewer(monkeypatch, tmp_path):
    monkeypatch.setattr(sheet, "viewer", lambda: None)
    with pytest.raises(sheet.ViewerMissingError):
        sheet.show("source", tmp_path / "x.pdf")
