"""Tests for the tones of chords and scales."""
# pylint: disable=missing-function-docstring

import pytest

from fretgrep import theory


def tones(text: str) -> list[str]:
    """Return the tones of each line of the answer."""
    lines = theory.parse(text).describe().splitlines()
    return [line.split(": ")[1].split("  [")[0] for line in lines if ": " in line]


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("G7", "G B D F"),
        ("Cmaj7", "C E G B"),
        ("CΔ7", "C E G B"),
        ("CM7", "C E G B"),
        ("Dm7b5", "D F Ab C"),
        ("Bø", "B D F A"),
        ("C-7", "C Eb G Bb"),
        ("F#m7", "F# A C# E"),
        ("Hm7", "B D F# A"),
        ("Bbo7", "Bb Db Fb Abb"),
        ("Ab+7", "Ab C E Gb"),
        ("Cm(maj7)", "C Eb G B"),
        ("E7sus4", "E A B D"),
        ("C6/9", "C E G A D"),
        ("Cadd9", "C E G D"),
        ("G7b9#11", "G B D F Ab C#"),
        ("C13#11", "C E G Bb D F# A"),
        ("Am", "A C E"),
    ],
)
def test_chords(symbol, expected):
    assert tones(symbol) == [expected]


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("C dur", "C D E F G A B"),
        ("A moll", "A B C D E F G"),
        ("Eb mixolydisch", "Eb F G Ab Bb C Db"),
        ("G HM5", "G Ab B C D Eb F"),
        ("Db lydisch dominant", "Db Eb F G Ab Bb Cb"),
        ("G alteriert", "G Ab Bb B Db Eb F"),
        ("Bb Blues", "Bb Db Eb E F Ab"),
        ("A Moll Bluestonleiter", "A C D D# E G"),
        ("C Dur-Blues", "C D Eb E G A"),
        ("G major blues", "G A Bb B D E"),
        ("C HTGT", "C Db Eb E F# G A Bb"),
        ("A Moll-Pentatonik", "A C D E G"),
        ("B HM2", "B C D E F G# A"),
    ],
)
def test_scales(symbol, expected):
    assert tones(symbol) == [expected]


@pytest.mark.parametrize("symbol", ["G7HM5", "G7 HM5", "g7 hm5", "G7 Tonleiter HM5"])
def test_chord_with_scale(symbol):
    assert tones(symbol) == ["G B D F", "G Ab B C D Eb F"]
    assert "5. Modus von C harmonisch Moll" in theory.tones(symbol)


def test_intervals_are_named():
    assert "[Intervalle 1 b2 3 4 5 b6 b7]" in theory.tones("G HM5")
    assert "[Intervalle 1 3 5 b7 b9 #11]" in theory.tones("G7b9#11")


@pytest.mark.parametrize("symbol", ["Xyz", "C quatsch", "", "G7b4"])
def test_unknown_symbols_explain_themselves(symbol):
    with pytest.raises(theory.SymbolError):
        theory.parse(symbol)
    assert theory.tones(symbol)  # a message, no exception
