"""Audio selection and composition: pick tracks, crossfade, apply fades."""

from __future__ import annotations

import json
import logging
import random
import subprocess
from pathlib import Path
from typing import Any

from . import run_cmd as _run

log = logging.getLogger(__name__)


def probe_audio(path: Path) -> float:
    """Return the duration of an audio file in seconds."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(path),
    ]
    result = _run(cmd)
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def select_tracks(
    music_dir: Path,
    target_duration: float,
    crossfade: float = 4.0,
    exclude: set[str] | None = None,
) -> list[Path]:
    """Pick random tracks from cache to cover target duration.

    Accounts for crossfade overlap when calculating total needed duration.
    Tracks whose filenames appear in *exclude* are skipped.
    """
    index_path = music_dir / "index.json"
    if index_path.exists():
        with open(index_path) as f:
            index = json.load(f)
        available = [
            (music_dir / entry["filename"], entry["duration"])
            for entry in index
            if (music_dir / entry["filename"]).exists()
        ]
    else:
        # Fallback: scan for audio files and probe durations
        available = []
        for ext in ("*.mp3", "*.wav", "*.m4a", "*.ogg", "*.flac"):
            for p in music_dir.glob(ext):
                try:
                    dur = probe_audio(p)
                    available.append((p, dur))
                except Exception:
                    log.warning("Could not probe %s, skipping", p)

    if exclude:
        before = len(available)
        available = [(p, d) for p, d in available if p.name not in exclude]
        skipped = before - len(available)
        if skipped:
            log.info("Excluded %d previously-used tracks", skipped)

    if not available:
        raise SystemExit(
            f"No music tracks found in {music_dir}. "
            "Add .mp3/.wav files or run: lofikit library sync"
        )

    random.shuffle(available)

    selected: list[Path] = []
    total = 0.0

    for path, duration in available:
        selected.append(path)
        if selected:
            # Each track after the first overlaps by crossfade seconds
            total += duration - (crossfade if len(selected) > 1 else 0)
        if total >= target_duration:
            break

    # If we've exhausted tracks but still short, loop the selection
    while total < target_duration and available:
        random.shuffle(available)
        for path, duration in available:
            selected.append(path)
            total += duration - crossfade
            if total >= target_duration:
                break

    log.info(
        "Selected %d tracks covering %.1fs (target: %.1fs)",
        len(selected), total, target_duration,
    )
    return selected


def compose_audio(
    tracks: list[Path],
    target_duration: float,
    crossfade: float = 4.0,
    fade_in: float = 3.0,
    fade_out: float = 3.0,
    output_path: Path = Path("composed_audio.m4a"),
) -> Path:
    """Crossfade tracks together, apply fade in/out, output single audio file.

    Uses FFmpeg filter_complex to:
    - Crossfade between consecutive tracks
    - Apply fade in at the start
    - Apply fade out at the end
    - Trim to target_duration
    """
    if len(tracks) == 1:
        return _compose_single(tracks[0], target_duration, fade_in, fade_out, output_path)

    return _compose_multiple(tracks, target_duration, crossfade, fade_in, fade_out, output_path)


def _compose_single(
    track: Path,
    target_duration: float,
    fade_in: float,
    fade_out: float,
    output_path: Path,
) -> Path:
    """Handle the simple case of a single track."""
    fade_out_start = target_duration - fade_out
    filter_str = (
        f"afade=t=in:st=0:d={fade_in},"
        f"afade=t=out:st={fade_out_start}:d={fade_out},"
        f"atrim=0:{target_duration}"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(track),
        "-af", filter_str,
        "-c:a", "aac",
        "-b:a", "192k",
        str(output_path),
    ]
    _run(cmd)
    return output_path


def _compose_multiple(
    tracks: list[Path],
    target_duration: float,
    crossfade: float,
    fade_in: float,
    fade_out: float,
    output_path: Path,
) -> Path:
    """Crossfade multiple tracks using FFmpeg filter_complex."""
    inputs: list[str] = []
    for t in tracks:
        inputs.extend(["-i", str(t)])

    # Build crossfade chain
    # [0:a][1:a] acrossfade=d=4 [a01]; [a01][2:a] acrossfade=d=4 [a012]; ...
    filter_parts: list[str] = []
    n = len(tracks)

    if n == 2:
        # Simple two-track crossfade
        filter_parts.append(
            f"[0:a][1:a]acrossfade=d={crossfade}:c1=tri:c2=tri[mixed]"
        )
        last_label = "mixed"
    else:
        # Chain crossfades for 3+ tracks
        filter_parts.append(
            f"[0:a][1:a]acrossfade=d={crossfade}:c1=tri:c2=tri[a01]"
        )
        last_label = "a01"
        for i in range(2, n):
            new_label = f"a{i:02d}"
            filter_parts.append(
                f"[{last_label}][{i}:a]acrossfade=d={crossfade}:c1=tri:c2=tri[{new_label}]"
            )
            last_label = new_label

    # Apply fade in, fade out, and trim
    fade_out_start = target_duration - fade_out
    filter_parts.append(
        f"[{last_label}]"
        f"afade=t=in:st=0:d={fade_in},"
        f"afade=t=out:st={fade_out_start}:d={fade_out},"
        f"atrim=0:{target_duration},"
        f"asetpts=N/SR/TB"
        f"[out]"
    )

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:a", "aac",
        "-b:a", "192k",
        str(output_path),
    ]
    _run(cmd)
    return output_path
