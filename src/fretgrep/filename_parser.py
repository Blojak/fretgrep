"""Turn a lick file name into tag suggestions with a confidence.

The parser never touches the database or the file itself. Everything it
returns is a suggestion; words it does not recognise are reported as
``unparsed`` instead of being guessed.
"""

import functools
import re
import tomllib
import unicodedata
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from importlib import resources
from pathlib import PurePosixPath

PARSER_VERSION = 1

SOURCE_FILENAME = "filename"
SOURCE_FOLDER = "folder"

CONF_EXACT = 0.9  # vocabulary hit or complete chord symbol
CONF_RULE = 0.7  # weaker rule, e.g. "lage 10" or a bare "Bbm"
CONF_FUZZY = 0.5  # typo match, ambiguous word or plain number
CONF_LETTER = 0.4  # single letter read as a chord
CONF_FOLDER = 0.3  # hint taken from a folder name only

FUZZY_MIN_LENGTH = 5
FUZZY_MIN_RATIO = 0.8

_SPLIT = re.compile(r"[\s,.]+")
_ALTERATION = re.compile(r"[b#](?:5|9|11|13)")
_CHORD = re.compile(
    r"(?P<root>[a-g][b#]?)"
    r"(?P<third>maj|min|j|m)?"
    r"(?P<number>7|6|9)?"
    r"(?P<flat5>b5)?"
    r"(?P<alt>alt)?"
    r"(?P<ext>(?:[b#](?:5|9|11|13))*)"
)
_VERSION = re.compile(r"v(\d+)")
_NUMBER = re.compile(r"\d{1,2}[a-z]?")

_ROMAN = {
    "i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6",
    "vii": "7", "viii": "8", "ix": "9", "x": "10", "xi": "11", "xii": "12",
}
_ORDINALS = {
    "erste": "1", "zweite": "2", "dritte": "3", "vierte": "4",
    "fünfte": "5", "sechste": "6", "siebte": "7", "achte": "8",
    "neunte": "9", "zehnte": "10", "elfte": "11", "zwölfte": "12",
}
_HEIGHTS = {"hohe": "high", "tiefe": "low"}

# (pattern, confidence, converter for group 1); applied in this order.
_POSITION_PATTERNS = (
    (
        re.compile(r"(?<![\w#])(\d{1,2})\s*\.?\s*(?:lage|position)\b", re.I),
        CONF_EXACT,
        lambda number: str(int(number)),
    ),
    (
        re.compile(r"\b(?:lage|position)\s+(\d{1,2})\b", re.I),
        CONF_RULE,
        lambda number: str(int(number)),
    ),
    (
        re.compile(rf"\b({'|'.join(sorted(_ROMAN, key=len, reverse=True))})"
                   r"\s*[.\s]\s*lage\b", re.I),
        CONF_EXACT,
        _ROMAN.__getitem__,
    ),
    (
        re.compile(rf"\b({'|'.join(_ORDINALS)})\s+(?:lage|position)\b", re.I),
        CONF_EXACT,
        _ORDINALS.__getitem__,
    ),
    (
        re.compile(rf"\b({'|'.join(_HEIGHTS)})\s+lage\b", re.I),
        CONF_RULE,
        _HEIGHTS.__getitem__,
    ),
)


@dataclass(frozen=True)
class TagSuggestion:
    """One suggested tag."""

    category: str
    value: str
    confidence: float
    source: str
    raw_token: str


@dataclass(frozen=True)
class ParseResult:
    """Outcome of parsing one relative path."""

    name: str
    tags: tuple[TagSuggestion, ...]
    unparsed: tuple[str, ...]


@dataclass(frozen=True)
class Alias:
    """One spelling from the vocabulary, split into lower-case tokens."""

    tokens: tuple[str, ...]
    category: str
    value: str
    confidence: float


@dataclass(frozen=True)
class Vocabulary:
    """Known spellings, filler words and explanations of tag values."""

    aliases: tuple[Alias, ...]
    stopwords: frozenset[str]
    descriptions: dict[str, str]


@functools.cache
def load_vocabulary() -> Vocabulary:
    """Load the vocabulary shipped with the package."""
    text = resources.files("fretgrep").joinpath("vocabulary.toml").read_text("utf-8")
    data = tomllib.loads(text)
    aliases = [
        Alias(tuple(spelling.split()), category, value, CONF_EXACT)
        for category, values in data["vocabulary"].items()
        for value, spellings in values.items()
        for spelling in spellings
    ]
    aliases += [
        Alias(
            tuple(entry["alias"].split()),
            entry["category"],
            entry["value"],
            CONF_FUZZY,
        )
        for entry in data.get("ambiguous", [])
    ]
    aliases.sort(key=lambda alias: len(alias.tokens), reverse=True)
    return Vocabulary(
        tuple(aliases),
        frozenset(data["stopwords"]["words"]),
        dict(data.get("descriptions", {})),
    )


def normalize_name(name: str) -> str:
    """Return the name NFC-normalised with whitespace trimmed and collapsed."""
    return " ".join(unicodedata.normalize("NFC", name).split())


def parse(rel_path: str) -> ParseResult:
    """Parse a path relative to the library into tag suggestions."""
    path = PurePosixPath(unicodedata.normalize("NFC", rel_path))
    vocabulary = load_vocabulary()
    tags, unparsed = _parse_text(path.stem, SOURCE_FILENAME, vocabulary)
    for folder in path.parts[:-1]:
        folder_tags, _ = _parse_text(folder, SOURCE_FOLDER, vocabulary)
        tags.extend(
            replace(tag, confidence=CONF_FOLDER)
            for tag in folder_tags
            if tag.category != "variant"
        )
    return ParseResult(
        normalize_name(path.stem), tuple(_deduplicate(tags)), tuple(unparsed)
    )


def suggest(text: str) -> tuple[TagSuggestion, ...]:
    """Return tag suggestions for free text such as a search term."""
    text = unicodedata.normalize("NFC", text)
    tags, _ = _parse_text(text, SOURCE_FILENAME, load_vocabulary())
    return tuple(_deduplicate(tags))


def _parse_text(
    text: str, source: str, vocabulary: Vocabulary
) -> tuple[list[TagSuggestion], list[str]]:
    """Parse one file or folder name."""
    tags, text = _extract_positions(text, source)
    tokens = [token for token in _SPLIT.split(text) if token]
    lowered = [token.lower() for token in tokens]
    unparsed = []
    index = 0
    while index < len(tokens):
        hit = _match_alias(lowered, index, vocabulary)
        if hit is None and lowered[index] in vocabulary.stopwords:
            index += 1
            continue
        if hit is None:
            hit = _match_rules(lowered, index)
        if hit is None:
            unparsed.append(tokens[index])
            index += 1
            continue
        found, consumed = hit
        raw = " ".join(tokens[index:index + consumed])
        tags.extend(
            TagSuggestion(category, value, confidence, source, raw)
            for category, value, confidence in found
        )
        index += consumed
    return tags, unparsed


def _extract_positions(text: str, source: str) -> tuple[list[TagSuggestion], str]:
    """Find fretboard positions and return them with the remaining text."""
    tags = []
    for pattern, confidence, convert in _POSITION_PATTERNS:
        for match in pattern.finditer(text):
            value = convert(match.group(1).lower())
            tags.append(
                TagSuggestion("position", value, confidence, source, match.group(0))
            )
        text = pattern.sub(" ", text)
    return tags, text


def _token_match(token: str, alias_token: str) -> float:
    """Return 1.0 for an exact match, 0.5 for a typo match, else 0.0."""
    if token == alias_token:
        return 1.0
    if min(len(token), len(alias_token)) < FUZZY_MIN_LENGTH:
        return 0.0
    ratio = SequenceMatcher(None, token, alias_token).ratio()
    return 0.5 if ratio >= FUZZY_MIN_RATIO else 0.0


def _match_alias(lowered: list[str], index: int, vocabulary: Vocabulary):
    """Match the longest vocabulary spelling starting at ``index``."""
    best = None
    best_key = (0, 0.0)
    for alias in vocabulary.aliases:
        window = lowered[index:index + len(alias.tokens)]
        if len(window) < len(alias.tokens):
            continue
        quality = min(map(_token_match, window, alias.tokens))
        key = (len(alias.tokens), quality)
        if quality and key > best_key:
            best, best_key = alias, key
    if best is None:
        return None
    confidence = best.confidence if best_key[1] == 1.0 else CONF_FUZZY
    return [(best.category, best.value, min(confidence, best.confidence))], len(
        best.tokens
    )


def _match_rules(lowered: list[str], index: int):
    """Apply the pattern rules to the token at ``index``."""
    token = lowered[index]
    following = lowered[index + 1] if index + 1 < len(lowered) else ""
    if _ALTERATION.fullmatch(token):
        return [("concept", token, CONF_RULE)], 1
    version = _VERSION.fullmatch(token)
    if version:
        return [("variant", f"v{version.group(1)}", CONF_EXACT)], 1
    if token == "variante" and following.isdigit():
        return [("variant", f"v{following}", CONF_EXACT)], 2
    if _NUMBER.fullmatch(token):
        return [("variant", f"nr {token}", CONF_FUZZY)], 1
    return _match_chord(lowered, index)


def _match_chord(lowered: list[str], index: int):
    """Read a chord symbol, including alterations written after a space."""
    match = _CHORD.fullmatch(lowered[index])
    if match is None:
        return None
    root = match["root"].capitalize()
    third = {"maj": "maj", "j": "maj", "min": "m", "m": "m"}.get(match["third"], "")
    number = match["number"] or ""
    flat5 = match["flat5"] or ""
    alt = match["alt"] or ""
    if alt and not number:
        number = "7"
    value = root + third + number + flat5 + alt + match["ext"]

    if number or flat5 or match["ext"]:
        confidence = CONF_EXACT
    elif third:
        confidence = CONF_RULE
    elif len(root) == 2:
        confidence = CONF_FUZZY
    else:
        confidence = CONF_LETTER

    consumed = 1
    if confidence == CONF_EXACT:
        for token in lowered[index + 1:]:
            if not _ALTERATION.fullmatch(token):
                break
            value += token
            consumed += 1

    found = [("chord", value, confidence)]
    if third == "m" and flat5:
        found.append(("tonality", "minor", CONF_FUZZY))
    return found, consumed


def _deduplicate(tags: list[TagSuggestion]) -> list[TagSuggestion]:
    """Keep one tag per category, value and source: the most confident."""
    best: dict[tuple[str, str, str], TagSuggestion] = {}
    for tag in tags:
        key = (tag.category, tag.value, tag.source)
        if key not in best or tag.confidence > best[key].confidence:
            best[key] = tag
    return list(best.values())
