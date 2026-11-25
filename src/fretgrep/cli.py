"""Command line interface ``fretgrep``."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from fretgrep import (
    arguments,
    banner,
    cli_chat,
    cli_playlist,
    completion,
    config,
    db,
    embeddings,
    notes,
    player,
    rhythm,
    search,
    sheet,
    theory,
    transcribe,
    user_meta,
)
from fretgrep import cli_common as common
from fretgrep.cli_common import EXIT_ERROR, EXIT_OK, EXIT_SCHEMA
from fretgrep.models import AutoFile, Recording
from fretgrep.scanner import ScanSummary, scan_library

__all__ = ["EXIT_ERROR", "EXIT_OK", "EXIT_SCHEMA", "main"]


def main(argv: list[str] | None = None) -> int:
    """Run the command line interface and return the exit code."""
    argv = sys.argv[1:] if argv is None else argv
    parser = _build_parser()
    if (not argv or argv[0] in arguments.LOGO_ARGUMENTS) and sys.stdout.isatty():
        print(banner.render(color="NO_COLOR" not in os.environ))
    if not argv:
        parser.print_help()
        return EXIT_OK
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except db.SchemaOutdatedError:
        common.print_error(
            f"Datenbank {config.database_path()} fehlt oder ist nicht aktuell. "
            "Bitte zuerst 'fretgrep db upgrade' ausführen."
        )
        return EXIT_SCHEMA


def _build_parser() -> argparse.ArgumentParser:
    return arguments.build(
        {
            "chat": lambda args: cli_chat.cmd_chat(args, main),
            "completion": _cmd_completion,
            "db_upgrade": _cmd_db_upgrade,
            "embed": _cmd_embed,
            "list": _cmd_list,
            "note": _cmd_note,
            "notes": _cmd_notes,
            "play": _cmd_play,
            "playlist_add": cli_playlist.cmd_add,
            "playlist_delete": cli_playlist.cmd_delete,
            "playlist_export": cli_playlist.cmd_export,
            "playlist_list": cli_playlist.cmd_list,
            "playlist_new": cli_playlist.cmd_new,
            "playlist_play": cli_playlist.cmd_play,
            "playlist_remove": cli_playlist.cmd_remove,
            "playlist_show": cli_playlist.cmd_play,
            "scan": _cmd_scan,
            "search": _cmd_search,
            "show": _cmd_show,
            "tag": _cmd_tag,
            "tones": _cmd_tones,
            "transcribe": _cmd_transcribe,
            "untag": _cmd_untag,
        }
    )


def _cmd_completion(args: argparse.Namespace) -> int:
    print(completion.script(_build_parser(), args.shell), end="")
    return EXIT_OK


def _cmd_db_upgrade(_args: argparse.Namespace) -> int:
    db_path = config.database_path()
    db.upgrade(db_path)
    with db.open_session(db_path) as session:
        search.rebuild(session)
        session.commit()
    print(f"Datenbank ist aktuell: {db_path}")
    return EXIT_OK


def _cmd_scan(args: argparse.Namespace) -> int:
    library = common.library_folder(args.folder)
    if library is None:
        return EXIT_ERROR
    with db.open_session(config.database_path()) as session:
        summary = scan_library(session, library)
        search.rebuild(session)
        session.commit()
    _print_summary(summary)
    return EXIT_OK


def _print_summary(summary: ScanSummary) -> None:
    print(
        f"neu: {summary.new}, aktualisiert: {summary.updated}, "
        f"unverändert: {summary.unchanged}, fehlend: {summary.missing}, "
        f"Duplikate: {len(summary.duplicates)}, Fehler: {len(summary.errors)}"
    )
    for duplicate, original in summary.duplicates:
        common.print_error(
            f"Duplikat übersprungen: {duplicate!r} (gleicher Inhalt: {original!r})"
        )
    for rel_path, message in summary.errors:
        common.print_error(f"Nicht lesbar: {rel_path!r}: {message}")


def _cmd_list(args: argparse.Namespace) -> int:
    query = (
        select(Recording)
        .join(AutoFile)
        .options(
            selectinload(Recording.file),
            selectinload(Recording.tags),
            selectinload(Recording.user_tags),
            selectinload(Recording.note),
        )
        .order_by(AutoFile.rel_path)
    )
    if args.missing:
        query = query.where(AutoFile.missing)
    with db.open_session(config.database_path()) as session:
        for recording in session.scalars(query):
            common.print_recording(recording)
    return EXIT_OK


def _cmd_embed(args: argparse.Namespace) -> int:
    embedder = common.embedder()
    if isinstance(embedder, str):
        common.print_error(embedder)
        return EXIT_ERROR
    embed, model_name = embedder
    with db.open_session(config.database_path()) as session:
        todo = embeddings.pending(session, model_name, args.redo)
        if not todo:
            print("Nichts zu tun: alle Vektoren sind aktuell.")
            return EXIT_OK
        try:
            embeddings.embed_recordings(
                session,
                embed,
                model_name,
                todo,
                report=lambda done: print(f"[{done}/{len(todo)}]", flush=True),
            )
        except embeddings.EmbeddingError as error:
            common.print_error(common.embedding_failed(error))
            return EXIT_ERROR
    print(f"Vektoren berechnet: {len(todo)} (Modell {model_name})")
    return EXIT_OK


def _no_meaning(args: argparse.Namespace, reason: str) -> int | None:
    """Report why the search by meaning is impossible; None means fall back."""
    if args.semantic:
        common.print_error(reason)
        return EXIT_ERROR
    common.print_error(f"Hinweis: {reason} Gesucht wird nur nach Stichwörtern.")
    return None


def _search_by_meaning(args: argparse.Namespace) -> int | None:
    """Search by keyword and meaning combined.

    Returns None if that is impossible and was not asked for with -s; the
    caller then searches by keyword only.
    """
    if not args.semantic and not config.embed_model():
        return None
    embedder = common.embedder()
    if isinstance(embedder, str):
        return _no_meaning(args, embedder)
    embed, model_name = embedder
    with db.open_session(config.database_path()) as session:
        outdated = len(embeddings.pending(session, model_name))
        try:
            found = embeddings.hybrid_search(
                session, embed, model_name, " ".join(args.words), args.limit
            )
        except embeddings.EmbeddingError as error:
            return _no_meaning(args, common.embedding_failed(error))
        hits = _print_found(found)
    if outdated:
        common.print_error(
            f"Hinweis: {outdated} Aufnahme(n) ohne aktuellen Vektor. "
            "'fretgrep embed' bringt sie auf den Stand."
        )
    return _after_search(args, hits)


def _print_found(found: list[Recording]) -> list[tuple[int, str]]:
    """Print the hits and return their IDs and paths within the library."""
    for recording in found:
        common.print_recording(recording)
    if not found:
        print("Keine Treffer.")
    return [(recording.id, recording.file.rel_path) for recording in found]


def _after_search(args: argparse.Namespace, hits: list[tuple[int, str]]) -> int:
    """Save the hits with --save and play them with --play."""
    if not hits:
        return EXIT_OK
    if args.save:
        ids = [recording_id for recording_id, _ in hits]
        cli_playlist.save_to_playlist(args.save, ids)
    if not args.play:
        return EXIT_OK
    return common.play_hits(hits, args)


def _cmd_search(args: argparse.Namespace) -> int:
    if args.speed <= 0:
        common.print_error(common.SPEED_ERROR)
        return EXIT_ERROR
    if not args.keyword:
        code = _search_by_meaning(args)
        if code is not None:
            return code
    words = " ".join(args.words)
    if search.build_query(words) is None:
        common.print_error("Die Suche enthält nur Füllwörter.")
        return EXIT_ERROR
    with db.open_session(config.database_path()) as session:
        hits = _print_found(search.search(session, words, args.limit))
    return _after_search(args, hits)


def _cmd_show(args: argparse.Namespace) -> int:
    with db.open_session(config.database_path()) as session:
        recording = session.get(Recording, args.id)
        if recording is None:
            return common.unknown_id(args.id)
        file = recording.file
        print(f"ID:            {recording.id}")
        print(f"Pfad:          {file.rel_path}{'  [fehlt]' if file.missing else ''}")
        print(f"Name:          {file.filename_norm}")
        print(f"Inhalts-Hash:  {recording.content_hash}")
        print(f"Größe:         {file.size_bytes} Bytes")
        print(f"Dauer:         {common.format_duration(file.duration_s).strip()}")
        print(
            f"Audio:         {file.sample_rate or '?'} Hz, "
            f"{file.channels or '?'} Kanal/Kanäle, "
            f"{file.bitrate or '?'} bit/s"
        )
        print(f"Eingelesen:    {file.scanned_at:%Y-%m-%d %H:%M} UTC")
        print(f"Eigene Tags:   {common.user_tags(recording) or '-'}")
        print(f"Notiz:         {recording.note.text if recording.note else '-'}")
        print(f"Nicht erkannt: {file.unparsed or '-'}")
        _print_transcript(recording)
        print("Tag-Vorschläge (automatisch, unbestätigt):")
        for tag in common.sorted_tags(recording.tags):
            print(
                f"  {tag.confidence:.1f}  {tag.category:<12} {tag.value:<32} "
                f"[{tag.source}: {tag.raw_token!r}]"
            )
    return EXIT_OK


def _print_transcript(recording: Recording) -> None:
    transcript = recording.transcript
    if transcript is None:
        print("Transkript:    (noch nicht erzeugt)")
    elif not transcript.text:
        print("Transkript:    (keine Sprache erkannt)")
    else:
        print(f"Transkript ({transcript.model}, {transcript.language}):")
        print(f"  {transcript.text}")


def _recording_file(recording_id: int, library: Path) -> Path | None:
    """Return the audio file of a recording, or None after printing why not."""
    with db.open_session(config.database_path()) as session:
        recording = session.get(Recording, recording_id)
        if recording is None:
            common.unknown_id(recording_id)
            return None
        path = library / recording.file.rel_path
    if not path.is_file():
        common.print_error(f"Datei nicht gefunden: {path}")
        return None
    return path


def _cmd_play(args: argparse.Namespace) -> int:
    if args.speed <= 0:
        common.print_error(common.SPEED_ERROR)
        return EXIT_ERROR
    try:
        loop = player.parse_loop(args.loop) if args.loop else None
    except ValueError:
        common.print_error("Der Loop braucht die Form A-B in Sekunden, z. B. 5-12.5.")
        return EXIT_ERROR
    if loop and len(args.ids) > 1:
        common.print_error("Ein Loop geht nur mit einer einzelnen Aufnahme.")
        return EXIT_ERROR
    library = common.library_folder(args.library)
    if library is None:
        return EXIT_ERROR
    hits = []
    for recording_id in args.ids:
        path = _recording_file(recording_id, library)
        if path is None:
            return EXIT_ERROR
        hits.append((recording_id, str(path.relative_to(library))))
        print(f"{recording_id}  {hits[-1][1]}")
    return common.play_hits(hits, args, loop)


def _detect_notes(recording_id: int, library_argument: str | None) -> bool:
    """Recognise and store the notes of a recording; False after an error."""
    library = common.library_folder(library_argument)
    path = _recording_file(recording_id, library) if library else None
    if path is None:
        return False
    try:
        detect, model_name = notes.load_detector()
    except notes.MissingDependencyError:
        common.print_error(
            "basic-pitch ist nicht installiert. Bitte ausführen:\n"
            "  pip install -e '.[notes]'\n"
            "  pip install --no-deps basic-pitch==0.4.0"
        )
        return False
    try:
        found = detect(path)
    except (OSError, subprocess.CalledProcessError) as error:
        common.print_error(f"Nicht lesbar: {path}: {error}")
        return False
    with db.open_session(config.database_path()) as session:
        notes.store(session.get(Recording, recording_id), found, model_name)
        session.commit()
    return True


def _cmd_notes(args: argparse.Namespace) -> int:
    if (args.rhythm or args.tempo) and not (args.sheet or args.show):
        common.print_error(
            "--rhythm und --tempo wirken nur zusammen mit --sheet oder --show."
        )
        return EXIT_ERROR
    if args.tempo is not None and not 20 <= args.tempo <= 400:
        common.print_error("Das Tempo muss zwischen 20 und 400 liegen.")
        return EXIT_ERROR
    with db.open_session(config.database_path()) as session:
        recording = session.get(Recording, args.id)
        if recording is None:
            return common.unknown_id(args.id)
        missing = recording.notes is None
    if (missing or args.redo) and not _detect_notes(args.id, args.library):
        return EXIT_ERROR
    with db.open_session(config.database_path()) as session:
        recording = session.get(Recording, args.id)
        found = notes.stored(recording)
        lines = notes.phrases(found, args.min_amplitude)
        shown = sum(len(chord) for phrase in lines for chord in phrase)
        title = recording.file.rel_path
        summary = (
            f"{recording.notes.model}: {shown} von {len(found)} Noten, "
            f"ab Lautstärke {args.min_amplitude:g}"
        )
    print(f"{args.id}  {title}")
    print(summary)
    width = shutil.get_terminal_size().columns
    for phrase in lines:
        print(notes.format_phrase(phrase, width))
    code = EXIT_OK
    if args.midi:
        code = _write_midi(found, args.min_amplitude, Path(args.midi))
    if args.sheet or args.show:
        rhythms = None
        if args.rhythm or args.tempo:
            rhythms = rhythm.estimate(lines, args.tempo)
        text = sheet.source(lines, title, summary, rhythms)
        if args.sheet:
            code = max(code, _write_sheet(text, args.sheet))
        if args.show:
            code = max(code, _show_sheet(text, args.id))
    return code


def _sheet_failed(error: Exception) -> int:
    """Report why no sheet could be drawn."""
    if isinstance(error, sheet.EngraverMissingError):
        common.print_error(
            "LilyPond ist nicht installiert. Bitte 'sudo apt install lilypond'."
        )
    else:
        common.print_error(f"Notenblatt nicht erzeugt: {error}")
    return EXIT_ERROR


def _show_sheet(text: str, recording_id: int) -> int:
    path = config.cache_path() / "sheets" / f"notes-{recording_id}{sheet.SHOW_SUFFIX}"
    try:
        sheet.show(text, path)
    except sheet.ViewerMissingError:
        common.print_error(
            "Kein Programm zum Öffnen gefunden (xdg-open). "
            "Bitte 'sudo apt install xdg-utils' oder --sheet DATEI benutzen."
        )
        return EXIT_ERROR
    except (sheet.EngraverMissingError, sheet.EngraverError, OSError) as error:
        return _sheet_failed(error)
    print(f"Notenblatt geöffnet: {path}")
    return EXIT_OK


def _write_sheet(text: str, target: str) -> int:
    path = Path(target)
    try:
        sheet.write(text, path)
    except ValueError:
        formats = ", ".join([*sheet.FORMATS, sheet.SOURCE_SUFFIX])
        common.print_error(
            f"Unbekanntes Format für das Notenblatt. Möglich sind: {formats}"
        )
        return EXIT_ERROR
    except (sheet.EngraverMissingError, sheet.EngraverError, OSError) as error:
        return _sheet_failed(error)
    print(f"Notenblatt gespeichert: {path}")
    return EXIT_OK


def _write_midi(found: list[notes.Note], min_amplitude: float, path: Path) -> int:
    try:
        count = notes.write_midi(found, min_amplitude, path)
    except notes.MissingDependencyError:
        common.print_error(
            "pretty_midi ist nicht installiert: pip install -e '.[notes]'"
        )
        return EXIT_ERROR
    except OSError as error:
        common.print_error(f"MIDI-Datei nicht schreibbar: {error}")
        return EXIT_ERROR
    print(f"MIDI gespeichert: {path} ({count} Noten)")
    return EXIT_OK


def _cmd_tag(args: argparse.Namespace) -> int:
    with db.open_session(config.database_path()) as session:
        recording = session.get(Recording, args.id)
        if recording is None:
            return common.unknown_id(args.id)
        user_meta.add_tags(recording, args.tags)
        search.refresh(session, recording)
        session.commit()
        print(f"Eigene Tags: {common.user_tags(recording) or '-'}")
    return EXIT_OK


def _cmd_untag(args: argparse.Namespace) -> int:
    with db.open_session(config.database_path()) as session:
        recording = session.get(Recording, args.id)
        if recording is None:
            return common.unknown_id(args.id)
        removed = user_meta.remove_tags(recording, args.tags)
        if not removed:
            common.print_error("Keiner dieser Tags war vergeben.")
            return EXIT_ERROR
        search.refresh(session, recording)
        session.commit()
        print(f"Eigene Tags: {common.user_tags(recording) or '-'}")
    return EXIT_OK


def _cmd_note(args: argparse.Namespace) -> int:
    if args.clear and args.text:
        common.print_error("Entweder Text angeben oder --clear, nicht beides.")
        return EXIT_ERROR
    with db.open_session(config.database_path()) as session:
        recording = session.get(Recording, args.id)
        if recording is None:
            return common.unknown_id(args.id)
        if args.text or args.clear:
            user_meta.set_note(recording, " ".join(args.text))
            search.refresh(session, recording)
            session.commit()
        print(f"Notiz: {recording.note.text if recording.note else '-'}")
    return EXIT_OK


def _cmd_transcribe(args: argparse.Namespace) -> int:
    library = common.library_folder(args.library)
    if library is None:
        return EXIT_ERROR
    model_name = config.whisper_model()
    with db.open_session(config.database_path()) as session:
        todo = transcribe.pending(session, model_name, args.ids, args.redo)
        todo = todo if args.limit is None else todo[: args.limit]
        if not todo:
            print("Nichts zu tun: alle Aufnahmen haben ein Transkript.")
            return EXIT_OK
        try:
            model = transcribe.load_model(model_name)
        except transcribe.MissingDependencyError:
            common.print_error(
                "faster-whisper ist nicht installiert. "
                "Bitte 'pip install -e .[transcribe]' ausführen."
            )
            return EXIT_ERROR
        progress = iter(range(1, len(todo) + 1))

        def report(recording: Recording, error: str | None) -> None:
            prefix = f"[{next(progress)}/{len(todo)}] {recording.file.rel_path}"
            if error is None:
                words = len(recording.transcript.text.split())
                print(f"{prefix}: {words} Wörter", flush=True)
            else:
                common.print_error(f"{prefix}: Fehler: {error}")

        done = transcribe.transcribe_recordings(
            session,
            library,
            model,
            model_name,
            todo,
            language=config.whisper_language(),
            report=report,
        )
    print(f"Transkribiert: {done} von {len(todo)} (Modell {model_name})")
    return EXIT_OK if done == len(todo) else EXIT_ERROR


def _cmd_tones(args: argparse.Namespace) -> int:
    try:
        print(theory.parse(" ".join(args.symbol)).describe())
    except theory.SymbolError as error:
        common.print_error(str(error))
        return EXIT_ERROR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
