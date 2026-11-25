"""The ``fretgrep chat`` command: the assistant for harmony and the collection."""

import argparse
import json
import shlex
from collections.abc import Callable
from pathlib import Path

from fretgrep import assistant, chat_output, config, db, embeddings, search, theory
from fretgrep import cli_common as common
from fretgrep.cli_common import EXIT_ERROR, EXIT_OK
from fretgrep.filename_parser import load_vocabulary

_CHAT_RESULTS = 8
# Characters per recording that the model gets from a search.
_CHAT_EXCERPT = 600
_CHAT_EXIT = ("exit", "quit", "ende")
# Starts a line in the conversation that runs a fretgrep command.
_CHAT_COMMAND = "!"
_TONES_TOOL = assistant.Tool(
    "tones",
    "Berechnet die Töne und Intervalle eines Akkords und/oder einer Skala "
    "auf einem Grundton, mit korrekter Schreibweise.",
    "symbol",
    "Grundton mit Akkord und/oder Skala, z. B. G7, Dm7b5, Cmaj7#11, G7HM5, "
    "C lydisch, F# alteriert, Bb MM4, A Moll-Pentatonik",
    theory.tones,
)


def _search_for_chat(query: str) -> str:
    """Search the recordings for the assistant; by meaning if possible."""
    found = None
    embedder = common.embedder() if config.embed_model() else None
    with db.open_session(config.database_path()) as session:
        if isinstance(embedder, tuple):
            embed, model_name = embedder
            try:
                found = embeddings.hybrid_search(
                    session, embed, model_name, query, _CHAT_RESULTS
                )
            except embeddings.EmbeddingError:
                found = None
        if found is None:
            ids = search.search_ids(session, query, _CHAT_RESULTS, match_all=False)
            found = search.load(session, ids)
        return "\n\n".join(
            f"ID {recording.id}:\n"
            + embeddings.document_text(recording)[:_CHAT_EXCERPT]
            for recording in found
        ) or "Keine Treffer."


_SEARCH_TOOL = assistant.Tool(
    "search_recordings",
    "Durchsucht die Lick-Aufnahmen des Nutzers nach Stichwörtern und "
    "Bedeutung. Liefert je Treffer ID, Pfad, Tags, Notiz und Gesprochenes.",
    "query",
    "Suchbegriffe, z. B. 'hm5 wes montgomery' oder 'trauriger blues'",
    _search_for_chat,
)


def _chat_failed(error: assistant.ChatError, model: str) -> str:
    if "not found" in str(error):
        return (
            f"Das Modell {model} gibt es auf dem Ollama-Server nicht. "
            f"Dort 'ollama pull {model}' ausführen oder "
            f"${config.ENV_CHAT_MODEL} ändern."
        )
    return f"Der Ollama-Server antwortet nicht richtig: {error}."


def _chat_file() -> Path:
    return config.cache_path() / "chat.json"


def _save_chat(conversation: assistant.Conversation) -> None:
    """Keep the conversation, so that 'chat -c' can continue it."""
    path = _chat_file()
    data = {"model": conversation.model, "messages": conversation.history}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError as error:
        common.print_error(f"Hinweis: Gespräch nicht gespeichert: {error}")


def _resume_chat(conversation: assistant.Conversation) -> None:
    """Load the last conversation, or say that there is none."""
    try:
        data = json.loads(_chat_file().read_text(encoding="utf-8"))
        conversation.restore(data["messages"])
    except (OSError, ValueError, KeyError, TypeError):
        common.print_error(
            "Hinweis: Kein früheres Gespräch gefunden, es beginnt ein neues."
        )
        return
    questions = sum(1 for message in conversation.history if message["role"] == "user")
    common.print_error(f"Setze das letzte Gespräch fort ({questions} Frage(n)).")


def _answer(conversation: assistant.Conversation, question: str) -> int:
    """Ask one question and stream the answer; return the exit code."""
    output = chat_output.ChatOutput()
    output.wait()
    try:
        conversation.ask(question, output.text, output.thinking, output.tool)
    except assistant.ChatError as error:
        output.end()
        common.print_error(_chat_failed(error, conversation.model))
        return EXIT_ERROR
    except KeyboardInterrupt:
        output.end()
        common.print_error("Abgebrochen.")
        return EXIT_ERROR
    output.end()
    _save_chat(conversation)
    return EXIT_OK


def _run_in_chat(line: str, run: Callable[[list[str]], int]) -> None:
    """Run a fretgrep command typed in the conversation, e.g. "play 46"."""
    try:
        argv = shlex.split(line)
    except ValueError as error:
        common.print_error(f"Befehl nicht lesbar: {error}")
        return
    if argv[:1] == ["fretgrep"]:
        argv = argv[1:]
    if not argv:
        common.print_error("Nach '!' fehlt der Befehl, z. B. '!play 46'.")
        return
    if argv[0] == "chat":
        common.print_error("Du bist schon im Chat.")
        return
    try:
        run(argv)
    except SystemExit:
        pass  # wrong arguments or --help; argparse has said why
    except KeyboardInterrupt:
        print()


def _chat_loop(
    conversation: assistant.Conversation, run: Callable[[list[str]], int]
) -> int:
    """Hold a conversation until the user ends it."""
    try:
        import readline  # pylint: disable=import-outside-toplevel,unused-import
    except ImportError:
        pass  # input() still works, only without line editing
    print(
        f"Gespräch mit {conversation.model}. Strg+D oder 'exit' beendet, "
        "Strg+C bricht eine Antwort ab,\n"
        f"'{_CHAT_COMMAND}play 46' führt einen fretgrep-Befehl aus."
    )
    while True:
        try:
            question = input("\n» ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return EXIT_OK
        if question.lower() in _CHAT_EXIT:
            return EXIT_OK
        if question.startswith(_CHAT_COMMAND):
            _run_in_chat(question[len(_CHAT_COMMAND):], run)
        elif question:
            _answer(conversation, question)


def cmd_chat(args: argparse.Namespace, run: Callable[[list[str]], int]) -> int:
    """Talk with the assistant; "!" lines run fretgrep commands through run."""
    urls = config.ollama_urls()
    url = embeddings.first_reachable(urls)
    if url is None:
        common.print_error(
            f"Kein Ollama-Server erreichbar (versucht: {', '.join(urls)})."
        )
        return EXIT_ERROR
    conversation = assistant.Conversation(
        assistant.ollama_transport(url),
        args.model or config.chat_model(),
        assistant.system_prompt(load_vocabulary().descriptions, bool(args.words)),
        [_TONES_TOOL, _SEARCH_TOOL],
        think=args.think,
    )
    if args.resume:
        _resume_chat(conversation)
    if args.words:
        return _answer(conversation, " ".join(args.words))
    return _chat_loop(conversation, run)
