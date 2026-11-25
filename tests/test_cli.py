"""Tests for the fretgrep command line."""
# pylint: disable=missing-function-docstring,redefined-outer-name

from pathlib import Path

import pytest

from fretgrep import (
    assistant,
    banner,
    cli,
    config,
    embeddings,
    notes,
    player,
    transcribe,
)


@pytest.fixture
def env(tmp_path, monkeypatch, library):
    """Point the configuration at a temporary database and library."""
    monkeypatch.setenv(config.ENV_DB, str(tmp_path / "cli.db"))
    monkeypatch.setenv(config.ENV_LIBRARY, str(library))
    monkeypatch.delenv(config.ENV_OLLAMA_URL, raising=False)
    monkeypatch.delenv(config.ENV_EMBED_MODEL, raising=False)
    monkeypatch.setattr(embeddings, "first_reachable", lambda urls: urls[0])
    (library / "251").mkdir()
    (library / "251" / "dm7 G7 v.lage.mp3").write_bytes(b"one")
    return library


def _fake_mpv(monkeypatch):
    """Replace mpv; return its calls, each the command and the playlist lines.

    The playlist is a temporary file, so it is read while mpv "runs".
    """
    calls = []

    def play(command):
        playlist = Path(command[-1].removeprefix("--playlist="))
        calls.append((command, playlist.read_text(encoding="utf-8").splitlines()))
        return 0

    monkeypatch.setattr(player, "play", play)
    return calls


@pytest.mark.usefixtures("env")
def test_scan_requires_upgrade(capsys):
    assert cli.main(["scan"]) == cli.EXIT_SCHEMA
    assert "fretgrep db upgrade" in capsys.readouterr().err


@pytest.mark.usefixtures("env")
def test_scan_list_show(capsys):
    assert cli.main(["db", "upgrade"]) == cli.EXIT_OK
    assert cli.main(["scan"]) == cli.EXIT_OK
    assert "neu: 1" in capsys.readouterr().out

    assert cli.main(["list"]) == cli.EXIT_OK
    listing = capsys.readouterr().out
    assert "251/dm7 G7 v.lage.mp3" in listing
    assert "position=5 (0.9)" in listing
    assert listing.count("progression=ii-V-I") == 1

    assert cli.main(["show", "1"]) == cli.EXIT_OK
    details = capsys.readouterr().out
    assert "Tag-Vorschläge" in details
    assert "'v.lage'" in details

    assert cli.main(["show", "99"]) == cli.EXIT_ERROR


def test_list_missing(env, capsys):
    cli.main(["db", "upgrade"])
    cli.main(["scan"])
    (env / "251" / "dm7 G7 v.lage.mp3").unlink()
    cli.main(["scan"])
    capsys.readouterr()

    assert cli.main(["list", "--missing"]) == cli.EXIT_OK
    assert "[fehlt]" in capsys.readouterr().out


def test_scan_rejects_unknown_folder(env, capsys):
    cli.main(["db", "upgrade"])
    assert cli.main(["scan", str(env / "nope")]) == cli.EXIT_ERROR
    assert "nicht gefunden" in capsys.readouterr().err


@pytest.mark.usefixtures("env")
def test_tag_note_search(capsys):
    cli.main(["db", "upgrade"])
    cli.main(["scan"])
    capsys.readouterr()

    assert cli.main(["tag", "1", "Favorit", "üben"]) == cli.EXIT_OK
    assert "Favorit, üben" in capsys.readouterr().out
    assert cli.main(["note", "1", "langsam", "anfangen"]) == cli.EXIT_OK
    assert cli.main(["note", "1"]) == cli.EXIT_OK
    assert "langsam anfangen" in capsys.readouterr().out

    assert cli.main(["search", "favorit", "lage"]) == cli.EXIT_OK
    found = capsys.readouterr().out
    assert "dm7 G7 v.lage.mp3" in found
    assert "Eigene Tags: Favorit, üben" in found

    assert cli.main(["untag", "1", "üben"]) == cli.EXIT_OK
    assert cli.main(["untag", "1", "üben"]) == cli.EXIT_ERROR
    assert cli.main(["note", "1", "--clear"]) == cli.EXIT_OK
    assert cli.main(["scan"]) == cli.EXIT_OK
    capsys.readouterr()
    assert cli.main(["show", "1"]) == cli.EXIT_OK
    details = capsys.readouterr().out
    assert "Eigene Tags:   Favorit" in details
    assert "Notiz:         -" in details

    assert cli.main(["search", "gibtsnicht"]) == cli.EXIT_OK
    assert "Keine Treffer" in capsys.readouterr().out
    assert cli.main(["search", "mit"]) == cli.EXIT_ERROR
    assert cli.main(["tag", "99", "x"]) == cli.EXIT_ERROR


@pytest.mark.usefixtures("env")
def test_transcribe(capsys, monkeypatch):
    class Model:
        """Stand-in for the Whisper model."""

        def transcribe(self, _audio, **_options):
            return [type("Segment", (), {"text": "erste Lage"})], type(
                "Info", (), {"language": "de"}
            )

    monkeypatch.setattr(transcribe, "load_model", lambda name: Model())
    monkeypatch.setattr(transcribe, "decode_audio", lambda path: None)
    cli.main(["db", "upgrade"])
    cli.main(["scan"])
    capsys.readouterr()

    assert cli.main(["transcribe"]) == cli.EXIT_OK
    assert "[1/1] 251/dm7 G7 v.lage.mp3: 2 Wörter" in capsys.readouterr().out
    assert cli.main(["transcribe"]) == cli.EXIT_OK
    assert "Nichts zu tun" in capsys.readouterr().out
    assert cli.main(["show", "1"]) == cli.EXIT_OK
    assert "erste Lage" in capsys.readouterr().out


@pytest.mark.usefixtures("env")
def test_embed_and_semantic_search(capsys, monkeypatch):
    def embedder(url, model):
        assert (url, model) == ("http://host:1", "fake")
        return lambda texts: [[1.0, float("lage" in text)] for text in texts]

    monkeypatch.setattr(embeddings, "ollama_embedder", embedder)
    cli.main(["db", "upgrade"])
    cli.main(["scan"])
    capsys.readouterr()

    assert cli.main(["embed"]) == cli.EXIT_ERROR
    assert cli.main(["search", "--semantic", "lage"]) == cli.EXIT_ERROR
    assert capsys.readouterr().err.count(config.ENV_EMBED_MODEL) == 2

    monkeypatch.setenv(config.ENV_OLLAMA_URL, "http://host:1")
    monkeypatch.setenv(config.ENV_EMBED_MODEL, "fake")
    assert cli.main(["search", "--semantic", "gibtsnicht"]) == cli.EXIT_OK
    captured = capsys.readouterr()
    assert "Keine Treffer" in captured.out
    assert "fretgrep embed" in captured.err

    assert cli.main(["embed"]) == cli.EXIT_OK
    assert "Vektoren berechnet: 1 (Modell fake)" in capsys.readouterr().out
    assert cli.main(["embed"]) == cli.EXIT_OK
    assert "Nichts zu tun" in capsys.readouterr().out

    # Meaning is the default; -k asks for the plain keyword search.
    for flags in (["-s"], []):
        assert cli.main(["search", *flags, "gibtsnicht"]) == cli.EXIT_OK
        captured = capsys.readouterr()
        assert "dm7 G7 v.lage.mp3" in captured.out
        assert not captured.err
    assert cli.main(["search", "-k", "gibtsnicht"]) == cli.EXIT_OK
    assert "Keine Treffer" in capsys.readouterr().out


@pytest.mark.usefixtures("env")
def test_embed_and_search_report_failing_server(capsys, monkeypatch):
    def embed(_texts):
        raise embeddings.EmbeddingError("HTTP 404: model not found")

    monkeypatch.setattr(embeddings, "ollama_embedder", lambda url, model: embed)
    monkeypatch.setenv(config.ENV_EMBED_MODEL, "fake")
    cli.main(["db", "upgrade"])
    cli.main(["scan"])
    capsys.readouterr()

    assert cli.main(["embed"]) == cli.EXIT_ERROR
    assert "model not found" in capsys.readouterr().err


@pytest.mark.usefixtures("env")
def test_search_falls_back_to_keywords_without_server(capsys, monkeypatch):
    monkeypatch.setattr(embeddings, "first_reachable", lambda urls: None)
    monkeypatch.setenv(config.ENV_OLLAMA_URL, "http://host:1")
    monkeypatch.setenv(config.ENV_EMBED_MODEL, "fake")
    cli.main(["db", "upgrade"])
    cli.main(["scan"])
    capsys.readouterr()

    assert cli.main(["search", "lage"]) == cli.EXIT_OK
    captured = capsys.readouterr()
    assert "dm7 G7 v.lage.mp3" in captured.out
    assert "http://host:1" in captured.err
    assert "nur nach Stichwörtern" in captured.err

    assert cli.main(["search", "-k", "lage"]) == cli.EXIT_OK
    assert not capsys.readouterr().err
    assert cli.main(["search", "-s", "lage"]) == cli.EXIT_ERROR
    assert cli.main(["embed"]) == cli.EXIT_ERROR
    assert capsys.readouterr().err.count("Kein Ollama-Server erreichbar") == 2


def test_play(env, capsys, monkeypatch):
    commands = _fake_mpv(monkeypatch)
    cli.main(["db", "upgrade"])
    cli.main(["scan"])
    capsys.readouterr()

    assert cli.main(["play", "1", "-s", "0.7", "-p", "-2", "-l", "2-4"]) == cli.EXIT_OK
    assert "251/dm7 G7 v.lage.mp3" in capsys.readouterr().out
    command, playlist = commands[-1]
    assert "--speed=0.7" in command
    assert "--ab-loop-a=2" in command
    assert playlist[1:] == ["#EXTINF:-1,ID 1  251/dm7 G7 v.lage.mp3",
                            str(env / "251" / "dm7 G7 v.lage.mp3")]

    assert cli.main(["play", "99"]) == cli.EXIT_ERROR
    assert cli.main(["play", "1", "--speed", "0"]) == cli.EXIT_ERROR
    assert cli.main(["play", "1", "--loop", "4-2"]) == cli.EXIT_ERROR
    assert len(commands) == 1


def test_play_several_and_search_hits(env, capsys, monkeypatch):
    commands = _fake_mpv(monkeypatch)
    (env / "blues lage.mp3").write_bytes(b"two")
    (env / "bossa lage.mp3").write_bytes(b"three")
    cli.main(["db", "upgrade"])
    cli.main(["scan"])
    capsys.readouterr()

    def played():
        return _played(commands, env)

    assert cli.main(["play", "3", "1"]) == cli.EXIT_OK
    assert played() == ["bossa lage.mp3", "251/dm7 G7 v.lage.mp3"]
    assert "nächstes Stück" in capsys.readouterr().out
    assert cli.main(["play", "3", "1", "-l", "2-4"]) == cli.EXIT_ERROR
    assert cli.main(["play", "3", "99"]) == cli.EXIT_ERROR
    assert "einzelnen Aufnahme" in capsys.readouterr().err
    assert len(commands) == 1

    # The hits are played in the order in which the search lists them.
    assert cli.main(["search", "lage", "--play", "--speed", "0.5"]) == cli.EXIT_OK
    listed = [
        line.split(maxsplit=2)[2]
        for line in capsys.readouterr().out.splitlines()
        if line.endswith(".mp3")
    ]
    assert len(listed) == 3 and played() == listed
    assert "--speed=0.5" in commands[-1][0]

    (env / "blues lage.mp3").unlink()
    assert cli.main(["search", "lage", "--play"]) == cli.EXIT_OK
    assert len(played()) == 2 and "blues lage.mp3" not in played()
    assert "1 Datei(en) nicht gefunden" in capsys.readouterr().err
    assert cli.main(["search", "bossa", "--play"]) == cli.EXIT_OK
    assert played() == ["bossa lage.mp3"]
    assert cli.main(["search", "blues", "--play"]) == cli.EXIT_ERROR
    assert "übersprungen" in capsys.readouterr().err
    assert cli.main(["search", "gibtsnicht", "--play"]) == cli.EXIT_OK
    assert cli.main(["search", "lage", "--play", "--speed", "0"]) == cli.EXIT_ERROR
    assert len(commands) == 4


def test_play_missing_file_or_player(env, capsys, monkeypatch):
    def no_player(_command):
        raise player.PlayerMissingError("mpv")

    monkeypatch.setattr(player, "play", no_player)
    cli.main(["db", "upgrade"])
    cli.main(["scan"])
    capsys.readouterr()

    assert cli.main(["play", "1"]) == cli.EXIT_ERROR
    assert "apt install mpv" in capsys.readouterr().err
    (env / "251" / "dm7 G7 v.lage.mp3").unlink()
    assert cli.main(["play", "1"]) == cli.EXIT_ERROR
    assert "Datei nicht gefunden" in capsys.readouterr().err


@pytest.mark.usefixtures("env")
def test_notes(capsys, monkeypatch, tmp_path):
    calls = []

    def detect(path):
        calls.append(path.name)
        return [
            notes.Note(1.0, 1.2, 60, 0.7),
            notes.Note(1.2, 1.4, 63, 0.4),
            notes.Note(1.4, 1.6, 67, 0.7),
        ]

    monkeypatch.setattr(notes, "load_detector", lambda: (detect, "fake 1"))
    cli.main(["db", "upgrade"])
    cli.main(["scan"])
    capsys.readouterr()

    assert cli.main(["notes", "1"]) == cli.EXIT_OK
    shown = capsys.readouterr().out
    assert "fake 1: 2 von 3 Noten, ab Lautstärke 0.5" in shown
    assert "1.0s  C4 G4" in shown

    assert cli.main(["notes", "1", "-m", "0"]) == cli.EXIT_OK
    assert "C4 Eb4 G4" in capsys.readouterr().out
    assert len(calls) == 1
    assert cli.main(["notes", "1", "--redo"]) == cli.EXIT_OK
    assert len(calls) == 2

    written = []
    monkeypatch.setattr(
        notes, "write_midi", lambda *args: written.append(args) or 2
    )
    assert cli.main(["notes", "1", "--midi", "lick.mid"]) == cli.EXIT_OK
    assert "MIDI gespeichert: lick.mid (2 Noten)" in capsys.readouterr().out
    assert written[0][1:] == (0.5, Path("lick.mid"))

    assert cli.main(["notes", "1", "--sheet", str(tmp_path / "lick.ly")]) == cli.EXIT_OK
    assert "Notenblatt gespeichert" in capsys.readouterr().out
    source = (tmp_path / "lick.ly").read_text(encoding="utf-8")
    assert 'title = "251/dm7 G7 v.lage.mp3"' in source
    assert "c'4" in source and "g'4" in source and "ees'4" not in source
    assert cli.main(["notes", "1", "--sheet", "lick.docx"]) == cli.EXIT_ERROR
    assert ".pdf" in capsys.readouterr().err
    assert cli.main(["notes", "99"]) == cli.EXIT_ERROR


@pytest.mark.usefixtures("env")
def test_notes_without_basic_pitch(capsys, monkeypatch):
    def load_detector():
        raise notes.MissingDependencyError("basic_pitch")

    monkeypatch.setattr(notes, "load_detector", load_detector)
    cli.main(["db", "upgrade"])
    cli.main(["scan"])
    capsys.readouterr()

    assert cli.main(["notes", "1"]) == cli.EXIT_ERROR
    assert "--no-deps basic-pitch" in capsys.readouterr().err


@pytest.mark.usefixtures("env")
def test_notes_sheet_with_rhythm(capsys, monkeypatch, tmp_path):
    def detect(_path):
        # eight even eighths at 100 beats per minute
        return [notes.Note(1 + 0.3 * i, 1.25 + 0.3 * i, 60 + i, 0.8) for i in range(8)]

    monkeypatch.setattr(notes, "load_detector", lambda: (detect, "fake 1"))
    cli.main(["db", "upgrade"])
    cli.main(["scan"])
    capsys.readouterr()
    target = tmp_path / "lick.ly"

    assert cli.main(["notes", "1", "--sheet", str(target), "--rhythm"]) == cli.EXIT_OK
    source = target.read_text(encoding="utf-8")
    assert "Tempo 100" in source
    assert "8[" in source and "\\omit Stem c'4" not in source

    assert cli.main(["notes", "1", "--sheet", str(target), "--tempo", "50"]) == 0
    assert "16[" in target.read_text(encoding="utf-8")

    assert cli.main(["notes", "1", "--rhythm"]) == cli.EXIT_ERROR
    assert cli.main(["notes", "1", "--sheet", str(target), "--tempo", "5"]) == 1
    assert "zwischen 20 und 400" in capsys.readouterr().err


def test_logo_only_on_a_terminal_and_only_for_overview_calls(capsys, monkeypatch):
    def output(arguments):
        try:
            assert cli.main(arguments) == cli.EXIT_OK
        except SystemExit as stop:
            assert stop.code == 0
        return capsys.readouterr().out

    assert banner.NOTE not in output([])
    assert "Üblicher Ablauf" in output([])
    assert output(["--version"]) == banner.version() + "\n"

    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)
    for arguments in ([], ["--help"], ["--version"]):
        assert output(arguments).startswith(banner.render(color=True))
    assert banner.NOTE not in output(["search", "--help"])

    monkeypatch.setenv("NO_COLOR", "1")
    plain = output(["--version"])
    assert plain.startswith(banner.render()) and "\033" not in plain
    assert "|___/" in plain and plain.endswith(banner.version() + "\n")


def test_help_explains_workflow_settings_and_every_command(capsys):
    with pytest.raises(SystemExit) as stop:
        cli.main(["--help"])
    assert stop.value.code == 0
    overview = capsys.readouterr().out
    assert "Üblicher Ablauf" in overview
    for name in (config.ENV_DB, config.ENV_LIBRARY, config.ENV_OLLAMA_URL):
        assert name in overview

    commands = [
        "db", "scan", "list", "show", "search", "tag", "untag", "note",
        "transcribe", "embed", "play", "notes", "chat", "tones", "completion",
    ]
    for command in commands:
        assert f"\n    {command} " in overview
        with pytest.raises(SystemExit) as stop:
            cli.main([command, "--help"])
        assert stop.value.code == 0
        assert "diese Hilfe anzeigen" in capsys.readouterr().out

    with pytest.raises(SystemExit):
        cli.main(["notes", "--help"])
    details = capsys.readouterr().out
    assert "Beispiele:" in details and "--tempo 110" in details


@pytest.mark.usefixtures("env")
def test_notes_show_opens_the_sheet_in_a_window(capsys, monkeypatch, tmp_path):
    def detect(_path):
        return [notes.Note(1 + 0.3 * i, 1.25 + 0.3 * i, 60 + i, 0.8) for i in range(8)]

    monkeypatch.setattr(notes, "load_detector", lambda: (detect, "fake 1"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    shown = []
    monkeypatch.setattr(cli.sheet, "show", lambda *args: shown.append(args))
    cli.main(["db", "upgrade"])
    cli.main(["scan"])
    capsys.readouterr()

    assert cli.main(["notes", "1", "-w", "--rhythm"]) == cli.EXIT_OK
    assert "Notenblatt geöffnet" in capsys.readouterr().out
    text, path = shown[0]
    assert "Tempo 100" in text
    assert path == tmp_path / "cache" / "fretgrep" / "sheets" / "notes-1.pdf"

    target = tmp_path / "lick.ly"
    assert cli.main(["notes", "1", "--show", "--sheet", str(target)]) == 0
    assert target.is_file() and len(shown) == 2

    def no_viewer(_text, _path):
        raise cli.sheet.ViewerMissingError("xdg-open")

    monkeypatch.setattr(cli.sheet, "show", no_viewer)
    assert cli.main(["notes", "1", "--show"]) == cli.EXIT_ERROR
    assert "--sheet DATEI" in capsys.readouterr().err


@pytest.mark.usefixtures("env")
def test_chat_answers_with_tools_and_searches_recordings(capsys, monkeypatch):
    cli.main(["db", "upgrade"])
    cli.main(["scan"])
    capsys.readouterr()
    seen = []

    def transport(_url):
        replies = [
            [{"message": {"tool_calls": [
                {"function": {"name": "tones", "arguments": {"symbol": "G7HM5"}}},
                {"function": {"name": "search_recordings",
                              "arguments": {"query": "lage"}}},
            ]}}],
            [{"message": {"content": "Siehe ID 1."}}],
        ]

        def send(body):
            seen.append(body)
            yield from replies.pop(0)

        return send

    monkeypatch.setattr(assistant, "ollama_transport", transport)
    assert cli.main(["chat", "--model", "x", "Töne", "von", "G7HM5?"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "→ tones: G7HM5" in out and out.endswith("Siehe ID 1.\n")
    assert seen[0]["model"] == "x"
    results = [m["content"] for m in seen[1]["messages"] if m["role"] == "tool"]
    assert "G Ab B C D Eb F" in results[0]
    assert results[1].startswith("ID 1:\n251 dm7 G7 v.lage")


@pytest.mark.usefixtures("env")
def test_chat_reports_a_missing_model(capsys, monkeypatch):
    def transport(_url):
        def send(_body):
            raise assistant.ChatError("HTTP 404: model 'x' not found")
            yield  # pylint: disable=unreachable

        return send

    monkeypatch.setattr(assistant, "ollama_transport", transport)
    assert cli.main(["chat", "--model", "x", "hallo"]) == cli.EXIT_ERROR
    assert "ollama pull x" in capsys.readouterr().err


@pytest.mark.usefixtures("env")
def test_chat_conversation_until_exit(capsys, monkeypatch):
    def transport(_url):
        def send(_body):
            yield {"message": {"content": "Antwort"}}

        return send

    questions = iter(["erste Frage", "", "exit"])
    monkeypatch.setattr(assistant, "ollama_transport", transport)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(questions))
    assert cli.main(["chat"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert out.count("\nAntwort\n") == 1 and "Strg+D" in out


def test_tones_without_a_model(capsys):
    assert cli.main(["tones", "G7", "HM5"]) == cli.EXIT_OK
    assert "G Ab B C D Eb F" in capsys.readouterr().out
    assert cli.main(["tones", "C", "quatsch"]) == cli.EXIT_ERROR
    assert "weder als Akkord noch als Skala" in capsys.readouterr().err


def _recording_transport(seen, answer="Antwort"):
    """Return a fake ollama_transport that records each request."""
    def transport(_url):
        def send(body):
            seen.append(body)
            yield {"message": {"content": answer}}

        return send

    return transport


@pytest.mark.usefixtures("env")
def test_chat_continue_keeps_the_last_conversation(capsys, monkeypatch):
    seen = []
    monkeypatch.setattr(assistant, "ollama_transport", _recording_transport(seen))

    assert cli.main(["chat", "-c", "erste"]) == cli.EXIT_OK
    assert "Kein früheres Gespräch" in capsys.readouterr().err
    assert "einzelne Frage" in seen[0]["messages"][0]["content"]

    assert cli.main(["chat", "-c", "ja", "bitte"]) == cli.EXIT_OK
    assert "1 Frage(n)" in capsys.readouterr().err
    contents = [m["content"] for m in seen[1]["messages"][1:]]
    assert contents == ["erste", "Antwort", "ja bitte"]

    assert cli.main(["chat", "neu"]) == cli.EXIT_OK
    assert [m["content"] for m in seen[2]["messages"][1:]] == ["neu"]


@pytest.mark.usefixtures("env")
def test_chat_runs_fretgrep_commands_and_goes_on(capsys, monkeypatch):
    seen = []
    monkeypatch.setattr(assistant, "ollama_transport", _recording_transport(seen))
    lines = iter(["!tones G7HM5", "!fretgrep tones", "!chat", "!", "frage", "exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(lines))

    assert cli.main(["chat"]) == cli.EXIT_OK
    captured = capsys.readouterr()
    assert "G Ab B C D Eb F" in captured.out and "\nAntwort\n" in captured.out
    assert "schon im Chat" in captured.err and "fehlt der Befehl" in captured.err
    assert len(seen) == 1  # only the question went to the model
    assert "einzelne Frage" not in seen[0]["messages"][0]["content"]


@pytest.fixture
def three(env, capsys, monkeypatch):
    """Three scanned recordings; return the mpv calls."""
    commands = _fake_mpv(monkeypatch)
    (env / "blues lage.mp3").write_bytes(b"two")
    (env / "bossa lage.mp3").write_bytes(b"three")
    cli.main(["db", "upgrade"])
    cli.main(["scan"])
    capsys.readouterr()
    return commands


def _played(commands, library):
    """Return the files mpv played last, each relative to the library."""
    _, playlist = commands[-1]
    files = [line for line in playlist if not line.startswith("#")]
    return [file.removeprefix(str(library) + "/") for file in files]


def test_playlist_build_and_play(env, three, capsys):
    assert cli.main(["playlist"]) == cli.EXIT_OK
    assert "Noch keine" in capsys.readouterr().out
    assert cli.main(["playlist", "--names"]) == cli.EXIT_OK
    assert capsys.readouterr().out == ""
    assert cli.main(["playlist", "new", "HM5  üben"]) == cli.EXIT_OK
    assert cli.main(["playlist", "new", "hm5 üben"]) == cli.EXIT_ERROR
    assert "gibt es schon" in capsys.readouterr().err

    # A recording stands only once in a list, but may stand in several lists.
    assert cli.main(["playlist", "add", "hm5 üben", "3", "1", "3"]) == cli.EXIT_OK
    assert cli.main(["playlist", "add", "hm5 üben", "1", "2"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "1 hinzugefügt, 1 stand(en) schon darin; jetzt 3 Aufnahmen" in out
    assert cli.main(["playlist", "add", "andere", "1"]) == cli.EXIT_OK
    assert "Neue Wiedergabeliste 'andere'" in capsys.readouterr().out
    assert cli.main(["playlist", "add", "andere", "99"]) == cli.EXIT_ERROR

    assert cli.main(["playlist"]) == cli.EXIT_OK
    assert capsys.readouterr().out.splitlines() == [
        "andere  (1 Aufnahme)",
        "HM5 üben  (3 Aufnahmen)",
    ]
    assert cli.main(["playlist", "--names"]) == cli.EXIT_OK
    assert capsys.readouterr().out.splitlines() == ["andere", "HM5 üben"]

    assert cli.main(["playlist", "show", "hm5 ÜBEN"]) == cli.EXIT_OK
    assert "Vorschläge" in capsys.readouterr().out
    assert not three

    assert cli.main(["playlist", "show", "hm5 üben", "--play", "-s", "0.7"]) == 0
    assert _played(three, env) == [
        "bossa lage.mp3", "251/dm7 G7 v.lage.mp3", "blues lage.mp3"
    ]
    assert "--speed=0.7" in three[-1][0]

    assert cli.main(["playlist", "remove", "hm5 üben", "1"]) == cli.EXIT_OK
    (env / "blues lage.mp3").unlink()
    assert cli.main(["playlist", "play", "hm5 üben", "-p", "-2"]) == cli.EXIT_OK
    assert _played(three, env) == ["bossa lage.mp3"]
    assert "1 Datei(en) nicht gefunden" in capsys.readouterr().err

    assert cli.main(["playlist", "remove", "hm5 üben", "1"]) == cli.EXIT_ERROR
    assert cli.main(["playlist", "play", "gibtsnicht"]) == cli.EXIT_ERROR
    assert cli.main(["playlist", "play", "andere", "-s", "0"]) == cli.EXIT_ERROR
    assert cli.main(["playlist", "delete", "hm5 üben"]) == cli.EXIT_OK
    assert cli.main(["playlist", "show", "hm5 üben"]) == cli.EXIT_ERROR
    assert cli.main(["show", "3"]) == cli.EXIT_OK
    assert len(three) == 2


@pytest.mark.usefixtures("env")
def test_search_saves_hits(three, capsys):
    assert cli.main(["search", "lage", "--save", "lagen"]) == cli.EXIT_OK
    assert cli.main(["search", "bossa", "--save", "Lagen"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "Neue Wiedergabeliste 'lagen'" in out
    assert "0 hinzugefügt, 1 stand(en) schon darin; jetzt 3 Aufnahmen" in out
    assert cli.main(["search", "gibtsnicht", "--save", "leer"]) == cli.EXIT_OK
    assert cli.main(["playlist"]) == cli.EXIT_OK
    assert "leer" not in capsys.readouterr().out
    assert not three


def test_playlist_survives_moving_files(env, three, capsys):
    cli.main(["playlist", "add", "liste", "3"])
    (env / "neu").mkdir()
    (env / "bossa lage.mp3").rename(env / "neu" / "bossa lage.mp3")
    cli.main(["scan"])
    capsys.readouterr()
    assert cli.main(["playlist", "play", "liste"]) == cli.EXIT_OK
    assert _played(three, env) == ["neu/bossa lage.mp3"]


def test_playlist_export(env, three, capsys, tmp_path):
    cli.main(["playlist", "add", "liste", "3", "1"])
    capsys.readouterr()
    assert cli.main(["playlist", "export", "liste"]) == cli.EXIT_OK
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "#EXTM3U"
    assert lines[1].startswith("#EXTINF:") and lines[1].endswith(",bossa lage")
    assert lines[2] == str((env / "bossa lage.mp3").resolve())
    assert lines[4] == str((env / "251" / "dm7 G7 v.lage.mp3").resolve())

    (env / "bossa lage.mp3").unlink()
    target = tmp_path / "liste.m3u"
    assert cli.main(["playlist", "export", "liste", "-o", str(target)]) == 0
    assert "weggelassen" in capsys.readouterr().err
    assert target.read_text(encoding="utf-8").count("#EXTINF") == 1
    assert cli.main(["playlist", "export", "gibtsnicht"]) == cli.EXIT_ERROR
    assert not three
