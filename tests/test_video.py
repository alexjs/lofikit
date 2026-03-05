"""Tests for video module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lofikit import video


@pytest.fixture
def probe_output() -> dict:
    """Sample ffprobe JSON output."""
    return {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 3840,
                "height": 2160,
                "r_frame_rate": "30000/1001",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
            },
        ],
        "format": {
            "duration": "120.5",
        },
    }


def test_probe(probe_output: dict) -> None:
    """Test video.probe() parses ffprobe output correctly."""
    mock_result = MagicMock()
    mock_result.stdout = json.dumps(probe_output)

    with patch("lofikit.video._run", return_value=mock_result):
        info = video.probe(Path("test.mp4"))

    assert info["width"] == 3840
    assert info["height"] == 2160
    assert info["duration"] == 120.5
    assert info["codec"] == "h264"
    assert info["fps"] == 29.97
    assert info["audio_codec"] == "aac"


def test_probe_no_audio(probe_output: dict) -> None:
    """Test probe when video has no audio stream."""
    probe_output["streams"] = [probe_output["streams"][0]]
    mock_result = MagicMock()
    mock_result.stdout = json.dumps(probe_output)

    with patch("lofikit.video._run", return_value=mock_result):
        info = video.probe(Path("test.mp4"))

    assert info["audio_codec"] is None


def test_probe_no_video() -> None:
    """Test probe raises when no video stream found."""
    data = {"streams": [{"codec_type": "audio", "codec_name": "aac"}], "format": {"duration": "10"}}
    mock_result = MagicMock()
    mock_result.stdout = json.dumps(data)

    with patch("lofikit.video._run", return_value=mock_result):
        with pytest.raises(ValueError, match="No video stream"):
            video.probe(Path("test.mp4"))


def test_strip_audio() -> None:
    """Test strip_audio calls ffmpeg with correct arguments."""
    with patch("lofikit.video._run") as mock_run:
        result = video.strip_audio(Path("in.mp4"), Path("out.mp4"))

    cmd = mock_run.call_args[0][0]
    assert "ffmpeg" in cmd[0]
    assert "-map" in cmd
    assert "0:v" in cmd
    assert "-c:v" in cmd
    assert "copy" in cmd
    assert result == Path("out.mp4")


def test_mux() -> None:
    """Test mux calls ffmpeg with correct arguments."""
    with patch("lofikit.video._run") as mock_run:
        result = video.mux(Path("video.mp4"), Path("audio.m4a"), Path("final.mp4"))

    cmd = mock_run.call_args[0][0]
    assert "-movflags" in cmd
    assert "+faststart" in cmd
    assert result == Path("final.mp4")


def test_check_ffmpeg_missing() -> None:
    """Test check_ffmpeg raises when ffmpeg not found."""
    with patch("subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(SystemExit, match="ffmpeg not found"):
            video.check_ffmpeg()
