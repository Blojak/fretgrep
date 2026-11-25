"""Terminal output of the assistant's answers while they stream in."""

import os
import sys


class ChatOutput:
    """Write an answer as it streams in; thinking and tool calls dimmed."""

    def __init__(self) -> None:
        self.terminal = sys.stdout.isatty()
        color = self.terminal and "NO_COLOR" not in os.environ
        self.dim, self.reset = ("\033[2m", "\033[0m") if color else ("", "")
        self.kind = ""
        self.waiting = False

    def wait(self) -> None:
        """Show that the model is working, until its first word arrives."""
        if self.terminal:
            self._write(f"{self.dim}… das Modell antwortet{self.reset}")
            self.waiting = True

    def _write(self, text: str) -> None:
        if self.waiting:
            text = "\r\033[K" + text
            self.waiting = False
        sys.stdout.write(text)
        sys.stdout.flush()

    def _switch(self, kind: str) -> None:
        """Start a new paragraph when thinking, tools and text alternate."""
        if self.kind and self.kind != kind:
            self._write("\n\n")
        self.kind = kind

    def text(self, chunk: str) -> None:
        """Write a piece of the answer."""
        self._switch("text")
        self._write(chunk)

    def thinking(self, chunk: str) -> None:
        """Write a piece of the model's thinking, dimmed."""
        self._switch("thinking")
        self._write(f"{self.dim}{chunk}{self.reset}")

    def tool(self, name: str, argument: str) -> None:
        """Note a tool call on a line of its own, then wait again."""
        if self.kind:
            self._write("\n\n")
        self._write(f"{self.dim}→ {name}: {argument}{self.reset}\n")
        self.kind = ""
        self.wait()

    def end(self) -> None:
        """Finish the answer; remove the note that the model is working."""
        self._write("\n" if self.kind else "")
