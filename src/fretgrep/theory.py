"""Tones of chords and scales, spelled correctly, without a language model.

A symbol is a root followed by a chord, a scale or both, e.g. ``G7``,
``Dm7b5``, ``C lydisch`` or ``G7HM5``. HMn and MMn stand for the n-th
mode of harmonic and melodic minor, built on the given root: G HM5 is
the fifth mode of C harmonic minor. Note names are English: B is the
German H, Bb the German B. ``H`` is accepted as input for B.
"""

import re
from dataclasses import dataclass, replace

LETTERS = "CDEFGAB"
_NATURAL = (0, 2, 4, 5, 7, 9, 11)
_ACCIDENTALS = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "##"}
_ACCIDENTAL_INPUT = {"bb": -2, "b": -1, "♭": -1, "##": 2, "#": 1, "♯": 1}
_ROOT = re.compile(r"\s*([A-Ha-h])(bb|##|b|#|♭|♯)?")


class SymbolError(ValueError):
    """The text is not a known chord or scale."""


@dataclass(frozen=True)
class Interval:
    """An interval as letter steps and semitones above the root."""

    steps: int
    semitones: int

    @property
    def name(self) -> str:
        """Return the name relative to the major scale, e.g. "b3" or "#11"."""
        octave, step = divmod(self.steps, 7)
        offset = self.semitones - 12 * octave - _NATURAL[step]
        return _ACCIDENTALS[offset] + str(self.steps + 1)


@dataclass(frozen=True)
class Note:
    """A note name as letter index and accidental, e.g. Ab = (5, -1)."""

    letter: int
    accidental: int

    def __str__(self) -> str:
        return LETTERS[self.letter] + _ACCIDENTALS[self.accidental]

    @property
    def pitch_class(self) -> int:
        """Return 0 for C up to 11 for B."""
        return (_NATURAL[self.letter] + self.accidental) % 12

    def up(self, interval: Interval) -> "Note":
        """Return the note the interval above, spelled by letter steps."""
        letter = (self.letter + interval.steps) % 7
        offset = (self.pitch_class + interval.semitones - _NATURAL[letter]) % 12
        offset = offset - 12 if offset > 6 else offset
        if offset not in _ACCIDENTALS:
            raise SymbolError("Die Töne lassen sich nicht sinnvoll schreiben.")
        return Note(letter, offset)

    def down(self, interval: Interval) -> "Note":
        """Return the note the interval below."""
        return self.up(Interval(-interval.steps % 7, -interval.semitones % 12))


def _interval(name: str) -> Interval:
    """Read an interval name such as "b9", "#11" or "5"."""
    match = re.fullmatch(r"(bb|b|#)?(\d+)", name)
    if not match:
        raise ValueError(name)
    steps = int(match[2]) - 1
    octave, step = divmod(steps, 7)
    offset = _ACCIDENTAL_INPUT[match[1]] if match[1] else 0
    return Interval(steps, 12 * octave + _NATURAL[step] + offset)


def _intervals(names: str) -> tuple[Interval, ...]:
    return tuple(_interval(name) for name in names.split())


# --- Scales -----------------------------------------------------------------

_MAJOR = (0, 2, 4, 5, 7, 9, 11)
_HARMONIC_MINOR = (0, 2, 3, 5, 7, 8, 11)
_MELODIC_MINOR = (0, 2, 3, 5, 7, 9, 11)


def _mode(parent: tuple[int, ...], number: int) -> tuple[Interval, ...]:
    """Return the intervals of a mode of a seven-note scale (number from 1)."""
    start = parent[number - 1]
    return tuple(
        Interval(step, (parent[(number - 1 + step) % 7] - start) % 12)
        for step in range(7)
    )


@dataclass(frozen=True)
class Scale:
    """A named scale, with the parent scale it is a mode of, if any."""

    name: str
    intervals: tuple[Interval, ...]
    parent: str = ""
    mode: int = 0
    # The interval from the root of the parent scale up to this root.
    offset: Interval = Interval(0, 0)


def _modes(parent: tuple[int, ...], parent_name: str, names: list[str]):
    return [
        Scale(
            name,
            _mode(parent, number),
            parent_name,
            number,
            Interval(number - 1, parent[number - 1]),
        )
        for number, name in enumerate(names, start=1)
    ]


_MAJOR_MODES = _modes(
    _MAJOR,
    "Dur",
    ["Ionisch", "Dorisch", "Phrygisch", "Lydisch", "Mixolydisch", "Äolisch",
     "Lokrisch"],
)
_HM_MODES = _modes(
    _HARMONIC_MINOR,
    "harmonisch Moll",
    ["HM1 (harmonisch Moll)", "HM2 (Lokrisch 6)", "HM3 (Ionisch #5)",
     "HM4 (Dorisch #4)", "HM5 (Mixolydisch b9 b13, Phrygisch-Dominant)",
     "HM6 (Lydisch #2)", "HM7 (alteriert bb7)"],
)
_MM_MODES = _modes(
    _MELODIC_MINOR,
    "melodisch Moll",
    ["MM1 (melodisch Moll, Jazz-Moll)", "MM2 (Dorisch b2)",
     "MM3 (Lydisch übermäßig)", "MM4 (Lydisch b7, Lydisch-Dominant)",
     "MM5 (Mixolydisch b13)", "MM6 (Lokrisch 9)", "MM7 (alteriert)"],
)
# Written the way jazz books do, with a major third instead of a b4.
_MM_MODES[6] = replace(_MM_MODES[6], intervals=_intervals("1 b2 b3 3 b5 b6 b7"))
_OTHER = [
    Scale("Dur-Pentatonik", _intervals("1 2 3 5 6")),
    Scale("Moll-Pentatonik", _intervals("1 b3 4 5 b7")),
    Scale("Moll-Blues (Blues-Skala)", _intervals("1 b3 4 #4 5 b7")),
    Scale("Ganzton", _intervals("1 2 3 #4 #5 b7")),
    Scale("Halbton-Ganzton (HTGT, vermindert-dominantisch)",
          _intervals("1 b2 b3 3 #4 5 6 b7")),
    Scale("Ganzton-Halbton (GTHT, vermindert)", _intervals("1 2 b3 4 b5 #5 6 7")),
    Scale("Bebop-Dominant", _intervals("1 2 3 4 5 6 b7 7")),
    Scale("Bebop-Dur", _intervals("1 2 3 4 5 #5 6 7")),
    Scale("Dur-Blues", _intervals("1 2 b3 3 5 6")),
]

# Spellings, lower case without spaces and hyphens -> scale.
SCALES: dict[str, Scale] = {}


def _alias(scale: Scale, *names: str) -> None:
    for name in names:
        SCALES[name] = scale


for _scale, _names in zip(
    _MAJOR_MODES,
    [
        ("ionisch", "ionian", "dur", "major", "durtonleiter"),
        ("dorisch", "dorian"),
        ("phrygisch", "phrygian"),
        ("lydisch", "lydian"),
        ("mixolydisch", "mixolydian", "mixo"),
        ("äolisch", "aeolisch", "aeolian", "moll", "minor", "natürlichmoll",
         "naturalminor"),
        ("lokrisch", "locrian"),
    ],
):
    _alias(_scale, *_names)
for _number, _scale in enumerate(_HM_MODES, start=1):
    _alias(_scale, f"hm{_number}", f"harmonischmoll{_number}")
for _number, _scale in enumerate(_MM_MODES, start=1):
    _alias(_scale, f"mm{_number}", f"melodischmoll{_number}")
_alias(_HM_MODES[0], "harmonischmoll", "harmonicminor")
_alias(_HM_MODES[4], "phrygischdominant", "phrygiandominant", "mixob9b13",
       "mixolydischb9b13", "spanisch")
_alias(_MM_MODES[0], "melodischmoll", "melodicminor", "jazzmoll")
_alias(_MM_MODES[2], "lydischübermäßig", "lydianaugmented")
_alias(_MM_MODES[3], "lydischdominant", "lydiandominant", "lydischb7", "lydianb7")
_alias(_MM_MODES[4], "mixob13", "mixolydischb13")
_alias(_MM_MODES[5], "lokrisch9", "lokrisch2", "locrian2", "locriannatural9")
_alias(_MM_MODES[6], "alteriert", "altered", "alt", "superlocrian", "superlokrisch")
_alias(_OTHER[0], "durpentatonik", "pentatonik", "majorpentatonic", "pentatonic")
_alias(_OTHER[1], "mollpentatonik", "minorpentatonic")
_alias(_OTHER[2], "blues", "bluesskala", "bluesscale", "blues-skala", "mollblues",
       "minorblues", "mollbluesskala")
_alias(_OTHER[3], "ganzton", "ganztonleiter", "wholetone")
_alias(_OTHER[4], "htgt", "halbtonganzton", "halfwhole", "verminderdominantisch",
       "vermindertdominantisch")
_alias(_OTHER[5], "gtht", "ganztonhalbton", "wholehalf", "vermindert", "diminished")
_alias(_OTHER[6], "bebopdominant", "bebop")
_alias(_OTHER[7], "bebopdur", "bebopmajor")
_alias(_OTHER[8], "durblues", "majorblues", "durbluesskala")

_FILLER = re.compile(r"tonleiter|skala|scale|modus|mode|[\s\-_.,()]", re.IGNORECASE)


def _scale_key(text: str) -> str:
    return _FILLER.sub("", text).lower()


# --- Chords -----------------------------------------------------------------

# Chord qualities after normalisation -> intervals; longest are tried first.
_QUALITIES = {
    "": "1 3 5",
    "5": "1 5",
    "m": "1 b3 5",
    "dim": "1 b3 b5",
    "dim7": "1 b3 b5 bb7",
    "aug": "1 3 #5",
    "aug7": "1 3 #5 b7",
    "6": "1 3 5 6",
    "69": "1 3 5 6 9",
    "m6": "1 b3 5 6",
    "m69": "1 b3 5 6 9",
    "7": "1 3 5 b7",
    "9": "1 3 5 b7 9",
    "11": "1 3 5 b7 9 11",
    "13": "1 3 5 b7 9 13",
    "maj7": "1 3 5 7",
    "maj9": "1 3 5 7 9",
    "maj13": "1 3 5 7 9 13",
    "m7": "1 b3 5 b7",
    "m9": "1 b3 5 b7 9",
    "m11": "1 b3 5 b7 9 11",
    "m13": "1 b3 5 b7 9 13",
    "m7b5": "1 b3 b5 b7",
    "mmaj7": "1 b3 5 7",
    "mmaj9": "1 b3 5 7 9",
    "7alt": "1 3 b7 b9 #9 #11 b13",
}
# Other ways to write a quality -> the spelling in _QUALITIES, in this order.
_MAJ = r"(maj|Maj|MAJ|ma|Ma|Δ|\^|j|M)"
_SPELLINGS = (
    (re.compile(rf"^{_MAJ}(?=\d|$)"), "maj"),
    (re.compile(r"^(min|mi|-)"), "m"),
    (re.compile(rf"^m{_MAJ}"), "mmaj"),
    (re.compile(r"^(ø|Ø)7?"), "m7b5"),
    (re.compile(r"^(°|o)"), "dim"),
    (re.compile(r"^\+"), "aug"),
    (re.compile(r"^7?alt"), "7alt"),
)
_CHANGE = re.compile(r"(bb|b|#|add|sus|no)(\d*)")


@dataclass(frozen=True)
class Chord:
    """A chord symbol with its intervals."""

    symbol: str
    intervals: tuple[Interval, ...]


def _normalise_quality(text: str) -> str:
    text = re.sub(r"[\s()/,]", "", text)
    for pattern, replacement in _SPELLINGS:
        text = pattern.sub(replacement, text, count=1)
    return text


def _apply(names: list[str], kind: str, number: str) -> list[str]:
    """Apply one alteration such as b9, #11, add9, sus4 or no3."""
    def degree(name: str) -> str:
        return name.lstrip("b#")

    if kind == "sus":
        number = number or "4"
        names = [name for name in names if degree(name) != "3"]
        return [*names, number]
    if kind == "no":
        return [name for name in names if degree(name) != number]
    if kind == "add":
        return [*names, number]
    altered = kind + number
    if number == "5" or (number in ("9", "11", "13") and altered not in names):
        names = [name for name in names if name != number]
    return [*names, altered]


def chord(quality: str) -> Chord | None:
    """Return the chord for a quality without root, or None if unknown."""
    text = _normalise_quality(quality)
    base = next(
        (
            key
            for key in sorted(_QUALITIES, key=len, reverse=True)
            if text.startswith(key) and _is_changes(text[len(key):])
        ),
        None,
    )
    if base is None:
        return None
    names = _QUALITIES[base].split()
    for kind, number in _CHANGE.findall(text[len(base):]):
        if kind in ("bb", "b", "#") and number not in ("5", "9", "11", "13"):
            return None
        names = _apply(names, kind, number)
    intervals = sorted(set(map(_interval, names)), key=lambda i: (i.steps, i.semitones))
    return Chord(quality, tuple(intervals))


def _is_changes(text: str) -> bool:
    return "".join(match[0] for match in _CHANGE.finditer(text)) == text


# --- Reading a symbol --------------------------------------------------------


@dataclass(frozen=True)
class Answer:
    """The tones of a chord and/or scale on one root."""

    root: Note
    chord: Chord | None
    scale: Scale | None

    def describe(self) -> str:
        """Return the answer as text, one line per chord and scale."""
        lines = []
        if self.chord is not None:
            label = f"Akkord {self.root}{self.chord.symbol}"
            lines.append(_line(label, self.root, self.chord.intervals))
        if self.scale is not None:
            label = f"Skala {self.root} {self.scale.name}"
            lines.append(_line(label, self.root, self.scale.intervals))
            if self.scale.mode > 1:
                parent = self.root.down(self.scale.offset)
                lines.append(
                    f"  = {self.scale.mode}. Modus von {parent} {self.scale.parent}"
                )
        return "\n".join(lines)


def _line(label: str, root: Note, intervals) -> str:
    spelled = " ".join(str(root.up(interval)) for interval in intervals)
    names = " ".join(interval.name for interval in intervals)
    return f"{label}: {spelled}  [Intervalle {names}]"


def _root(text: str) -> tuple[Note, str]:
    match = _ROOT.match(text)
    if not match:
        raise SymbolError(f"Kein Grundton erkannt in {text!r}.")
    letter = "B" if match[1].upper() == "H" else match[1].upper()
    accidental = _ACCIDENTAL_INPUT[match[2]] if match[2] else 0
    return Note(LETTERS.index(letter), accidental), text[match.end():]


def parse(text: str) -> Answer:
    """Read a symbol such as "G7", "C lydisch" or "G7HM5".

    Raises SymbolError for anything unknown.
    """
    root, rest = _root(text.strip())
    key = _scale_key(rest)
    if key in SCALES and not chord_only(rest):
        return Answer(root, None, SCALES[key])
    found = chord(rest)
    if found is not None:
        return Answer(root, found, None)
    # A chord followed by a scale, e.g. "7HM5" or "maj7 lydisch".
    for split in range(1, len(rest)):
        scale = SCALES.get(_scale_key(rest[split:]))
        found = chord(rest[:split]) if scale else None
        if found is not None:
            return Answer(root, found, scale)
    raise SymbolError(
        f"{text!r} ist weder als Akkord noch als Skala bekannt. Skalen: "
        + ", ".join(dict.fromkeys(scale.name for scale in SCALES.values()))
    )


def chord_only(rest: str) -> bool:
    """Tell symbols that read as both chord and scale, such as "m", apart.

    "Cm" is the chord, "C moll" the scale.
    """
    return chord(rest) is not None and rest.strip() in ("m", "-", "alt", "7alt")


def tones(text: str) -> str:
    """Return the tones of a chord and/or scale as text, or why not."""
    try:
        return parse(text).describe()
    except SymbolError as error:
        return str(error)
