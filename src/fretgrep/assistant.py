"""A chat assistant: a language model on the Ollama server, with tools.

The model writes the answers; facts it is bad at come from tools. It
calls ``tones`` for the notes of chords and scales, which ``theory``
computes exactly, and may search the user's recordings. The transport
is a plain function from a request to response chunks, so tests can
supply their own.
"""

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

# A long answer of a large model on a CPU can take minutes.
TIMEOUT_S = 900
# Rounds of tool calls per question before the assistant gives up.
MAX_TOOL_ROUNDS = 6

Transport = Callable[[dict], Iterable[dict]]
Output = Callable[[str], None]

_SYSTEM = """\
Du bist der Assistent von fretgrep, einem Programm für eine Sammlung
selbst aufgenommener Jazzgitarren-Licks. Du beantwortest Fragen zu
Harmonielehre, Skalen, Akkorden, Improvisation und Gitarrentechnik.

Regeln:
- Antworte auf Deutsch, knapp und fachlich genau.
- Für die Töne oder Intervalle eines Akkords oder einer Skala rufst du
  immer das Werkzeug tones auf und rechnest nicht selbst. Übernimm die
  Töne genau so, wie das Werkzeug sie liefert. Bei mehreren Akkorden
  oder Skalen rufst du es für jeden einzeln auf.
- Notennamen sind englisch: B ist das deutsche H, Bb das deutsche B.
- HM5 heißt die fünfte Stufe von harmonisch Moll, gebaut auf dem
  genannten Grundton; G7HM5 ist ein G7 mit der Skala G HM5. Entsprechend
  HM1 bis HM7 und MM1 bis MM7 (melodisch Moll).
- Fragt der Nutzer nach Aufnahmen oder Beispielen aus seiner Sammlung,
  rufst du search_recordings auf. Nenne Treffer mit ihrer ID, denn mit
  'fretgrep play ID' spielt er sie ab und mit 'fretgrep notes ID --show'
  sieht er die Noten. Erfinde keine Aufnahmen.
- Weißt du etwas nicht sicher, sag das.
"""

# Added for a question on the command line, where nobody can answer back.
_SINGLE = """\
Dies ist eine einzelne Frage von der Kommandozeile; der Nutzer kann nicht
direkt antworten. Antworte deshalb vollständig, ohne Rückfragen und ohne
Angebote wie "Soll ich …?". Will er Beispiele oder Aufnahmen, suche gleich
danach.
"""


class ChatError(RuntimeError):
    """The model server could not be reached or refused the request."""


@dataclass(frozen=True)
class Tool:
    """A function the model may call with one text argument."""

    name: str
    description: str
    parameter: str
    parameter_description: str
    run: Callable[[str], str]

    def schema(self) -> dict:
        """Return the description the model gets, in Ollama's format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        self.parameter: {
                            "type": "string",
                            "description": self.parameter_description,
                        }
                    },
                    "required": [self.parameter],
                },
            },
        }


def system_prompt(descriptions: dict[str, str], single: bool = False) -> str:
    """Return the instructions, with the explanations from the vocabulary.

    ``single`` marks a lone question, after which nobody answers back.
    """
    prompt = _SYSTEM + ("\n" + _SINGLE if single else "")
    if not descriptions:
        return prompt
    glossary = "\n".join(f"- {name}: {text}" for name, text in descriptions.items())
    heading = "Abkürzungen und Namen in der Sammlung des Nutzers:"
    return f"{prompt}\n{heading}\n{glossary}\n"


def ollama_transport(base_url: str) -> Transport:
    """Return a transport that streams from ``/api/chat`` of an Ollama server."""
    url = base_url.rstrip("/") + "/api/chat"

    def send(body: dict) -> Iterator[dict]:
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                for line in response:
                    if line.strip():
                        yield json.loads(line)
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace").strip()
            raise ChatError(f"HTTP {error.code}: {detail}") from error
        except (OSError, ValueError) as error:
            raise ChatError(str(error)) from error

    return send


def _arguments(call: dict) -> dict:
    """Return the arguments of a tool call; some models send them as text."""
    arguments = call.get("function", {}).get("arguments") or {}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            return {}
    return arguments if isinstance(arguments, dict) else {}


class Conversation:
    """A chat that keeps its history, so follow-up questions work."""

    def __init__(
        self,
        send: Transport,
        model: str,
        system: str,
        tools: list[Tool],
        think: bool = False,
    ):
        self.send = send
        self.model = model
        self.tools = {tool.name: tool for tool in tools}
        self.think = think
        self.messages: list[dict] = [{"role": "system", "content": system}]

    @property
    def history(self) -> list[dict]:
        """Return the messages so far, without the instructions."""
        return self.messages[1:]

    def restore(self, history: list[dict]) -> None:
        """Continue an earlier conversation; the instructions stay current."""
        self.messages[1:] = [
            message for message in history if isinstance(message, dict)
        ]

    def ask(
        self,
        question: str,
        on_text: Output,
        on_thinking: Output = lambda _text: None,
        on_tool: Callable[[str, str], None] = lambda _name, _argument: None,
    ) -> str:
        """Ask a question and return the answer.

        The answer streams to ``on_text`` while it is written. If anything
        goes wrong, including Ctrl+C, the history stays as it was before.
        """
        before = len(self.messages)
        self.messages.append({"role": "user", "content": question})
        try:
            for _round in range(MAX_TOOL_ROUNDS):
                message = self._reply(on_text, on_thinking)
                self.messages.append(message)
                calls = message.get("tool_calls") or []
                if not calls:
                    return message["content"]
                for call in calls:
                    self.messages.append(self._call(call, on_tool))
            raise ChatError("Das Modell ruft immer weiter Werkzeuge auf.")
        except BaseException:
            del self.messages[before:]
            raise

    def _reply(self, on_text: Output, on_thinking: Output) -> dict:
        body = {
            "model": self.model,
            "messages": list(self.messages),
            "tools": [tool.schema() for tool in self.tools.values()],
            "think": self.think,
            "stream": True,
        }
        content: list[str] = []
        calls: list[dict] = []
        for chunk in self.send(body):
            if "error" in chunk:
                raise ChatError(str(chunk["error"]))
            message = chunk.get("message") or {}
            if message.get("thinking"):
                on_thinking(message["thinking"])
            if message.get("content"):
                content.append(message["content"])
                on_text(message["content"])
            calls += message.get("tool_calls") or []
        reply = {"role": "assistant", "content": "".join(content)}
        if calls:
            reply["tool_calls"] = calls
        return reply

    def _call(self, call: dict, on_tool: Callable[[str, str], None]) -> dict:
        """Run one tool call and return the message with its result."""
        name = call.get("function", {}).get("name", "")
        tool = self.tools.get(name)
        if tool is None:
            result = f"Unbekanntes Werkzeug {name!r}."
        else:
            argument = str(_arguments(call).get(tool.parameter, ""))
            on_tool(name, argument)
            result = tool.run(argument)
        return {"role": "tool", "tool_name": name, "content": result}
