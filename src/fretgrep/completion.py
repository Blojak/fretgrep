"""Tab completion for zsh and bash, generated from the argument parser.

The scripts are static: they contain every command and switch, so a
press of Tab does not start Python. They are generated from the parser
itself and therefore never fall behind the commands. Only the names of
the playlists live in the database; for them the script asks
``fretgrep playlist --names``.
"""
# argparse offers no public way to walk its sub-commands.
# pylint: disable=protected-access

import argparse
from dataclasses import dataclass, field

SHELLS = ("zsh", "bash")

# What the value of an argument is, judged by its metavar.
DIRS = "dirs"
FILES = "files"
PLAYLISTS = "playlists"
NOTHING = ""
_KINDS = {"ORDNER": DIRS, "DATEI": FILES, "LISTE": PLAYLISTS}


@dataclass
class Node:
    """What can follow one command, e.g. ``fretgrep db``."""

    commands: list[tuple[str, str]] = field(default_factory=list)
    options: list[tuple[str, str]] = field(default_factory=list)
    # switch -> kind of its value, for switches that take one
    values: dict[str, str] = field(default_factory=dict)
    # kind of the first free argument, or the words it can be
    positional: str | list[str] = NOTHING


def _kind(action: argparse.Action) -> str | list[str]:
    if action.choices and not isinstance(action, argparse._SubParsersAction):
        return [str(choice) for choice in action.choices]
    return _KINDS.get(str(action.metavar), NOTHING)


def tree(parser: argparse.ArgumentParser, path: str = "") -> dict[str, Node]:
    """Return what can follow each command; the key is the command path."""
    node, nodes = Node(), {}
    for action in parser._actions:
        if action.help == argparse.SUPPRESS:
            continue
        if isinstance(action, argparse._SubParsersAction):
            helps = {choice.dest: choice.help for choice in action._choices_actions}
            for name, child in action.choices.items():
                node.commands.append((name, helps.get(name) or ""))
                nodes |= tree(child, f"{path} {name}".strip())
        elif action.option_strings:
            for flag in action.option_strings:
                node.options.append((flag, action.help or ""))
                if action.nargs != 0:
                    node.values[flag] = _kind(action)
        elif not node.positional:
            node.positional = _kind(action)
    return {path: node, **nodes}


def _quote(text: str) -> str:
    """Quote for both shells, in single quotes."""
    return "'" + text.replace("'", "'\\''") + "'"


def _describe(name: str, text: str) -> str:
    """Return a zsh ``_describe`` entry, "name:description"."""
    return _quote(name.replace(":", "\\:") + ":" + text)


def _command_steps(nodes: dict[str, Node]) -> list[str]:
    """Return case patterns that move from one command to its sub-command."""
    return [
        f'({_quote(f"{path}|{name}")}) key={_quote(f"{path} {name}".strip())} ;;'
        for path, node in nodes.items()
        for name, _help in node.commands
    ]


def _value_patterns(nodes: dict[str, Node], kind: str) -> str:
    patterns = [
        _quote(f"{path}|{flag}")
        for path, node in nodes.items()
        for flag, value in node.values.items()
        if value == kind
    ]
    return "|".join(patterns)


def _choice_values(nodes: dict[str, Node]) -> list[tuple[str, list[str]]]:
    return [
        (f"{path}|{flag}", value)
        for path, node in nodes.items()
        for flag, value in node.values.items()
        if isinstance(value, list)
    ]


def _cases(lines: list[str], indent: str = "    ") -> str:
    return "\n".join(indent + line for line in lines)


def zsh(parser: argparse.ArgumentParser) -> str:
    """Return the completion script for zsh."""
    nodes = tree(parser)
    name = parser.prog
    value_cases = []
    for kind, call in (
        (DIRS, "_files -/"),
        (FILES, "_files"),
        (PLAYLISTS, f"_{name}_playlists"),
    ):
        if patterns := _value_patterns(nodes, kind):
            value_cases.append(f"({patterns}) {call}; return ;;")
    for pattern, words in _choice_values(nodes):
        choices = " ".join(words)
        value_cases.append(f"({_quote(pattern)}) compadd -- {choices}; return ;;")
    if patterns := _value_patterns(nodes, NOTHING):
        value_cases.append(f"({patterns}) return ;;")
    node_cases = []
    for path, node in nodes.items():
        body = []
        if node.commands:
            entries = " ".join(_describe(*command) for command in node.commands)
            body.append(f"commands=({entries})")
        entries = " ".join(_describe(*option) for option in node.options)
        body.append(f"options=({entries})")
        if isinstance(node.positional, list):
            body.append(f"words_=({' '.join(map(_quote, node.positional))})")
        elif node.positional:
            body.append(f"positional={node.positional}")
        node_cases.append(f"({_quote(path)})\n      " + "\n      ".join(body) + " ;;")
    return f"""#compdef {name}
# Tab completion for {name}; generated by '{name} completion zsh'.

_{name}_playlists() {{
  local -a names
  names=(${{(f)"$({name} playlist --names 2>/dev/null)"}})
  compadd -a names
}}

_{name}() {{
  local key="" prev=${{words[CURRENT-1]}} positional="" i
  local -a commands options words_
  for (( i = 2; i < CURRENT; i++ )); do
    case "$key|${{words[i]}}" in
{_cases(_command_steps(nodes), "      ")}
    esac
  done
  case "$key|$prev" in
{_cases(value_cases)}
  esac
  case $key in
{_cases(node_cases)}
  esac
  if [[ $PREFIX == -* ]]; then
    _describe -t options Schalter options
  elif (( $#commands )); then
    _describe -t commands Befehl commands
  elif (( $#words_ )); then
    compadd -- $words_
  elif [[ $positional == {DIRS} ]]; then
    _files -/
  elif [[ $positional == {FILES} ]]; then
    _files
  elif [[ $positional == {PLAYLISTS} ]]; then
    _{name}_playlists
  fi
}}

if [[ $zsh_eval_context[-1] == loadautofunc ]]; then
  _{name} "$@"
else
  compdef _{name} {name}
fi
"""


def bash(parser: argparse.ArgumentParser) -> str:
    """Return the completion script for bash."""
    nodes = tree(parser)
    name = parser.prog
    value_cases = []
    for kind, flag in ((DIRS, "-d"), (FILES, "-f")):
        if patterns := _value_patterns(nodes, kind):
            value_cases.append(
                f'({patterns}) COMPREPLY=($(compgen {flag} -- "$cur")); return ;;'
            )
    if patterns := _value_patterns(nodes, PLAYLISTS):
        value_cases.append(f"({patterns}) _{name}_playlists; return ;;")
    for pattern, words in _choice_values(nodes):
        value_cases.append(
            f"({_quote(pattern)}) COMPREPLY=($(compgen -W "
            f'{_quote(" ".join(words))} -- "$cur")); return ;;'
        )
    if patterns := _value_patterns(nodes, NOTHING):
        value_cases.append(f"({patterns}) return ;;")
    node_cases = []
    for path, node in nodes.items():
        body = [
            f"commands={_quote(' '.join(command for command, _ in node.commands))}",
            f"options={_quote(' '.join(option for option, _ in node.options))}",
        ]
        if isinstance(node.positional, list):
            body.append(f"words={_quote(' '.join(node.positional))}")
        elif node.positional:
            body.append(f"positional={node.positional}")
        node_cases.append(f"({_quote(path)}) " + "; ".join(body) + " ;;")
    return f"""# Tab completion for {name}; generated by '{name} completion bash'.

# One name per line; -o filenames escapes spaces. No compgen -W: it would
# expand $(...) in a name.
_{name}_playlists() {{
  local word=${{cur//\\\\/}} name
  word=${{word#\\\"}} word=${{word#\\\'}}
  COMPREPLY=()
  while IFS= read -r name; do
    [[ $name == "$word"* ]] && COMPREPLY+=("$name")
  done < <({name} playlist --names 2>/dev/null)
}}

_{name}() {{
  local cur=${{COMP_WORDS[COMP_CWORD]}} prev=${{COMP_WORDS[COMP_CWORD-1]}}
  local key="" commands="" options="" words="" positional="" i
  for (( i = 1; i < COMP_CWORD; i++ )); do
    case "$key|${{COMP_WORDS[i]}}" in
{_cases(_command_steps(nodes), "      ")}
    esac
  done
  case "$key|$prev" in
{_cases(value_cases)}
  esac
  case $key in
{_cases(node_cases)}
  esac
  if [[ $cur == -* ]]; then
    COMPREPLY=($(compgen -W "$options" -- "$cur"))
  elif [[ -n $commands ]]; then
    COMPREPLY=($(compgen -W "$commands" -- "$cur"))
  elif [[ -n $words ]]; then
    COMPREPLY=($(compgen -W "$words" -- "$cur"))
  elif [[ $positional == {DIRS} ]]; then
    COMPREPLY=($(compgen -d -- "$cur"))
  elif [[ $positional == {FILES} ]]; then
    COMPREPLY=($(compgen -f -- "$cur"))
  elif [[ $positional == {PLAYLISTS} ]]; then
    _{name}_playlists
  fi
}}

complete -o filenames -F _{name} {name}
"""


def script(parser: argparse.ArgumentParser, shell: str) -> str:
    """Return the completion script for one of ``SHELLS``."""
    return {"zsh": zsh, "bash": bash}[shell](parser)
