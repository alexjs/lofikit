"""Tests for music library module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lofikit import music_library


def test_load_empty_index(tmp_path: Path) -> None:
    """Test loading index from empty directory."""
    result = music_library._load_index(tmp_path)
    assert result == []


def test_save_and_load_index(tmp_path: Path) -> None:
    """Test round-trip save/load of index."""
    index = [{"filename": "test.mp3", "title": "Test", "duration": 120.0}]
    music_library._save_index(tmp_path, index)
    loaded = music_library._load_index(tmp_path)
    assert loaded == index


def test_scan_local(tmp_path: Path) -> None:
    """Test scanning local directory for audio files."""
    music = tmp_path / "music"
    music.mkdir()
    (music / "song.mp3").write_text("fake")

    with patch("lofikit.music_library._probe_duration", return_value=180.0):
        count = music_library.scan_local(music)

    assert count == 1
    index = music_library._load_index(music)
    assert len(index) == 1
    assert index[0]["filename"] == "song.mp3"
    assert index[0]["duration"] == 180.0


def test_scan_local_skips_indexed(tmp_path: Path) -> None:
    """Test scan doesn't re-index existing files."""
    music = tmp_path / "music"
    music.mkdir()
    (music / "song.mp3").write_text("fake")

    index = [{"filename": "song.mp3", "title": "Song", "duration": 180.0}]
    music_library._save_index(music, index)

    with patch("lofikit.music_library._probe_duration") as mock_probe:
        count = music_library.scan_local(music)

    assert count == 0
    mock_probe.assert_not_called()


def test_add_track(tmp_path: Path) -> None:
    """Test adding a track to the library."""
    music = tmp_path / "music"
    music.mkdir()
    source = tmp_path / "new_song.mp3"
    source.write_text("audio data")

    with patch("lofikit.music_library._probe_duration", return_value=240.0):
        entry = music_library.add_track(source, music)

    assert entry["filename"] == "new_song.mp3"
    assert entry["duration"] == 240.0
    assert (music / "new_song.mp3").exists()


def test_add_track_missing_file(tmp_path: Path) -> None:
    """Test adding nonexistent file raises error."""
    with pytest.raises(FileNotFoundError):
        music_library.add_track(tmp_path / "nope.mp3", tmp_path)


def test_list_tracks(tmp_path: Path) -> None:
    """Test listing tracks scans and returns index."""
    music = tmp_path / "music"
    music.mkdir()

    index = [
        {"filename": "a.mp3", "title": "A", "duration": 100.0},
        {"filename": "b.mp3", "title": "B", "duration": 200.0},
    ]
    music_library._save_index(music, index)

    tracks = music_library.list_tracks(music)
    assert len(tracks) == 2


def test_check_ytdlp_missing() -> None:
    """Test check raises when yt-dlp not found."""
    with patch("subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(SystemExit, match="yt-dlp not found"):
            music_library.check_ytdlp()
