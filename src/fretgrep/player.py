"""Play recordings with mpv, with tempo, pitch and A-B loop.

mpv runs in the terminal and keeps its own keyboard control. The
rubberband filter changes tempo and pitch independently of each other.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

PLAYER = "mpv"


class PlayerMissingError(RuntimeError):
    """mpv is not installed."""


def pitch_scale(semitones: float) -> float:
    """Return the frequency factor of a pitch shift in semitones."""
    return 2 ** (semitones / 12)


def parse_loop(text: str) -> tuple[float, float]:
    """Read an A-B loop given as "START-END" in seconds.

    Raises ValueError unless both are numbers and the start comes first.
    """
    start_text, _, end_text = text.partition("-")
    start, end = float(start_text), float(end_text)
    if not 0 <= start < end:
        raise ValueError(text)
    return start, end


def build_command(
    playlist: Path,
    speed: float = 1.0,
    semitones: float = 0.0,
    loop: tuple[float, float] | None = None,
) -> list[str]:
    """Return the mpv command line that plays an M3U playlist.

    mpv prints each entry's title when it starts playing it and shows the
    titles in its playlist (F8).
    """
    command = [
        PLAYER,
        "--no-audio-display",
        f"--speed={speed:g}",
        f"--af=rubberband=pitch-scale={pitch_scale(semitones):.6f}",
        "--term-playing-msg=Spielt: ${media-title}",
    ]
    if loop is not None:
        command += [f"--ab-loop-a={loop[0]:g}", f"--ab-loop-b={loop[1]:g}"]
    return command + [f"--playlist={playlist}"]


def play(command: list[str]) -> int:
    """Run the player in the foreground and return its exit code."""
    sys.stdout.flush()  # what fretgrep printed comes before mpv's output
    try:
        return subprocess.run(command, check=False).returncode
    except FileNotFoundError as error:
        raise PlayerMissingError(str(error)) from error


def play_files(
    files: list[tuple[Path, str]],
    speed: float = 1.0,
    semitones: float = 0.0,
    loop: tuple[float, float] | None = None,
) -> int:
    """Play files with their titles one after another; return the exit code.

    The files go to mpv as a temporary M3U playlist, which is the only way
    for mpv to know the titles of entries it has not played yet.
    """
    with tempfile.TemporaryDirectory(prefix="fretgrep-") as folder:
        playlist = Path(folder) / "wiedergabe.m3u"
        text = m3u([(path, None, title) for path, title in files])
        playlist.write_text(text, encoding="utf-8")
        return play(build_command(playlist, speed, semitones, loop))


def m3u(entries: list[tuple[Path, float | None, str]]) -> str:
    """Return an extended M3U playlist of files with durations and titles."""
    lines = ["#EXTM3U"]
    for path, duration, title in entries:
        seconds = -1 if duration is None else round(duration)
        title = " ".join(title.splitlines())
        lines += [f"#EXTINF:{seconds},{title}", str(path.resolve())]
    return "\n".join(lines) + "\n"
