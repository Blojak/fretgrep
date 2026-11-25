"""Helpers that the commands of the command line share."""

import argparse
import sys
from pathlib import Path

from fretgrep import config, embeddings, player
from fretgrep.models import AutoTag, Recording

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_SCHEMA = 2

SPEED_ERROR = "Das Tempo muss größer als 0 sein."


def print_error(message: str) -> None:
    """Print a message for the user on standard error."""
    print(message, file=sys.stderr)


def library_folder(argument: str | None) -> Path | None:
    """Return the library folder, or None after printing why there is none."""
    library = Path(argument) if argument else config.library_path()
    if library is None:
        print_error(
            f"Kein Ordner angegeben und ${config.ENV_LIBRARY} ist nicht gesetzt."
        )
    elif not library.is_dir():
        print_error(f"Ordner nicht gefunden: {library}")
        library = None
    return library


def unknown_id(recording_id: int) -> int:
    """Say that there is no such recording; return the error code."""
    print_error(f"Keine Aufnahme mit ID {recording_id}.")
    return EXIT_ERROR


def count(entries: int) -> str:
    """Return a number of recordings in words, e.g. "1 Aufnahme"."""
    return f"{entries} Aufnahme" + ("" if entries == 1 else "n")


def format_duration(seconds: float | None) -> str:
    """Return a duration as "M:SS", or a placeholder if unknown."""
    if seconds is None:
        return "  ?  "
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def sorted_tags(tags: list[AutoTag]) -> list[AutoTag]:
    """Return the suggested tags, the most certain first."""
    return sorted(tags, key=lambda tag: (-tag.confidence, tag.category, tag.value))


def _compact_tags(tags: list[AutoTag]) -> str:
    """Format tags for one line; show each category/value pair only once."""
    best: dict[tuple[str, str], AutoTag] = {}
    for tag in sorted_tags(tags):
        best.setdefault((tag.category, tag.value), tag)
    return ", ".join(
        f"{tag.category}={tag.value} ({tag.confidence:.1f})" for tag in best.values()
    )


def user_tags(recording: Recording) -> str:
    """Return the recording's own tags, sorted and comma-separated."""
    return ", ".join(sorted(tag.tag for tag in recording.user_tags))


def print_recording(recording: Recording) -> None:
    """Print the compact form used by ``list`` and ``search``."""
    file = recording.file
    flag = "  [fehlt]" if file.missing else ""
    print(
        f"{recording.id:>5}  {format_duration(file.duration_s):>5}  "
        f"{file.rel_path}{flag}"
    )
    if recording.user_tags:
        print(f"       Eigene Tags: {user_tags(recording)}")
    if recording.note:
        print(f"       Notiz:       {recording.note.text.splitlines()[0]}")
    print(f"       Vorschläge:  {_compact_tags(recording.tags) or '-'}")


def embedder() -> tuple[embeddings.Embedder, str] | str:
    """Return the embedder and its model name, or the reason there is none."""
    model_name = config.embed_model()
    if not model_name:
        return f"Bitte ${config.ENV_EMBED_MODEL} setzen."
    urls = config.ollama_urls()
    url = embeddings.first_reachable(urls)
    if url is None:
        return f"Kein Ollama-Server erreichbar (versucht: {', '.join(urls)})."
    return embeddings.ollama_embedder(url, model_name), model_name


def embedding_failed(error: embeddings.EmbeddingError) -> str:
    """Return the message for a failed request to the embedding server."""
    return f"Der Ollama-Server antwortet nicht richtig: {error}."


def play_hits(
    hits: list[tuple[int, str]],
    args: argparse.Namespace,
    loop: tuple[float, float] | None = None,
) -> int:
    """Play recordings given by ID and library path; return the exit code.

    Missing files are skipped. mpv shows each recording's ID while playing.
    """
    library = library_folder(args.library)
    if library is None:
        return EXIT_ERROR
    present = [hit for hit in hits if (library / hit[1]).is_file()]
    if len(present) < len(hits):
        print_error(
            f"Hinweis: {len(hits) - len(present)} Datei(en) nicht gefunden "
            "und übersprungen."
        )
    if not present:
        return EXIT_ERROR
    files = [(library / rel_path, f"ID {recording_id}  {rel_path}")
             for recording_id, rel_path in present]
    keys = "Tasten: Leertaste Pause, Pfeile springen, [ ] Tempo, "
    if len(files) > 1:
        keys += "< > voriges/nächstes Stück, F8 Liste zeigen, "
    print(keys + "l A-B-Loop setzen, L ganze Datei wiederholen, q beenden")
    try:
        code = player.play_files(files, args.speed, args.pitch, loop)
    except player.PlayerMissingError:
        print_error(
            "mpv ist nicht installiert. Bitte 'sudo apt install mpv' ausführen."
        )
        return EXIT_ERROR
    return EXIT_OK if code == 0 else EXIT_ERROR
