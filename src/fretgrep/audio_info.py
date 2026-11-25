"""Read technical audio properties from a file header."""

from dataclasses import dataclass
from pathlib import Path

import mutagen


@dataclass(frozen=True)
class AudioInfo:
    """Technical properties; None where they could not be determined."""

    duration_s: float | None = None
    sample_rate: int | None = None
    channels: int | None = None
    bitrate: int | None = None


def read_audio_info(path: Path) -> AudioInfo:
    """Return the audio properties of a file, empty if it is unreadable."""
    try:
        audio = mutagen.File(path)
    except (mutagen.MutagenError, OSError):
        return AudioInfo()
    info = getattr(audio, "info", None)
    if info is None:
        return AudioInfo()
    return AudioInfo(
        duration_s=getattr(info, "length", None),
        sample_rate=getattr(info, "sample_rate", None),
        channels=getattr(info, "channels", None),
        bitrate=getattr(info, "bitrate", None),
    )
