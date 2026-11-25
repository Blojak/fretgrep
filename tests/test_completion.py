"""Tests for the tab completion scripts."""
# pylint: disable=missing-function-docstring

import shutil
import subprocess

import pytest

from fretgrep import cli, completion


def test_tree_knows_commands_switches_and_values():
    nodes = completion.tree(cli._build_parser())  # pylint: disable=protected-access

    assert ("search", "Aufnahmen suchen") in nodes[""].commands
    assert [name for name, _ in nodes["db"].commands] == ["upgrade"]
    assert "db upgrade" in nodes
    assert "--show" in dict(nodes["notes"].options)
    assert nodes["notes"].values["--sheet"] == completion.FILES
    assert nodes["notes"].values["--library"] == completion.DIRS
    assert nodes["search"].values["-n"] == completion.NOTHING
    assert "--play" not in nodes["search"].values
    assert nodes["scan"].positional == completion.DIRS
    assert nodes["completion"].positional == ["zsh", "bash"]
    assert nodes["playlist show"].positional == completion.PLAYLISTS
    assert nodes["search"].values["--save"] == completion.PLAYLISTS
    assert "--names" not in dict(nodes["playlist"].options)


def test_command_prints_script(capsys):
    assert cli.main(["completion", "zsh"]) == cli.EXIT_OK
    script = capsys.readouterr().out
    assert script.startswith("#compdef fretgrep\n")
    assert "'search:Aufnahmen suchen'" in script


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not installed")
def test_bash_completes_commands_switches_and_choices():
    script = completion.bash(cli._build_parser())  # pylint: disable=protected-access
    probe = """
t() { COMP_WORDS=("$@"); COMP_CWORD=$(( ${#COMP_WORDS[@]} - 1 )); COMPREPLY=()
      _fretgrep; echo "${COMPREPLY[*]}"; }
t fretgrep se
t fretgrep db u
t fretgrep notes 21 --sh
t fretgrep completion ''
t fretgrep search -n ''
"""
    done = subprocess.run(
        ["bash", "-c", script + probe], capture_output=True, text=True, check=True
    )
    assert done.stdout.splitlines() == [
        "search", "upgrade", "--sheet --show", "zsh bash", ""
    ]


@pytest.mark.parametrize("shell", completion.SHELLS)
def test_script_is_valid_shell(shell):
    if shutil.which(shell) is None:
        pytest.skip(f"{shell} is not installed")
    script = completion.script(cli._build_parser(), shell)  # pylint: disable=protected-access
    subprocess.run([shell, "-n"], input=script, text=True, check=True)


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not installed")
def test_bash_completes_playlist_names(tmp_path):
    script = completion.bash(cli._build_parser())  # pylint: disable=protected-access
    probe = """
fretgrep() { printf '%s\\n' 'HM5 üben' andere 'HM5 langsam' '$(touch pwned)'; }
t() { COMP_WORDS=("$@"); COMP_CWORD=$(( ${#COMP_WORDS[@]} - 1 )); COMPREPLY=()
      _fretgrep; printf '%s|' "${COMPREPLY[@]}"; echo; }
t fretgrep playlist show ''
t fretgrep playlist play HM5
t fretgrep playlist add '"HM5 l'
t fretgrep search blues --save a
t fretgrep playlist ''
"""
    done = subprocess.run(
        ["bash", "-c", script + probe],
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )
    lines = done.stdout.splitlines()
    assert not (tmp_path / "pwned").exists()
    assert lines[:4] == [
        "HM5 üben|andere|HM5 langsam|$(touch pwned)|",
        "HM5 üben|HM5 langsam|",
        "HM5 langsam|",
        "andere|",
    ]
    assert "export|" in lines[4] and "HM5" not in lines[4]
