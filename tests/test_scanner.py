"""Tests for reading a library folder into the database."""
# pylint: disable=missing-function-docstring

import os
import shutil
import subprocess

import pytest
from sqlalchemy import select

from fretgrep import scanner
from fretgrep.models import AutoFile, AutoTag, Recording
from fretgrep.scanner import scan_library


def write(library, rel_path, content):
    path = library / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def recordings(session):
    return session.scalars(select(Recording).order_by(Recording.id)).all()


def test_new_files_are_stored_with_tags(session, library):
    write(library, "251/minor/dm7b5 chet baker.mp3", b"one")
    write(library, "notes.txt", b"ignored")

    summary = scan_library(session, library)

    assert (summary.new, summary.updated, summary.unchanged) == (1, 0, 0)
    (recording,) = recordings(session)
    assert len(recording.content_hash) == 64
    assert recording.file.rel_path == "251/minor/dm7b5 chet baker.mp3"
    assert recording.file.filename_norm == "dm7b5 chet baker"
    assert recording.file.size_bytes == 3
    assert not recording.file.missing
    assert ("source", "chet baker") in {
        (tag.category, tag.value) for tag in recording.tags
    }


def test_rescan_is_unchanged_and_does_not_rehash(session, library, monkeypatch):
    write(library, "a.mp3", b"one")
    scan_library(session, library)
    monkeypatch.setattr(scanner, "hash_file", pytest.fail)

    summary = scan_library(session, library)

    assert (summary.new, summary.updated, summary.unchanged) == (0, 0, 1)


def test_renamed_file_keeps_its_id(session, library):
    path = write(library, "251 moll 1.mp3", b"one")
    scan_library(session, library)
    (before,) = recordings(session)
    recording_id = before.id

    path.rename(library / "251 dur wes.mp3")
    summary = scan_library(session, library)

    assert (summary.new, summary.updated, summary.missing) == (0, 1, 0)
    (after,) = recordings(session)
    assert after.id == recording_id
    assert after.file.rel_path == "251 dur wes.mp3"
    values = {(tag.category, tag.value) for tag in after.tags}
    assert ("tonality", "major") in values
    assert ("tonality", "minor") not in values
    assert session.scalar(select(AutoTag).where(AutoTag.value == "minor")) is None


def test_changed_content_is_a_new_recording(session, library):
    path = write(library, "a.mp3", b"one")
    scan_library(session, library)
    path.write_bytes(b"other content")

    summary = scan_library(session, library)

    assert (summary.new, summary.missing) == (1, 1)
    old, new = recordings(session)
    assert old.file.missing
    assert not new.file.missing


def test_duplicate_content_is_reported_once(session, library):
    write(library, "a.mp3", b"same")
    write(library, "b.mp3", b"same")

    summary = scan_library(session, library)

    assert summary.new == 1
    assert summary.duplicates == [("b.mp3", "a.mp3")]
    assert len(recordings(session)) == 1


def test_missing_file_is_flagged_and_comes_back(session, library):
    path = write(library, "a.mp3", b"one")
    scan_library(session, library)
    path.unlink()

    assert scan_library(session, library).missing == 1
    (recording,) = recordings(session)
    assert recording.file.missing

    write(library, "sub/a.mp3", b"one")
    summary = scan_library(session, library)

    assert (summary.updated, summary.missing) == (1, 0)
    assert session.scalars(select(AutoFile)).one().rel_path == "sub/a.mp3"


def test_broken_audio_is_stored_without_audio_info(session, library):
    write(library, "a.mp3", b"this is not an mp3 file")

    summary = scan_library(session, library)

    assert (summary.new, summary.errors) == (1, [])
    assert recordings(session)[0].file.duration_s is None


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read any file")
def test_unreadable_file_is_reported(session, library):
    write(library, "a.mp3", b"one").chmod(0)

    summary = scan_library(session, library)

    assert summary.new == 0
    assert [rel_path for rel_path, _ in summary.errors] == ["a.mp3"]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_audio_info_of_real_mp3(session, library):
    target = library / "tone.mp3"
    command = [
        "ffmpeg", "-loglevel", "error", "-f", "lavfi",
        "-i", "sine=frequency=440:duration=2",
        "-ac", "1", "-ar", "44100", "-b:a", "64k", str(target),
    ]
    if subprocess.run(command, check=False).returncode != 0:
        pytest.skip("ffmpeg cannot encode mp3")

    scan_library(session, library)

    file = recordings(session)[0].file
    assert file.duration_s == pytest.approx(2.0, abs=0.2)
    assert (file.sample_rate, file.channels) == (44100, 1)
    assert file.bitrate == pytest.approx(64000, rel=0.01)
