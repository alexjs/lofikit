"""Tests for the render pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_render_file_not_found() -> None:
    """Test render raises when input file doesn't exist."""
    from lofikit import pipeline

    with patch("lofikit.pipeline.video.check_ffmpeg"):
        with pytest.raises(FileNotFoundError, match="Input video not found"):
            pipeline.render(Path("/nonexistent/video.mp4"))


def test_render_calls_pipeline_steps(tmp_path: Path) -> None:
    """Test render orchestrates all pipeline steps."""
    input_file = tmp_path / "input.mp4"
    input_file.write_text("fake video")
    output_file = tmp_path / "output.mp4"
    music_dir = tmp_path / "music"
    music_dir.mkdir()

    # Create a fake track
    track = music_dir / "song.mp3"
    track.write_text("fake audio")
    import json
    (music_dir / "index.json").write_text(json.dumps([
        {"filename": "song.mp3", "title": "Song", "duration": 300.0}
    ]))

    # Create fake endcard
    endcard = tmp_path / "endcard.png"
    endcard.write_text("fake image")

    probe_data = {
        "duration": 120.0,
        "width": 1920,
        "height": 1080,
        "codec": "h264",
        "fps": 30.0,
        "audio_codec": "aac",
        "path": input_file,
    }

    with (
        patch("lofikit.pipeline.video.check_ffmpeg"),
        patch("lofikit.pipeline.video.probe", return_value=probe_data),
        patch("lofikit.pipeline.video.strip_audio") as mock_strip,
        patch("lofikit.pipeline.endcard.append_endcard") as mock_endcard,
        patch("lofikit.pipeline.audio.compose_audio") as mock_compose,
        patch("lofikit.pipeline.video.mux") as mock_mux,
    ):
        # Make mux create the output file so stat() works
        def create_output(*args, **kwargs):
            output_file.write_text("final video")
            return output_file
        mock_mux.side_effect = create_output

        # strip_audio needs to return a path
        mock_strip.return_value = tmp_path / "silent.mp4"
        mock_endcard.return_value = tmp_path / "with_endcard.mp4"
        mock_compose.return_value = tmp_path / "audio.m4a"

        from lofikit import pipeline
        result = pipeline.render(
            input_path=input_file,
            output_path=output_file,
            music_dir=music_dir,
            endcard_path=endcard,
        )

    assert result == output_file
    mock_strip.assert_called_once()
    mock_endcard.assert_called_once()
    mock_compose.assert_called_once()
    mock_mux.assert_called_once()
