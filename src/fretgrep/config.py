"""Settings read from environment variables."""

import os
from pathlib import Path

ENV_DB = "FRETGREP_DB"
ENV_LIBRARY = "FRETGREP_LIBRARY"
ENV_WHISPER_MODEL = "FRETGREP_WHISPER_MODEL"
ENV_WHISPER_LANGUAGE = "FRETGREP_WHISPER_LANGUAGE"
ENV_OLLAMA_URL = "FRETGREP_OLLAMA_URL"
ENV_EMBED_MODEL = "FRETGREP_EMBED_MODEL"
ENV_CHAT_MODEL = "FRETGREP_CHAT_MODEL"
# The project used to be called woodshed. Its variable names and its
# database file still work, so that nothing breaks after the rename.
LEGACY_PREFIX = "WOODSHED_"

DEFAULT_DB_PATH = Path("~/.local/share/fretgrep/fretgrep.db")
LEGACY_DB_PATH = Path("~/.local/share/woodshed/woodshed.db")
DEFAULT_WHISPER_MODEL = "small"
DEFAULT_CHAT_MODEL = "qwen3.8:27b"
# Tried after the configured addresses: Ollama's own default, then the
# address of a libvirt host, which is the same from a VM and on the host.
DEFAULT_OLLAMA_URLS = ("http://localhost:11434", "http://192.168.122.1:11434")


def _env(name: str) -> str:
    """Return a setting, falling back to its name from before the rename."""
    legacy = LEGACY_PREFIX + name.removeprefix("FRETGREP_")
    return os.environ.get(name) or os.environ.get(legacy) or ""


def cache_path() -> Path:
    """Return the folder for files that can be thrown away at any time."""
    base = os.environ.get("XDG_CACHE_HOME") or "~/.cache"
    return Path(base).expanduser() / "fretgrep"


def database_path() -> Path:
    """Return the path of the SQLite database file.

    Without a setting, the old database file is used as long as it exists
    and the new one does not.
    """
    if value := _env(ENV_DB):
        return Path(value).expanduser()
    path, legacy = DEFAULT_DB_PATH.expanduser(), LEGACY_DB_PATH.expanduser()
    return legacy if legacy.is_file() and not path.exists() else path


def library_path() -> Path | None:
    """Return the default library folder, or None if it is not configured."""
    value = _env(ENV_LIBRARY)
    return Path(value).expanduser() if value else None


def whisper_model() -> str:
    """Return the name of the Whisper model used for transcription."""
    return _env(ENV_WHISPER_MODEL) or DEFAULT_WHISPER_MODEL


def whisper_language() -> str | None:
    """Return the spoken language code, or None to detect it per file."""
    return _env(ENV_WHISPER_LANGUAGE) or None


def ollama_urls() -> list[str]:
    """Return the addresses to try for the Ollama server, in this order.

    The variable may hold several addresses separated by commas; the
    default addresses follow them.
    """
    configured = _env(ENV_OLLAMA_URL).split(",")
    urls = [url.strip().rstrip("/") for url in configured if url.strip()]
    return list(dict.fromkeys([*urls, *DEFAULT_OLLAMA_URLS]))


def chat_model() -> str:
    """Return the name of the language model for ``fretgrep chat``."""
    return _env(ENV_CHAT_MODEL) or DEFAULT_CHAT_MODEL


def embed_model() -> str | None:
    """Return the name of the embedding model, or None if not configured."""
    return _env(ENV_EMBED_MODEL) or None
