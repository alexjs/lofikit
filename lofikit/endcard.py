"""End card generation and appending to video."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from . import run_cmd as _run

log = logging.getLogger(__name__)

# Default end card location relative to package
DEFAULT_ENDCARD = Path(__file__).parent.parent / "assets" / "endcard.png"


def generate_placeholder(output_path: Path, width: int = 3840, height: int = 2160) -> Path:
    """Generate a placeholder end card image with Pillow."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (width, height), color=(20, 20, 25))
    draw = ImageDraw.Draw(img)

    # Try to use a decent font, fall back to default
    font_large = None
    font_small = None
    try:
        font_large = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 120)
        font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 60)
    except (OSError, IOError):
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Draw centered text
    title = "Thanks for watching"
    subtitle = "Subscribe for more"

    bbox = draw.textbbox((0, 0), title, font=font_large)
    tw = bbox[2] - bbox[0]
    draw.text(
        ((width - tw) / 2, height / 2 - 120),
        title,
        fill=(220, 220, 220),
        font=font_large,
    )

    bbox = draw.textbbox((0, 0), subtitle, font=font_small)
    sw = bbox[2] - bbox[0]
    draw.text(
        ((width - sw) / 2, height / 2 + 40),
        subtitle,
        fill=(160, 160, 170),
        font=font_small,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)
    log.info("Generated placeholder end card at %s", output_path)
    return output_path


def append_endcard(
    video_path: Path,
    endcard_image: Path,
    output_path: Path,
    width: int,
    height: int,
    fps: float,
    codec: str = "h264",
    rotation: int = 0,
    duration: float = 20.0,
    fade_duration: float = 2.0,
    temp_dir: Path | None = None,
) -> Path:
    """Append an end card to video with crossfade from last frame.

    Strategy (avoids decoding the entire video):
      1. Stream-copy the main body (everything except last fade_duration) — fast
      2. Extract just the tail clip (last few seconds) — tiny re-encode
      3. xfade the short tail with the endcard image — tiny re-encode
      4. Join via MPEG-TS concat (handles HEVC SPS differences between
         camera and libx265), then remux to MP4 with display_rotation
         to restore the rotation metadata lost in the TS roundtrip.
    """
    import tempfile

    video_duration = _get_duration(video_path)
    split_point = video_duration - fade_duration

    if temp_dir is None:
        temp_dir = Path(tempfile.mkdtemp(prefix="lofikit_endcard_"))

    main_body = temp_dir / "main_body.mp4"
    tail_clip = temp_dir / "tail_clip.mp4"
    endcard_segment = temp_dir / "endcard_segment.mp4"
    main_ts = temp_dir / "main_body.ts"
    endcard_ts = temp_dir / "endcard_segment.ts"

    fps_int = int(fps)

    # Step 1: Stream-copy the main body (fast, no re-encode)
    # -map 0:v strips any data streams (e.g. DJI timecode) so the concat
    # sees matching stream counts in both files.
    log.debug("Splitting video at %.2fs (codec=%s)", split_point, codec)
    _run([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-t", str(split_point),
        "-map", "0:v",
        "-c:v", "copy",
        str(main_body),
    ])

    # Pick encoder to match source codec
    if codec in ("hevc", "h265"):
        encoder = "libx265"
        crf = "22"
    else:
        encoder = "libx264"
        crf = "18"

    # Step 2: Extract + re-encode only the tail clip (a few seconds)
    _run([
        "ffmpeg", "-y",
        "-ss", str(split_point),
        "-i", str(video_path),
        "-c:v", encoder, "-crf", crf, "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-r", str(fps_int),
        "-an",
        str(tail_clip),
    ])

    # Step 3: xfade only the short tail clip with the endcard image
    # Both inputs are normalized to matching fps, pixel format, and timebase
    tail_duration = _get_duration(tail_clip)
    xfade_offset = max(tail_duration - fade_duration, 0)

    filter_complex = (
        f"[0:v]fps={fps_int},format=yuv420p,settb=1/{fps_int}[main];"
        f"[1:v]loop=loop=-1:size=1:start=0,"
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"setsar=1,fps={fps_int},format=yuv420p,"
        f"settb=1/{fps_int},trim=duration={duration}[endcard];"
        f"[main][endcard]xfade=transition=fade:duration={fade_duration}:offset={xfade_offset}[outv]"
    )
    _run([
        "ffmpeg", "-y",
        "-i", str(tail_clip),
        "-i", str(endcard_image),
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-c:v", encoder, "-crf", crf, "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-r", str(fps_int),
        "-an",
        str(endcard_segment),
    ])

    # Step 4: Join via MPEG-TS intermediates then remux to MP4
    # MPEG-TS carries HEVC parameter sets inline per segment, so the
    # decoder reinitialises at the boundary (no grey frames).
    # Rotation is restored via -display_rotation on the final remux.
    _run([
        "ffmpeg", "-y",
        "-i", str(main_body),
        "-map", "0:v",
        "-c:v", "copy",
        "-f", "mpegts",
        str(main_ts),
    ])

    _run([
        "ffmpeg", "-y",
        "-i", str(endcard_segment),
        "-c:v", "copy",
        "-f", "mpegts",
        str(endcard_ts),
    ])

    # Remux TS concat to MP4, restoring rotation via display_rotation
    # (MPEG-TS doesn't carry MP4 display matrices)
    rotation_args: list[str] = []
    if rotation:
        rotation_args = ["-display_rotation:v", str(-rotation)]

    _run([
        "ffmpeg", "-y",
        *rotation_args,
        "-i", f"concat:{main_ts}|{endcard_ts}",
        "-c", "copy",
        "-an",
        str(output_path),
    ])

    return output_path


def _get_duration(path: Path) -> float:
    """Get duration of a video file."""
    import json as _json

    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(path),
    ]
    result = _run(cmd)
    data = _json.loads(result.stdout)
    return float(data["format"]["duration"])
