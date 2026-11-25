"""Tests for the rhythm estimate, on licks built from a known rhythm."""
# pylint: disable=missing-function-docstring,unbalanced-tuple-unpacking

import random

import pytest

from fretgrep import rhythm
from fretgrep.notes import Note

EIGHTH = 0.27  # seconds; a quarter note at about 111 per minute

# Eighth slots; even slots are beats.
CHAIN = list(range(16))
PICKUP = [1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 14, 16, 17, 18]
MIXED = [0, 2, 3, 4, 6, 7, 8, 10, 12, 13, 14, 16]


def phrase(slots, *, swing=0.0, jitter=0.0, drift=0.0, seed=1):
    """Return a phrase whose onsets follow the slots.

    ``swing`` delays the eighths off the beat (in eighths), ``jitter`` is
    the spread of the timing in seconds, ``drift`` the relative change of
    the tempo over the phrase.
    """
    noise = random.Random(seed)
    chords, time, previous = [], 1.0, slots[0]
    for index, slot in enumerate(slots):
        current = EIGHTH * (1 + drift * index / len(slots))
        time += (slot - previous) * current
        previous = slot
        onset = time + (swing * current if slot % 2 else 0.0)
        onset += noise.gauss(0, jitter)
        chords.append([Note(onset, onset + 0.8 * current, 60 + index, 0.9)])
    return chords


def positions(result):
    """Return the positions of the notes in eighths."""
    return [event.position // 2 for event in result.events if event.chord]


@pytest.mark.parametrize("slots", [CHAIN, PICKUP, MIXED])
@pytest.mark.parametrize("swing", [0.2, 0.33])
@pytest.mark.parametrize("drift", [0.0, 0.1, -0.1])
def test_swung_lines_are_recovered_with_their_beats(slots, swing, drift):
    played = phrase(slots, swing=swing, jitter=0.01, drift=drift)

    (result,) = rhythm.estimate([played])

    assert positions(result) == slots


@pytest.mark.parametrize("slots", [CHAIN, PICKUP, MIXED])
def test_straight_lines_keep_their_distances(slots):
    # without swing nothing tells where the beat is, only the distances
    (result,) = rhythm.estimate([phrase(slots, jitter=0.01)])

    found = positions(result)
    assert [slot - found[0] for slot in found] == [slot - slots[0] for slot in slots]


def test_tempo_is_reported_in_quarter_notes_per_minute():
    (result,) = rhythm.estimate([phrase(CHAIN, swing=0.2)])

    assert result.bpm == pytest.approx(30 / EIGHTH, rel=0.03)
    assert result.deviation < 0.05


def test_given_tempo_is_used_instead_of_searching():
    played = phrase(CHAIN, swing=0.33)

    (half,) = rhythm.estimate([played], bpm=30 / EIGHTH / 2)

    # at half the tempo two played eighths share one eighth of the grid
    assert len(set(positions(half))) < len(CHAIN)


def test_lengths_fill_the_time_to_the_next_note():
    (result,) = rhythm.estimate([phrase(MIXED, swing=0.2)])

    lengths = [event.length for event in result.events]
    assert lengths[:4] == [4, 2, 2, 4]
    assert sum(lengths[:-1]) == 2 * (MIXED[-1] - MIXED[0])


def test_silence_becomes_a_rest():
    slots = [0, 1, 2, 3, 4, 10, 11, 12]

    (result,) = rhythm.estimate([phrase(slots, swing=0.2)])

    rests = [event for event in result.events if not event.chord]
    assert [(rest.position, rest.length) for rest in rests] == [(10, 10)]


def test_two_onsets_in_one_eighth_become_sixteenths():
    played = phrase(CHAIN, swing=0.2)
    extra = played[4][0].start + EIGHTH / 2
    played.insert(5, [Note(extra, extra + 0.1, 80, 0.9)])

    (result,) = rhythm.estimate([played])

    pair = [event for event in result.events if event.position in (8, 9)]
    assert [event.length for event in pair] == [1, 1]
    assert pair[1].chord[0].pitch == 80


def test_short_phrases_get_no_rhythm():
    short = phrase([0, 1, 2])

    assert rhythm.estimate([short]) == [None]
    assert rhythm.estimate([short, phrase(CHAIN)])[0] is None
    assert not rhythm.estimate([])


def test_phrases_of_one_recording_share_the_tempo():
    first = phrase(MIXED, swing=0.33, seed=1)
    second = phrase(CHAIN, swing=0.33, seed=2)

    one, two = rhythm.estimate([first, second])

    assert one.bpm == pytest.approx(two.bpm, rel=0.05)
    assert positions(one) == MIXED
