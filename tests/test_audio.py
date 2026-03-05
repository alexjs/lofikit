"""Tests for audio module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lofikit import audio


@pytest.fixture
def music_dir(tmp_path: Path) -> Path:
    """Create a temp music dir with an index."""
    music = tmp_path / "music"
    music.mkdir()

    # Create fake audio files
    for name in ["track_a.mp3", "track_b.mp3", "track_c.mp3"]:
        (music / name).write_text("fake")

    index = [
        {"filename": "track_a.mp3", "title": "Track A", "duration": 180.0},
        {"filename": "track_b.mp3", "title": "Track B", "duration": 200.0},
        {"filename": "track_c.mp3", "title": "Track C", "duration": 150.0},
    ]
    (music / "index.json").write_text(json.dumps(index))
    return music


def test_select_tracks_covers_duration(music_dir: Path) -> None:
    """Test track selection covers the target duration."""
    tracks = audio.select_tracks(music_dir, target_duration=300.0, crossfade=4.0)
    assert len(tracks) >= 1
    # All returned paths should exist
    for t in tracks:
        assert t.exists()


def test_select_tracks_single_long_track(music_dir: Path) -> None:
    """Test selection when one track is long enough."""
    tracks = audio.select_tracks(music_dir, target_duration=100.0, crossfade=4.0)
    assert len(tracks) >= 1


def test_select_tracks_empty_dir(tmp_path: Path) -> None:
    """Test selection fails gracefully with no tracks."""
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(SystemExit, match="No music tracks"):
        audio.select_tracks(empty, target_duration=100.0)


def test_select_tracks_excludes(music_dir: Path) -> None:
    """Test that excluded tracks are skipped."""
    tracks = audio.select_tracks(
        music_dir, target_duration=100.0, crossfade=4.0,
        exclude={"track_a.mp3", "track_b.mp3"},
    )
    # Only track_c.mp3 should be available
    assert all(t.name == "track_c.mp3" for t in tracks)


def test_compose_single_track() -> None:
    """Test composing a single track."""
    with patch("lofikit.audio._run") as mock_run:
        result = audio._compose_single(
            Path("track.mp3"), 120.0, 3.0, 3.0, Path("out.m4a")
        )

    cmd = mock_run.call_args[0][0]
    assert "-af" in cmd
    assert "afade" in cmd[cmd.index("-af") + 1]
    assert result == Path("out.m4a")


def test_compose_multiple_tracks() -> None:
    """Test composing multiple tracks with crossfade."""
    tracks = [Path("a.mp3"), Path("b.mp3"), Path("c.mp3")]

    with patch("lofikit.audio._run") as mock_run:
        result = audio._compose_multiple(
            tracks, 300.0, 4.0, 3.0, 3.0, Path("out.m4a")
        )

    cmd = mock_run.call_args[0][0]
    assert "-filter_complex" in cmd
    filter_str = cmd[cmd.index("-filter_complex") + 1]
    assert "acrossfade" in filter_str
    assert result == Path("out.m4a")
