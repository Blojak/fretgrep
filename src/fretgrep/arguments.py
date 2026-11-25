"""The commands and switches of ``fretgrep``, with their help texts.

The functions that carry out the commands live in ``cli``; they are
passed in by name, so that this module only describes the interface.
"""

import argparse
from collections.abc import Callable, Mapping

from fretgrep import banner, completion, config, notes

Handlers = Mapping[str, Callable[[argparse.Namespace], int]]

DEFAULT_SEARCH_LIMIT = 20
# The logo appears only where nobody processes the output any further.
_WORKFLOW = """\
Üblicher Ablauf:
  fretgrep db upgrade       Datenbank anlegen oder aktualisieren
  fretgrep scan ORDNER      Aufnahmen einlesen
  fretgrep transcribe       optional: Gesprochenes mitschreiben
  fretgrep embed            optional: Vektoren für die Suche nach Bedeutung
  fretgrep search WÖRTER    suchen; die Zahl am Zeilenanfang ist die ID
  fretgrep play ID          abspielen
  fretgrep playlist         eigene Wiedergabelisten anlegen und abspielen
  fretgrep notes ID         gespielte Noten anzeigen
  fretgrep tones SYMBOL     Töne eines Akkords oder einer Skala, z. B. G7HM5
  fretgrep chat FRAGE       den Assistenten fragen

Tab-Vervollständigung einrichten: fretgrep completion --help

Einstellungen (Umgebungsvariablen):
  {db:<26}Datenbankdatei (Standard: {default_db})
  {library:<26}Ordner mit den Aufnahmen
  {ollama:<26}Adresse des Ollama-Servers (Standard: {default_ollama})
  {embed:<26}Embedding-Modell, z. B. bge-m3:latest; schaltet die
  {empty:<26}Suche nach Bedeutung ein
  {chat:<26}Sprachmodell für chat (Standard: {default_chat})
  {whisper:<26}Whisper-Modell (Standard: {default_whisper})
  {language:<26}Sprache der Erklärungen, z. B. de

Hilfe zu einem Befehl:  fretgrep BEFEHL --help
Ausführliche Anleitung: docs/benutzung.md
"""

_HELP = "diese Hilfe anzeigen"
LOGO_ARGUMENTS = ("-h", "--help", "--version")
_LIBRARY_HELP = f"Ordner mit den Aufnahmen (Standard: ${config.ENV_LIBRARY})"
_SPEED_HELP = "Tempo als Faktor, z. B. 0.7; die Tonhöhe bleibt gleich"
_PITCH_HELP = "Tonhöhe in Halbtönen, z. B. -2 oder 0.5"


def _add_help(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-h", "--help", action="help", help=_HELP)


def _command(commands, name: str, summary: str, details: str = "", examples=()):
    """Add a command; its own help shows the summary, details and examples."""
    description = summary[0].upper() + summary[1:] + "."
    if details:
        description += "\n\n" + details
    epilog = None
    if examples:
        epilog = "Beispiele:\n" + "\n".join(f"  {line}" for line in examples)
    parser = commands.add_parser(
        name,
        help=summary,
        description=description,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    _add_help(parser)
    return parser


def build(handlers: Handlers) -> argparse.ArgumentParser:
    """Return the parser; ``handlers`` maps each command to its function."""
    parser = argparse.ArgumentParser(
        prog="fretgrep",
        description="Gitarren-Lick-Aufnahmen einlesen, durchsuchen, abspielen "
        "und als Noten anzeigen.",
        epilog=_WORKFLOW.format(
            db=config.ENV_DB,
            library=config.ENV_LIBRARY,
            ollama=config.ENV_OLLAMA_URL,
            embed=config.ENV_EMBED_MODEL,
            chat=config.ENV_CHAT_MODEL,
            default_chat=config.DEFAULT_CHAT_MODEL,
            whisper=config.ENV_WHISPER_MODEL,
            language=config.ENV_WHISPER_LANGUAGE,
            empty="",
            default_ollama=config.DEFAULT_OLLAMA_URLS[0],
            default_db=config.DEFAULT_DB_PATH,
            default_whisper=config.DEFAULT_WHISPER_MODEL,
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    _add_help(parser)
    parser.add_argument(
        "--version",
        action="version",
        version=banner.version(),
        help="Version anzeigen",
    )
    commands = parser.add_subparsers(
        dest="command", required=True, title="Befehle", metavar="BEFEHL"
    )
    _add_library_commands(commands, handlers)
    _add_search_commands(commands, handlers)
    _add_derived_data_commands(commands, handlers)
    _add_audio_commands(commands, handlers)
    _add_playlist_commands(commands, handlers)
    _add_chat_command(commands, handlers)
    _add_shell_commands(commands, handlers)
    return parser


def _add_library_commands(commands, handlers: Handlers) -> None:
    """Add the commands that set up and list the library."""
    db_parser = _command(commands, "db", "Datenbank verwalten")
    db_commands = db_parser.add_subparsers(
        dest="db_command", required=True, title="Befehle", metavar="BEFEHL"
    )
    upgrade = _command(
        db_commands,
        "upgrade",
        "Datenbank anlegen bzw. auf den neuesten Stand bringen",
        "Nötig beim ersten Start und nach jeder neuen Version von fretgrep.\n"
        "Eigene Tags und Notizen bleiben erhalten.",
    )
    upgrade.set_defaults(handler=handlers["db_upgrade"])

    scan = _command(
        commands,
        "scan",
        "Ordner mit Aufnahmen einlesen",
        "Sucht im Ordner und allen Unterordnern nach MP3-Dateien und schlägt\n"
        "aus den Dateinamen Tags vor. Kann beliebig oft laufen: Umbenannte\n"
        "und verschobene Dateien behalten Tags, Notizen und Transkript.",
        ["fretgrep scan lick-library", "fretgrep scan"],
    )
    scan.add_argument("folder", nargs="?", metavar="ORDNER", help=_LIBRARY_HELP)
    scan.set_defaults(handler=handlers["scan"])

    list_parser = _command(commands, "list", "Aufnahmen auflisten")
    list_parser.add_argument(
        "--missing", action="store_true", help="nur fehlende Dateien zeigen"
    )
    list_parser.set_defaults(handler=handlers["list"])

    show = _command(
        commands,
        "show",
        "Details einer Aufnahme zeigen",
        "Zeigt Pfad, Audiodaten, eigene Tags, Notiz, Transkript und alle\n"
        "Tag-Vorschläge mit Konfidenz und Herkunft.",
    )
    show.add_argument("id", type=int, metavar="ID", help="ID der Aufnahme")
    show.set_defaults(handler=handlers["show"])


def _add_search_commands(commands, handlers: Handlers) -> None:
    """Add the search and the commands for the user's own tags and notes."""
    find = _command(
        commands,
        "search",
        "Aufnahmen suchen",
        "Sucht nach Stichwörtern und nach Bedeutung zugleich und liefert\n"
        "eine Rangliste; das eignet sich auch für ganze Sätze. Die Bedeutung\n"
        f"braucht ${config.ENV_EMBED_MODEL}, den Ollama-Server und einen Lauf\n"
        "von 'embed'. Fehlt etwas davon, wird nur nach Stichwörtern gesucht.\n"
        "Bei der Stichwortsuche (immer mit -k) müssen alle Wörter vorkommen:\n"
        "in Name, Ordner, Tags, Notiz oder Transkript. Wortanfänge reichen,\n"
        "und bekannte Schreibweisen werden übersetzt (moll findet auch minor).\n"
        "Mit --play laufen die Treffer danach als Wiedergabeliste, der beste\n"
        "zuerst; die Tasten stehen bei 'fretgrep play --help'. --save legt\n"
        "die Treffer in eine eigene Wiedergabeliste (siehe 'playlist').",
        [
            "fretgrep search etwas von meinem Lehrer",
            "fretgrep search -n 5 blues",
            "fretgrep search -k chet baker moll",
            "fretgrep search -n 5 blues --play",
            "fretgrep search -k chet baker --play --speed 0.7",
            'fretgrep search -n 5 hm5 --save "hm5 üben"',
        ],
    )
    find.add_argument("words", nargs="+", metavar="WORT", help="Suchwörter")
    find.add_argument(
        "-n",
        "--limit",
        type=int,
        default=DEFAULT_SEARCH_LIMIT,
        metavar="ANZAHL",
        help=f"maximale Trefferzahl (Standard: {DEFAULT_SEARCH_LIMIT})",
    )
    mode = find.add_mutually_exclusive_group()
    mode.add_argument(
        "-k",
        "--keyword",
        action="store_true",
        help="nur nach Stichwörtern suchen; alle Wörter müssen vorkommen",
    )
    mode.add_argument(
        "-s",
        "--semantic",
        action="store_true",
        help="Bedeutung verlangen: Fehler statt Stichwortsuche, wenn sie fehlt",
    )
    find.add_argument(
        "--play", action="store_true", help="die Treffer nacheinander abspielen"
    )
    find.add_argument(
        "--speed", type=float, default=1.0, metavar="FAKTOR", help=_SPEED_HELP
    )
    find.add_argument(
        "--pitch", type=float, default=0.0, metavar="HALBTÖNE", help=_PITCH_HELP
    )
    find.add_argument(
        "--save",
        metavar="LISTE",
        help="die Treffer an diese Wiedergabeliste anhängen; legt sie bei Bedarf an",
    )
    find.add_argument("--library", metavar="ORDNER", help=_LIBRARY_HELP)
    find.set_defaults(handler=handlers["search"])

    tag = _command(
        commands,
        "tag",
        "eigene Tags vergeben",
        "Eigene Tags werden nie automatisch geändert oder überschrieben.",
        ["fretgrep tag 21 Favorit üben"],
    )
    tag.add_argument("id", type=int, metavar="ID", help="ID der Aufnahme")
    tag.add_argument("tags", nargs="+", metavar="TAG", help="Tags")
    tag.set_defaults(handler=handlers["tag"])

    untag = _command(
        commands, "untag", "eigene Tags entfernen", examples=["fretgrep untag 21 üben"]
    )
    untag.add_argument("id", type=int, metavar="ID", help="ID der Aufnahme")
    untag.add_argument("tags", nargs="+", metavar="TAG", help="Tags")
    untag.set_defaults(handler=handlers["untag"])

    note = _command(
        commands,
        "note",
        "Notiz anzeigen, setzen oder löschen",
        "Ohne Text wird die Notiz angezeigt, mit Text wird sie ersetzt.",
        [
            "fretgrep note 21",
            "fretgrep note 21 langsam anfangen, Fingersatz prüfen",
            "fretgrep note 21 --clear",
        ],
    )
    note.add_argument("id", type=int, metavar="ID", help="ID der Aufnahme")
    note.add_argument("text", nargs="*", metavar="TEXT", help="neuer Notiztext")
    note.add_argument("--clear", action="store_true", help="Notiz löschen")
    note.set_defaults(handler=handlers["note"])


def _add_derived_data_commands(commands, handlers: Handlers) -> None:
    """Add the commands that compute transcripts and embedding vectors."""
    speech = _command(
        commands,
        "transcribe",
        "gesprochene Erklärungen in Text umwandeln",
        "Braucht faster-whisper und ffmpeg. Läuft auf der CPU und dauert;\n"
        "ein abgebrochener Lauf macht beim nächsten Start dort weiter.\n"
        "Bearbeitet nur Aufnahmen, die noch kein Transkript haben.",
        [
            "fretgrep transcribe",
            "fretgrep transcribe --limit 5",
            "fretgrep transcribe 21 22",
        ],
    )
    speech.add_argument(
        "ids", nargs="*", type=int, metavar="ID", help="nur diese Aufnahmen"
    )
    speech.add_argument("--library", metavar="ORDNER", help=_LIBRARY_HELP)
    speech.add_argument(
        "--limit", type=int, metavar="ANZAHL", help="höchstens so viele Aufnahmen"
    )
    speech.add_argument(
        "--redo", action="store_true", help="vorhandene Transkripte neu erzeugen"
    )
    speech.set_defaults(handler=handlers["transcribe"])

    embed = _command(
        commands,
        "embed",
        "Vektoren für die Suche nach Bedeutung berechnen",
        f"Braucht ${config.ENV_EMBED_MODEL} und einen Ollama-Server.\n"
        "Berechnet nur, was fehlt oder veraltet ist. Erneut ausführen nach\n"
        "neuen Aufnahmen, Tags, Notizen, Transkripten oder Änderungen am\n"
        "Vokabular.",
    )
    embed.add_argument(
        "--redo", action="store_true", help="vorhandene Vektoren neu berechnen"
    )
    embed.set_defaults(handler=handlers["embed"])


def _add_audio_commands(commands, handlers: Handlers) -> None:
    """Add the commands that work on the audio itself."""
    play = _command(
        commands,
        "play",
        "Aufnahmen mit mpv abspielen",
        "Mehrere IDs laufen nacheinander als Wiedergabeliste. Tempo und\n"
        "Tonhöhe lassen sich unabhängig voneinander ändern.\n"
        "Tasten während der Wiedergabe: Leertaste Pause, Pfeile springen,\n"
        "[ und ] Tempo, l A-B-Loop setzen, L ganze Datei wiederholen,\n"
        "< und > voriges und nächstes Stück, F8 Wiedergabeliste zeigen,\n"
        "q beenden.\n"
        "Die Treffer einer Suche spielt 'fretgrep search ... --play' ab.",
        [
            "fretgrep play 21",
            "fretgrep play 21 34 95",
            "fretgrep play 21 -s 0.7",
            "fretgrep play 21 -p -2",
            "fretgrep play 21 -s 0.5 -l 5-12.5",
        ],
    )
    play.add_argument(
        "ids", nargs="+", type=int, metavar="ID", help="IDs der Aufnahmen"
    )
    play.add_argument(
        "-s",
        "--speed",
        type=float,
        default=1.0,
        metavar="FAKTOR",
        help=_SPEED_HELP,
    )
    play.add_argument(
        "-p",
        "--pitch",
        type=float,
        default=0.0,
        metavar="HALBTÖNE",
        help=_PITCH_HELP,
    )
    play.add_argument(
        "-l",
        "--loop",
        metavar="A-B",
        help="Ausschnitt in Sekunden wiederholen; nur mit einer einzelnen ID",
    )
    play.add_argument("--library", metavar="ORDNER", help=_LIBRARY_HELP)
    play.set_defaults(handler=handlers["play"])

    note_parser = _command(
        commands,
        "notes",
        "gespielte Noten erkennen und anzeigen",
        "Der erste Aufruf je Aufnahme erkennt die Noten mit basic-pitch und\n"
        "speichert sie; danach kommen sie aus der Datenbank. Jede Zeile der\n"
        "Ausgabe ist eine Phrase mit ihrer Startzeit in Sekunden, Töne in\n"
        "eckigen Klammern beginnen gleichzeitig.\n"
        "--show öffnet das Notenblatt in einem Fenster, --sheet speichert es.\n"
        "Das Notenblatt braucht LilyPond. Notenwerte (--rhythm) sind eine\n"
        "Schätzung ohne Takte; wirkt das Blatt zu schnell oder zu langsam\n"
        "notiert, hilft --tempo.",
        [
            "fretgrep notes 83",
            "fretgrep notes 83 -m 0.6",
            "fretgrep notes 83 --midi wes.mid",
            "fretgrep notes 83 --show",
            "fretgrep notes 83 --show --rhythm",
            "fretgrep notes 83 --sheet wes.pdf",
            "fretgrep notes 83 --sheet wes.pdf --rhythm",
            "fretgrep notes 83 --sheet wes.pdf --tempo 110",
        ],
    )
    note_parser.add_argument("id", type=int, metavar="ID", help="ID der Aufnahme")
    note_parser.add_argument(
        "-m",
        "--min-amplitude",
        type=float,
        default=notes.DEFAULT_MIN_AMPLITUDE,
        metavar="SCHWELLE",
        help="leisere Noten ausblenden, 0 bis 1 "
        f"(Standard: {notes.DEFAULT_MIN_AMPLITUDE})",
    )
    note_parser.add_argument("--redo", action="store_true", help="Noten neu erkennen")
    note_parser.add_argument(
        "--midi", metavar="DATEI", help="die gezeigten Noten als MIDI-Datei speichern"
    )
    note_parser.add_argument(
        "--sheet",
        metavar="DATEI",
        help="die gezeigten Noten als Notenblatt speichern (.pdf, .svg, .png, .ly)",
    )
    note_parser.add_argument(
        "-w",
        "--show",
        action="store_true",
        help="das Notenblatt in einem Fenster zeigen, ohne es zu speichern",
    )
    note_parser.add_argument(
        "--rhythm",
        action="store_true",
        help="im Notenblatt Notenwerte schätzen (Achtel, Viertel, Pausen)",
    )
    note_parser.add_argument(
        "--tempo",
        type=float,
        metavar="BPM",
        help="Tempo in Vierteln pro Minute vorgeben statt schätzen; "
        "schaltet --rhythm ein",
    )
    note_parser.add_argument("--library", metavar="ORDNER", help=_LIBRARY_HELP)
    note_parser.set_defaults(handler=handlers["notes"])


def _add_speed_pitch(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-s", "--speed", type=float, default=1.0, metavar="FAKTOR", help=_SPEED_HELP
    )
    parser.add_argument(
        "-p", "--pitch", type=float, default=0.0, metavar="HALBTÖNE", help=_PITCH_HELP
    )
    parser.add_argument("--library", metavar="ORDNER", help=_LIBRARY_HELP)


def _add_playlist_commands(commands, handlers: Handlers) -> None:
    """Add the commands for the user's own playlists."""
    playlist = _command(
        commands,
        "playlist",
        "eigene Wiedergabelisten anlegen, pflegen und abspielen",
        "Ohne Befehl werden alle Listen gezeigt. Eine Aufnahme steht in einer\n"
        "Liste höchstens einmal, kann aber in beliebig vielen Listen stehen.\n"
        "Listen folgen den Aufnahmen auch nach Umbenennen oder Verschieben.\n"
        "Groß- und Kleinschreibung im Namen spielt keine Rolle; Namen mit\n"
        "Leerzeichen in Anführungszeichen setzen. Die Tasten beim Abspielen\n"
        "stehen bei 'fretgrep play --help'.",
        [
            "fretgrep playlist",
            'fretgrep playlist new "hm5 üben"',
            'fretgrep playlist add "hm5 üben" 46 63 81',
            'fretgrep search -n 5 hm5 --save "hm5 üben"',
            'fretgrep playlist show "hm5 üben"',
            'fretgrep playlist show "hm5 üben" --play -s 0.7',
            'fretgrep playlist play "hm5 üben" -s 0.7 -p -2',
            'fretgrep playlist remove "hm5 üben" 63',
            'fretgrep playlist export "hm5 üben" -o hm5.m3u',
            'fretgrep playlist delete "hm5 üben"',
        ],
    )
    # Only for the tab completion: the names, one per line.
    playlist.add_argument("--names", action="store_true", help=argparse.SUPPRESS)
    playlist.set_defaults(handler=handlers["playlist_list"])
    playlist_commands = playlist.add_subparsers(
        dest="playlist_command", title="Befehle", metavar="BEFEHL"
    )

    def name_argument(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("name", metavar="LISTE", help="Name der Liste")

    new = _command(playlist_commands, "new", "leere Liste anlegen")
    # Not LISTE: the tab completion would offer the names already taken.
    new.add_argument("name", metavar="NAME", help="Name der neuen Liste")
    new.set_defaults(handler=handlers["playlist_new"])

    add = _command(
        playlist_commands,
        "add",
        "Aufnahmen hinten anhängen",
        "Legt die Liste an, wenn es sie noch nicht gibt. Aufnahmen, die schon\n"
        "in der Liste stehen, werden übersprungen.",
    )
    name_argument(add)
    add.add_argument("ids", nargs="+", type=int, metavar="ID", help="IDs der Aufnahmen")
    add.set_defaults(handler=handlers["playlist_add"])

    remove = _command(playlist_commands, "remove", "Aufnahmen aus der Liste nehmen")
    name_argument(remove)
    remove.add_argument(
        "ids", nargs="+", type=int, metavar="ID", help="IDs der Aufnahmen"
    )
    remove.set_defaults(handler=handlers["playlist_remove"])

    show = _command(
        playlist_commands,
        "show",
        "Liste zeigen, mit --play danach abspielen",
        "Fehlende Dateien werden beim Abspielen mit Hinweis übersprungen.",
    )
    name_argument(show)
    show.add_argument(
        "--play", action="store_true", help="die Liste danach mit mpv abspielen"
    )
    _add_speed_pitch(show)
    show.set_defaults(handler=handlers["playlist_show"])

    play = _command(
        playlist_commands,
        "play",
        "Liste mit mpv abspielen",
        "Fehlende Dateien werden mit Hinweis übersprungen.",
    )
    name_argument(play)
    _add_speed_pitch(play)
    play.set_defaults(handler=handlers["playlist_play"])

    export = _command(
        playlist_commands,
        "export",
        "Liste als .m3u für andere Player ausgeben",
        "Die Datei enthält absolute Pfade. Ohne -o geht sie auf die\n"
        "Standardausgabe. Fehlende Dateien werden mit Hinweis weggelassen.",
    )
    name_argument(export)
    export.add_argument(
        "-o", "--output", metavar="DATEI", help="in diese Datei schreiben"
    )
    export.add_argument("--library", metavar="ORDNER", help=_LIBRARY_HELP)
    export.set_defaults(handler=handlers["playlist_export"])

    delete = _command(
        playlist_commands,
        "delete",
        "Liste löschen",
        "Die Aufnahmen selbst bleiben erhalten.",
    )
    name_argument(delete)
    delete.set_defaults(handler=handlers["playlist_delete"])


def _add_chat_command(commands, handlers: Handlers) -> None:
    """Add the assistant."""
    chat = _command(
        commands,
        "chat",
        "den Assistenten fragen: Harmonielehre, Skalen, eigene Aufnahmen",
        "Ein Sprachmodell auf dem Ollama-Server beantwortet Fragen. Die Töne\n"
        "von Akkorden und Skalen rechnet fretgrep selbst aus und gibt sie dem\n"
        "Modell; so stimmen sie auch, wenn das Modell sich verrechnen würde.\n"
        "Auf Wunsch sucht das Modell in deiner Sammlung und nennt die IDs.\n"
        "Mit Frage gibt es eine Antwort. Ohne Frage beginnt ein Gespräch, in\n"
        "dem Rückfragen möglich sind; Strg+D oder 'exit' beendet es, Strg+C\n"
        "bricht eine laufende Antwort ab. Im Gespräch führt '!' am\n"
        "Zeilenanfang einen fretgrep-Befehl aus, z. B. '!play 46'.\n"
        "Das letzte Gespräch wird gespeichert; -c setzt es fort, auch nach\n"
        "einer einzelnen Frage.\n"
        "Nur die Töne, sofort und ohne Modell: 'fretgrep tones SYMBOL'.\n"
        "Notennamen sind englisch: B ist das deutsche H, Bb das deutsche B.\n"
        f"Das Modell legt ${config.ENV_CHAT_MODEL} fest.",
        [
            "fretgrep chat was sind die Töne von G7HM5",
            "fretgrep chat welche Skala passt über Dm7b5",
            "fretgrep chat hab ich Aufnahmen mit alterierten Licks",
            "fretgrep chat -c ja, such mir passende Aufnahmen",
            "fretgrep chat",
            "fretgrep chat -c",
            "fretgrep chat --think warum klingt HM5 über V7 in Moll so gut",
        ],
    )
    chat.add_argument("words", nargs="*", metavar="WORT", help="die Frage")
    chat.add_argument(
        "-c",
        "--continue",
        dest="resume",
        action="store_true",
        help="das letzte Gespräch fortsetzen",
    )
    chat.add_argument(
        "--think",
        action="store_true",
        help="das Modell erst nachdenken lassen: gründlicher, aber deutlich langsamer",
    )
    chat.add_argument(
        "--model",
        metavar="NAME",
        help=f"anderes Sprachmodell (Standard: ${config.ENV_CHAT_MODEL} "
        f"oder {config.DEFAULT_CHAT_MODEL})",
    )
    chat.set_defaults(handler=handlers["chat"])

    tones = _command(
        commands,
        "tones",
        "Töne eines Akkords und/oder einer Skala zeigen",
        "Rechnet sofort und ohne Sprachmodell. Bekannt sind Akkorde mit\n"
        "Erweiterungen und Alterationen, die Kirchentonarten, HM1 bis HM7,\n"
        "MM1 bis MM7, Pentatonik, Dur- und Moll-Blues, Ganzton, HTGT, GTHT\n"
        "und Bebop.\n"
        "HM5 ist die Skala auf dem genannten Grundton (G HM5 = 5. Modus von\n"
        "C harmonisch Moll). Notennamen sind englisch: B ist das deutsche H,\n"
        "Bb das deutsche B; H wird als Eingabe verstanden.",
        [
            "fretgrep tones G7HM5",
            "fretgrep tones Dm7b5",
            "fretgrep tones C lydisch",
            "fretgrep tones F# alteriert",
            "fretgrep tones Cmaj7 lydisch",
        ],
    )
    tones.add_argument(
        "symbol", nargs="+", metavar="SYMBOL", help="Grundton mit Akkord und/oder Skala"
    )
    tones.set_defaults(handler=handlers["tones"])


def _add_shell_commands(commands, handlers: Handlers) -> None:
    """Add the command that sets up the shell."""
    complete = _command(
        commands,
        "completion",
        "Befehle und Schalter mit der Tab-Taste vervollständigen",
        "Gibt ein Skript für die Shell aus. Einmal einrichten, danach wird\n"
        "z. B. 'fretgrep se' mit Tab zu 'fretgrep search'. Zweimal Tab zeigt\n"
        "die Möglichkeiten mit Erklärung.\n\n"
        "zsh, in der ~/.zshrc nach 'compinit':\n"
        "  eval \"$(fretgrep completion zsh)\"\n"
        "bash, in der ~/.bashrc:\n"
        "  eval \"$(fretgrep completion bash)\"\n"
        "Danach eine neue Shell öffnen.",
        ["fretgrep completion zsh", "fretgrep completion bash"],
    )
    complete.add_argument(
        "shell", choices=completion.SHELLS, metavar="SHELL", help="zsh oder bash"
    )
    complete.set_defaults(handler=handlers["completion"])
