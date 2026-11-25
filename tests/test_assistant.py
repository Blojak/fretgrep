"""Tests for the chat assistant, with a scripted model instead of Ollama."""
# pylint: disable=missing-function-docstring

import pytest

from fretgrep import assistant, theory

TONES = assistant.Tool("tones", "Töne", "symbol", "Symbol", theory.tones)


def scripted(*replies):
    """Return a transport that answers each request with the next reply."""
    requests = []
    queue = list(replies)

    def send(body):
        requests.append(body)
        reply = queue.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        yield from reply

    return send, requests


def text(*pieces):
    return [{"message": {"content": piece}} for piece in pieces]


def call(name, **arguments):
    return [{"message": {"content": "", "tool_calls": [
        {"function": {"name": name, "arguments": arguments}}
    ]}}]


def test_answer_streams_and_history_grows():
    send, requests = scripted(text("Hal", "lo"), text("Noch", "mal"))
    chat = assistant.Conversation(send, "m", "system", [TONES])
    pieces = []

    assert chat.ask("Hi", pieces.append) == "Hallo"
    assert pieces == ["Hal", "lo"]
    assert chat.ask("Und?", pieces.append) == "Nochmal"
    roles = [message["role"] for message in requests[1]["messages"]]
    assert roles == ["system", "user", "assistant", "user"]
    assert requests[0]["think"] is False and requests[0]["stream"] is True
    assert requests[0]["tools"][0]["function"]["name"] == "tones"


def test_tool_result_goes_back_to_the_model():
    send, requests = scripted(call("tones", symbol="G7HM5"), text("G Ab B C D Eb F"))
    chat = assistant.Conversation(send, "m", "system", [TONES])
    used = []

    answer = chat.ask("G7HM5?", lambda _t: None, on_tool=lambda *a: used.append(a))

    assert answer == "G Ab B C D Eb F"
    assert used == [("tones", "G7HM5")]
    result = requests[1]["messages"][-1]
    assert result["role"] == "tool" and result["tool_name"] == "tones"
    assert "G Ab B C D Eb F" in result["content"]


def test_arguments_as_text_and_unknown_tools():
    as_text = [{"message": {"tool_calls": [
        {"function": {"name": "tones", "arguments": '{"symbol": "C dur"}'}},
        {"function": {"name": "nope", "arguments": {}}},
    ]}}]
    send, requests = scripted(as_text, text("ok"))
    chat = assistant.Conversation(send, "m", "system", [TONES])

    chat.ask("?", lambda _t: None)

    results = [m["content"] for m in requests[1]["messages"] if m["role"] == "tool"]
    assert "C D E F G A B" in results[0]
    assert "Unbekanntes Werkzeug" in results[1]


def test_thinking_is_passed_on():
    send, _ = scripted([{"message": {"thinking": "hm"}}, *text("ja")])
    chat = assistant.Conversation(send, "m", "system", [], think=True)
    thoughts = []
    assert chat.ask("?", lambda _t: None, thoughts.append) == "ja"
    assert thoughts == ["hm"]


def test_failure_leaves_history_unchanged():
    send, _ = scripted(
        [{"error": "model 'x' not found"}], KeyboardInterrupt(), text("gut")
    )
    chat = assistant.Conversation(send, "m", "system", [])

    with pytest.raises(assistant.ChatError, match="not found"):
        chat.ask("eins", lambda _t: None)
    with pytest.raises(KeyboardInterrupt):
        chat.ask("zwei", lambda _t: None)
    assert len(chat.messages) == 1
    assert chat.ask("drei", lambda _t: None) == "gut"


def test_endless_tool_calls_stop():
    send, _ = scripted(*[call("tones", symbol="C")] * assistant.MAX_TOOL_ROUNDS)
    chat = assistant.Conversation(send, "m", "system", [TONES])
    with pytest.raises(assistant.ChatError):
        chat.ask("?", lambda _t: None)
    assert len(chat.messages) == 1


def test_system_prompt_contains_the_glossary():
    prompt = assistant.system_prompt({"hm5": "Harmonisch-Moll-5"})
    assert "tones" in prompt and "- hm5: Harmonisch-Moll-5" in prompt


def test_history_can_be_restored():
    send, requests = scripted(text("zwei"))
    chat = assistant.Conversation(send, "m", "neu", [])
    chat.restore([{"role": "user", "content": "eins"}, "kaputt"])

    chat.ask("noch was", lambda _t: None)

    assert requests[0]["messages"][0] == {"role": "system", "content": "neu"}
    assert [m["content"] for m in chat.history] == ["eins", "noch was", "zwei"]
