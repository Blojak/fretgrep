"""The logo that fretgrep draws in the terminal.

A fretboard with a few marked notes next to the name. With colour, the
notes and the word "grep" are red, the way grep highlights its matches.
"""

import re
from html import escape
from importlib import metadata

NOTE = "●"
TAGLINE = "find licks, hear them, read them"
_FRETBOARD = [
    "e ║───┼───┼───┼───┼───┼───┤",
    "B ║───┼───┼─●─┼───┼───┼───┤",
    "G ║───┼───┼───┼─●─┼───┼───┤",
    "D ║───┼─●─┼───┼───┼───┼───┤",
    "A ║───┼───┼─●─┼───┼───┼───┤",
    "E ║───┼───┼───┼───┼───┼───┤",
]
_FRET = [
    r"  __         _   ",
    r" / _|_ _ ___| |_ ",
    r"|  _| '_/ -_)  _|",
    r"|_| |_| \___|\__|",
    r"                 ",
]
_GREP = [
    r"                   ",
    r" __ _ _ _ ___ _ __ ",
    "/ _` | '_/ -_) '_ \\",  # a raw string cannot end in a backslash
    r"\__, |_| \___| .__/",
    r"|___/        |_|   ",
]

_MATCH = "\033[1;31m"
_DIM = "\033[2m"
_RESET = "\033[0m"


# The README shows the logo as an SVG drawn from the coloured text.
_SVG_FONT_SIZE = 14
_SVG_CHAR = 8.4  # width of one character at that size in a monospace font
_SVG_LINE = 19
_SVG_PAD = 18
_SVG_CLASS = {_MATCH: "match", _DIM: "dim", _RESET: "text"}
_ANSI = re.compile(r"(\033\[[0-9;]*m)")


def version() -> str:
    """Return the name and version, as shown by ``fretgrep --version``."""
    return f"fretgrep {metadata.version('fretgrep')}"


def render(color: bool = False) -> str:
    """Return the logo as text, with ANSI colours if asked for."""
    match, dim, reset = (_MATCH, _DIM, _RESET) if color else ("", "", "")
    names = [fret + match + grep + reset for fret, grep in zip(_FRET, _GREP)]
    names.append(TAGLINE)
    lines = []
    for board, name in zip(_FRETBOARD, names):
        strings = f"{reset}{match}{NOTE}{reset}{dim}".join(board[2:].split(NOTE))
        lines.append(f" {board[:2]}{dim}{strings}{reset}   {name}".rstrip())
    return "\n".join(lines) + "\n"


def svg() -> str:
    """Return the logo as an SVG image with the terminal colours.

    docs/logo.svg holds its output; a test keeps the two the same.
    """
    lines = render(color=True).splitlines()
    plain = [_ANSI.sub("", line) for line in lines]
    width = round(2 * _SVG_PAD + max(map(len, plain)) * _SVG_CHAR)
    height = 2 * _SVG_PAD + len(lines) * _SVG_LINE
    rows = []
    for number, (line, text) in enumerate(zip(lines, plain)):
        style, spans = "text", []
        for part in _ANSI.split(line):
            if part in _SVG_CLASS:
                style = _SVG_CLASS[part]
            elif part:
                spans.append(f'<tspan class="{style}">{escape(part)}</tspan>')
        baseline = _SVG_PAD + (number + 1) * _SVG_LINE - 5
        rows.append(
            f'  <text x="{_SVG_PAD}" y="{baseline}" '
            f'textLength="{len(text) * _SVG_CHAR:g}" lengthAdjust="spacing">'
            + "".join(spans) + "</text>"
        )
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="fretgrep: {TAGLINE}">',
        "  <style>",
        "    text { font-family: ui-monospace, 'DejaVu Sans Mono', Menlo, "
        f"Consolas, monospace; font-size: {_SVG_FONT_SIZE}px; "
        "white-space: pre; }",
        "    .text { fill: #e6e6e6; }",
        "    .dim { fill: #7a7f8c; }",
        "    .match { fill: #ff5c57; font-weight: bold; }",
        "  </style>",
        f'  <rect width="{width}" height="{height}" rx="10" fill="#1d1f24"/>',
        *rows,
        "</svg>",
    ]) + "\n"
