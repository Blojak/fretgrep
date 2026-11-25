"""Tests for the mpv command line; mpv itself is never started."""
# pylint: disable=missing-function-docstring

from pathlib import Path

import pytest

from fretgrep import player


def test_plain_command():
    assert player.build_command(Path("/tmp/x/liste.m3u")) == [
        "mpv",
        "--no-audio-display",
        "--speed=1",
        "--af=rubberband=pitch-scale=1.000000",
        "--term-playing-msg=Spielt: ${media-title}",
        "--playlist=/tmp/x/liste.m3u",
    ]


def test_speed_pitch_and_loop():
    command = player.build_command(
        Path("liste.m3u"), speed=0.7, semitones=-12, loop=(5, 12.5)
    )

    assert "--speed=0.7" in command
    assert "--af=rubberband=pitch-scale=0.500000" in command
    assert command[-3:] == ["--ab-loop-a=5", "--ab-loop-b=12.5", "--playlist=liste.m3u"]


def test_pitch_scale():
    assert player.pitch_scale(0) == 1
    assert player.pitch_scale(12) == 2
    assert player.pitch_scale(2) == pytest.approx(1.122462, abs=1e-6)


def test_parse_loop():
    assert player.parse_loop("5-12.5") == (5.0, 12.5)
    assert player.parse_loop("0-3") == (0.0, 3.0)


@pytest.mark.parametrize("text", ["5", "5-", "-5", "12-5", "5-5", "a-b", ""])
def test_parse_loop_rejects_nonsense(text):
    with pytest.raises(ValueError):
        player.parse_loop(text)


def test_missing_player(monkeypatch):
    monkeypatch.setattr(player, "PLAYER", "mpv-gibt-es-nicht")

    with pytest.raises(player.PlayerMissingError):
        player.play_files([(Path("a.mp3"), "a")])


def test_play_files_hands_titles_to_mpv(monkeypatch, tmp_path):
    seen = []

    def play(command):
        playlist = Path(command[-1].removeprefix("--playlist="))
        seen.append(playlist.read_text(encoding="utf-8"))
        return 0

    monkeypatch.setattr(player, "play", play)
    files = [(tmp_path / "a b.mp3", "ID 3  a b.mp3"), (tmp_path / "-x.mp3", "ID 9\nx")]

    assert player.play_files(files, speed=0.7) == 0
    assert seen == [
        "#EXTM3U\n"
        f"#EXTINF:-1,ID 3  a b.mp3\n{tmp_path}/a b.mp3\n"
        f"#EXTINF:-1,ID 9 x\n{tmp_path}/-x.mp3\n"
    ]
