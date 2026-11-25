"""Estimate note values for recognised notes.

The recognition gives onset times in seconds. This module lays a grid of
eighth notes over each phrase and follows the playing note by note, so a
changing tempo does not add up to an error. Swing is expected: an eighth
off the beat may come late without counting as a deviation.

The result is an estimate. There are no bars, because nothing in a solo
recording says where a bar begins.
"""

import statistics
from dataclasses import dataclass

from fretgrep.notes import Note

Chord = list[Note]

# Phrases with fewer onsets say too little about the tempo.
MIN_ONSETS = 6
# Gaps shorter than this are two notes of one chord or a slur, not a beat.
MIN_GAP_S = 0.06
# An eighth off the beat may be this late (in eighths) and still be on time:
# triplet swing delays it by a third of an eighth pair.
MAX_SWING = 0.34
# How strongly one onset corrects the grid position and the tempo.
POSITION_GAIN = 0.5
TEMPO_GAIN = 0.1
# The first guess (the usual gap between onsets) can be a swung eighth,
# so the tempo of a recording is searched this far around it ...
RECORDING_STEPS = [step / 100 for step in range(-36, 37, 2)]
# ... and each phrase may then differ from the recording by this much.
PHRASE_STEPS = [step / 100 for step in range(-8, 9, 2)]
# A note that stops this many eighths before the next one leaves a rest.
MIN_REST = 2
LAST_NOTE_MAX = 4
# Readings that squeeze two onsets into one eighth must fit clearly better.
DOUBLE_COST = 0.5
# Of two readings that fit alike, the one that needs fewer eighths wins:
# swung eighths also fit a faster grid as quarter plus eighth.
SPAN_COST = 0.05


@dataclass(frozen=True)
class Event:
    """Notes or a rest of ``length`` sixteenths starting at ``position``.

    Positions count sixteenths from the first beat of the phrase grid;
    a beat is four sixteenths. ``chord`` is empty for a rest.
    """

    position: int
    length: int
    chord: tuple[Note, ...] = ()


@dataclass(frozen=True)
class Rhythm:
    """The estimated rhythm of one phrase."""

    events: tuple[Event, ...]
    bpm: float
    deviation: float


def _gaps(onsets: list[float]) -> list[float]:
    return [b - a for a, b in zip(onsets, onsets[1:]) if b - a > MIN_GAP_S]


def _deviation(place: float, slot: int) -> float:
    """Return how far a position (in eighths) is from where the slot expects it."""
    late = place - slot
    if slot % 2 == 0 or late < 0:
        return late
    return max(0.0, late - MAX_SWING)  # off the beat: swing may delay it


def _nearest_slot(place: float) -> int:
    return min(
        range(int(place) - 1, int(place) + 3),
        key=lambda slot: abs(_deviation(place, slot)),
    )


def _follow(onsets: list[float], eighth: float, first_slot: int, first_late: float):
    """Assign each onset an eighth slot; return (slots, deviation, eighth).

    Even slots are beats. ``first_late`` says how late (in eighths) the
    first onset is taken to be. The grid moves with the playing: each
    onset is placed relative to the one before, then pulls the grid
    position and the tempo a little towards itself.
    """
    slot = first_slot
    grid_time = onsets[0] - first_late * eighth  # where the grid has the slot
    slots = [slot]
    total = 0.0
    for onset in onsets[1:]:
        place = slot + (onset - grid_time) / eighth
        new = _nearest_slot(place)
        if new <= slot:
            slots.append(slot)  # two onsets in one eighth
            continue
        error = _deviation(place, new)
        grid_time += (new - slot + POSITION_GAIN * error) * eighth
        eighth *= 1 + TEMPO_GAIN * error / (new - slot)
        total += abs(error)
        slot = new
        slots.append(slot)
    return slots, total / len(onsets), eighth


# How the first onset may sit on the grid: (slot, lateness in eighths).
_STARTS = [(0, 0.0), (1, 0.0), (1, MAX_SWING / 2), (1, MAX_SWING)]


def _fit(onsets: list[float], guess: float, steps: list[float]):
    """Try tempi around the guess and the possible starts.

    Return (cost, slots, deviation, eighth) of the best reading.
    """
    readings = []
    for step in steps:
        for first_slot, first_late in _STARTS:
            slots, deviation, eighth = _follow(
                onsets, guess * (1 + step), first_slot, first_late
            )
            doubled = len(slots) - len(set(slots))
            # two onsets in one eighth cost nothing above, so charge them here
            cost = deviation + DOUBLE_COST * doubled / len(slots)
            cost += SPAN_COST * (slots[-1] - slots[0]) / len(slots)
            readings.append((cost, slots, deviation, eighth))
    return min(readings, key=lambda reading: round(reading[0], 9))


def _events(phrase: list[Chord], slots: list[int], eighth: float) -> list[Event]:
    """Turn slots into notes and rests with lengths in sixteenths."""
    groups: dict[int, list[Chord]] = {}
    for chord, slot in zip(phrase, slots):
        groups.setdefault(slot, []).append(chord)
    order = sorted(groups)
    events = []
    for index, slot in enumerate(order):
        chords = groups[slot][:2]  # more than two onsets per eighth: drop
        last = chords[-1]
        sounding = max(note.end for note in last) - last[0].start
        sounding = max(1, round(sounding / eighth))
        if index + 1 < len(order):
            length = order[index + 1] - slot
            rest = length - sounding if length - sounding >= MIN_REST else 0
            length -= rest
        else:
            length, rest = min(sounding, LAST_NOTE_MAX), 0
        position = slot * 2
        if len(chords) == 2:
            events.append(Event(position, 1, tuple(chords[0])))
            events.append(Event(position + 1, length * 2 - 1, tuple(chords[1])))
        else:
            events.append(Event(position, length * 2, tuple(chords[0])))
        if rest:
            events.append(Event(position + length * 2, rest * 2))
    return events


def _onsets(phrase: list[Chord]) -> list[float]:
    return [chord[0].start for chord in phrase]


def _is_long(phrase: list[Chord]) -> bool:
    return len(_gaps(_onsets(phrase))) >= MIN_ONSETS - 1


def recording_eighth(phrases: list[list[Chord]]) -> float | None:
    """Return the length of an eighth that fits the whole recording best."""
    long_phrases = [_onsets(phrase) for phrase in phrases if _is_long(phrase)]
    gaps = [gap for onsets in long_phrases for gap in _gaps(onsets)]
    if not gaps:
        return None
    guess = statistics.median(gaps)

    def cost(step: float) -> float:
        return sum(
            _fit(onsets, guess * (1 + step), [0.0])[0] * len(onsets)
            for onsets in long_phrases
        )

    return guess * (1 + min(RECORDING_STEPS, key=cost))


def estimate(
    phrases: list[list[Chord]], bpm: float | None = None
) -> list[Rhythm | None]:
    """Estimate the rhythm of each phrase; None where it is too short to tell.

    ``bpm`` fixes the tempo of the recording in quarter notes per minute
    instead of searching for it; each phrase may still differ a little.
    """
    eighth = 30 / bpm if bpm else recording_eighth(phrases)
    result: list[Rhythm | None] = []
    for phrase in phrases:
        if eighth is None or not _is_long(phrase):
            result.append(None)
            continue
        onsets = _onsets(phrase)
        _, slots, deviation, fitted = _fit(onsets, eighth, PHRASE_STEPS)
        events = tuple(_events(phrase, slots, fitted))
        # average tempo over the phrase; the grid itself moves with the playing
        played = (onsets[-1] - onsets[0]) / max(1, slots[-1] - slots[0])
        result.append(Rhythm(events, 30 / played, deviation))
    return result
