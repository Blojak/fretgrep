"""The ``fretgrep playlist`` commands: own playlists of recordings."""

import argparse
import sys
from pathlib import Path

from fretgrep import cli_common as common
from fretgrep import config, db, player, user_meta
from fretgrep.cli_common import EXIT_ERROR, EXIT_OK
from fretgrep.filename_parser import normalize_name
from fretgrep.models import Recording


def _unknown_playlist(name: str) -> int:
    common.print_error(
        f"Keine Wiedergabeliste namens {name!r}. 'fretgrep playlist' zeigt alle."
    )
    return EXIT_ERROR


def save_to_playlist(name: str, ids: list[int]) -> None:
    """Append recordings to a playlist, creating it if needed."""
    with db.open_session(config.database_path()) as session:
        playlist = user_meta.find_playlist(session, name)
        if playlist is None:
            playlist = user_meta.create_playlist(session, name)
            print(f"Neue Wiedergabeliste {playlist.name!r} angelegt.")
        recordings = [session.get(Recording, recording_id) for recording_id in ids]
        added = user_meta.add_to_playlist(playlist, recordings)
        session.commit()
        skipped = len(recordings) - len(added)
        message = f"{playlist.name}: {len(added)} hinzugefügt"
        if skipped:
            message += f", {skipped} stand(en) schon darin"
        print(f"{message}; jetzt {common.count(len(playlist.entries))}.")


def cmd_list(args: argparse.Namespace) -> int:
    """List the playlists, or only their names with --names."""
    with db.open_session(config.database_path()) as session:
        found = user_meta.playlists(session)
        for playlist in found:
            if args.names:
                print(playlist.name)
            else:
                print(f"{playlist.name}  ({common.count(len(playlist.entries))})")
    if not found and not args.names:
        print("Noch keine Wiedergabelisten. Anlegen mit 'fretgrep playlist new NAME'.")
    return EXIT_OK


def cmd_new(args: argparse.Namespace) -> int:
    """Create an empty playlist."""
    if not normalize_name(args.name):
        common.print_error("Der Name der Liste ist leer.")
        return EXIT_ERROR
    with db.open_session(config.database_path()) as session:
        existing = user_meta.find_playlist(session, args.name)
        if existing is not None:
            common.print_error(f"Die Wiedergabeliste {existing.name!r} gibt es schon.")
            return EXIT_ERROR
        playlist = user_meta.create_playlist(session, args.name)
        session.commit()
        print(f"Wiedergabeliste {playlist.name!r} angelegt.")
    return EXIT_OK


def cmd_add(args: argparse.Namespace) -> int:
    """Append recordings to a playlist, creating it if needed."""
    if not normalize_name(args.name):
        common.print_error("Der Name der Liste ist leer.")
        return EXIT_ERROR
    with db.open_session(config.database_path()) as session:
        for recording_id in args.ids:
            if session.get(Recording, recording_id) is None:
                return common.unknown_id(recording_id)
    save_to_playlist(args.name, args.ids)
    return EXIT_OK


def cmd_remove(args: argparse.Namespace) -> int:
    """Take recordings out of a playlist."""
    with db.open_session(config.database_path()) as session:
        playlist = user_meta.find_playlist(session, args.name)
        if playlist is None:
            return _unknown_playlist(args.name)
        removed = user_meta.remove_from_playlist(playlist, args.ids)
        if not removed:
            common.print_error("Keine dieser Aufnahmen steht in der Liste.")
            return EXIT_ERROR
        session.commit()
        print(f"{playlist.name}: {len(removed)} entfernt; "
              f"jetzt {common.count(len(playlist.entries))}.")
    return EXIT_OK


def cmd_delete(args: argparse.Namespace) -> int:
    """Delete a playlist; its recordings stay."""
    with db.open_session(config.database_path()) as session:
        playlist = user_meta.find_playlist(session, args.name)
        if playlist is None:
            return _unknown_playlist(args.name)
        name = playlist.name
        session.delete(playlist)
        session.commit()
    print(f"Wiedergabeliste {name!r} gelöscht; die Aufnahmen bleiben erhalten.")
    return EXIT_OK


def _playlist_paths(name: str, show: bool) -> list[tuple[int, str]] | None:
    """Return the IDs and paths of a playlist in order; print its entries."""
    with db.open_session(config.database_path()) as session:
        playlist = user_meta.find_playlist(session, name)
        if playlist is None:
            _unknown_playlist(name)
            return None
        recordings = [entry.recording for entry in playlist.entries]
        print(f"{playlist.name}  ({common.count(len(recordings))})")
        for recording in recordings:
            if show:
                common.print_recording(recording)
            else:
                print(f"{recording.id:>5}  {recording.file.rel_path}")
        if not recordings:
            print("Die Liste ist leer.")
        return [(recording.id, recording.file.rel_path) for recording in recordings]


def cmd_play(args: argparse.Namespace) -> int:
    """Play a playlist; 'show' prints it first and plays only with --play."""
    show = args.playlist_command == "show"
    if args.speed <= 0:
        common.print_error(common.SPEED_ERROR)
        return EXIT_ERROR
    hits = _playlist_paths(args.name, show)
    if hits is None:
        return EXIT_ERROR
    if not hits or (show and not args.play):
        return EXIT_OK
    return common.play_hits(hits, args)


def cmd_export(args: argparse.Namespace) -> int:
    """Write a playlist as M3U for other players."""
    library = common.library_folder(args.library)
    if library is None:
        return EXIT_ERROR
    with db.open_session(config.database_path()) as session:
        playlist = user_meta.find_playlist(session, args.name)
        if playlist is None:
            return _unknown_playlist(args.name)
        files = [
            (library / entry.recording.file.rel_path, entry.recording.file.duration_s)
            for entry in playlist.entries
        ]
    present = [(path, duration) for path, duration in files if path.is_file()]
    if len(present) < len(files):
        common.print_error(
            f"Hinweis: {len(files) - len(present)} Datei(en) nicht gefunden "
            "und weggelassen."
        )
    text = player.m3u([(path, duration, path.stem) for path, duration in present])
    if not args.output:
        sys.stdout.write(text)
        return EXIT_OK
    try:
        Path(args.output).write_text(text, encoding="utf-8")
    except OSError as error:
        common.print_error(f"Datei nicht schreibbar: {error}")
        return EXIT_ERROR
    print(f"Gespeichert: {args.output} ({common.count(len(present))})")
    return EXIT_OK
