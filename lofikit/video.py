"""FFmpeg video operations: probe, strip audio, mux."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from . import run_cmd as _run

log = logging.getLogger(__name__)


def check_ffmpeg() -> None:
    """Verify FFmpeg and FFprobe are available."""
    for tool in ("ffmpeg", "ffprobe"):
        try:
            subprocess.run(
                [tool, "-version"], capture_output=True, text=True, check=True
            )
        except FileNotFoundError:
            raise SystemExit(
                f"{tool} not found. Install with: brew install ffmpeg"
            )


def probe(path: Path) -> dict[str, Any]:
    """Probe a video file and return metadata.

    Returns dict with keys: duration, width, height, codec, fps, audio_codec.
    """
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    result = _run(cmd)
    data = json.loads(result.stdout)

    video_stream = next(
        (s for s in data.get("streams", []) if s["codec_type"] == "video"),
        None,
    )
    audio_stream = next(
        (s for s in data.get("streams", []) if s["codec_type"] == "audio"),
        None,
    )

    if video_stream is None:
        raise ValueError(f"No video stream found in {path}")

    # Parse frame rate from r_frame_rate (e.g. "30000/1001")
    fps_str = video_stream.get("r_frame_rate", "30/1")
    num, den = fps_str.split("/")
    fps = round(int(num) / int(den), 2)

    # Extract rotation from side_data_list display matrix
    rotation = 0
    for side_data in video_stream.get("side_data_list", []):
        if "rotation" in side_data:
            rotation = int(float(side_data["rotation"]))
            break

    return {
        "duration": float(data["format"]["duration"]),
        "width": int(video_stream["width"]),
        "height": int(video_stream["height"]),
        "codec": video_stream["codec_name"],
        "fps": fps,
        "rotation": rotation,
        "audio_codec": audio_stream["codec_name"] if audio_stream else None,
        "path": path,
    }


def strip_audio(input_path: Path, output_path: Path) -> Path:
    """Remux video without audio or data streams (stream copy, fast)."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-map", "0:v",
        "-c:v", "copy",
        str(output_path),
    ]
    _run(cmd)
    return output_path


def mux(video_path: Path, audio_path: Path, output_path: Path) -> Path:
    """Combine video and audio into final MP4 with faststart."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(output_path),
    ]
    _run(cmd)
    return output_path
