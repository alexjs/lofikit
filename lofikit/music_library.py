"""Music library management: download, list, and add tracks."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

from . import run_cmd as _run

log = logging.getLogger(__name__)

# Default music directory
DEFAULT_MUSIC_DIR = Path(__file__).parent.parent / "music"


def check_ytdlp() -> None:
    """Verify yt-dlp is available."""
    try:
        subprocess.run(
            ["yt-dlp", "--version"], capture_output=True, text=True, check=True
        )
    except FileNotFoundError:
        raise SystemExit(
            "yt-dlp not found. Install with: brew install yt-dlp"
        )


def _probe_duration(path: Path) -> float:
    """Probe the duration of an audio file using ffprobe."""
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


def _load_index(music_dir: Path) -> list[dict[str, Any]]:
    """Load the track index."""
    index_path = music_dir / "index.json"
    if index_path.exists():
        with open(index_path) as f:
            return json.load(f)
    return []


def _save_index(music_dir: Path, index: list[dict[str, Any]]) -> None:
    """Save the track index."""
    index_path = music_dir / "index.json"
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)


def sync(
    music_dir: Path,
    playlists: list[str] | None = None,
    max_tracks: int = 50,
) -> int:
    """Download tracks from YouTube via yt-dlp, then index all files on disk.

    Pass URLs with --url. If none are provided, falls back to scanning
    the music directory for any existing audio files.

    Returns the number of new tracks indexed.
    """
    if not playlists:
        log.info("No URLs provided. Scanning local files instead.")
        return scan_local(music_dir)

    check_ytdlp()
    music_dir.mkdir(parents=True, exist_ok=True)

    for url in playlists:
        log.info("Downloading from: %s", url)
        cmd = [
            "yt-dlp",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "--output", str(music_dir / "%(title)s.%(ext)s"),
            "--no-overwrites",
            "--playlist-end", str(max_tracks),
            url,
        ]
        log.debug("Running: %s", " ".join(cmd))
        try:
            subprocess.run(cmd, check=False)
        except KeyboardInterrupt:
            log.info("Download interrupted by user.")
            break

    # Index everything on disk (catches all downloads, even partial runs)
    count = scan_local(music_dir)
    log.info("Sync complete. %d new tracks indexed.", count)
    return count


def scan_local(music_dir: Path) -> int:
    """Scan music directory for audio files not yet in the index.

    Fallback for when yt-dlp is not available or playlists are unreliable.
    Returns the number of new tracks added to the index.
    """
    music_dir.mkdir(parents=True, exist_ok=True)
    index = _load_index(music_dir)
    existing_files = {entry["filename"] for entry in index}
    new_count = 0

    for ext in ("*.mp3", "*.wav", "*.m4a", "*.ogg", "*.flac"):
        for path in music_dir.glob(ext):
            if path.name in existing_files:
                continue
            try:
                duration = _probe_duration(path)
            except Exception:
                log.warning("Could not probe %s, skipping", path)
                continue

            entry = {
                "filename": path.name,
                "title": path.stem,
                "artist": "Unknown",
                "duration": duration,
                "genre": "lofi",
                "licence": "User provided",
            }
            index.append(entry)
            existing_files.add(path.name)
            new_count += 1
            log.info("Indexed: %s (%.1fs)", entry["title"], duration)

    _save_index(music_dir, index)
    return new_count


def list_tracks(music_dir: Path) -> list[dict[str, Any]]:
    """Return all tracks in the library index.

    Also scans for any un-indexed local files.
    """
    scan_local(music_dir)
    return _load_index(music_dir)


def add_track(source_path: Path, music_dir: Path) -> dict[str, Any]:
    """Copy an audio file into the music library and index it."""
    music_dir.mkdir(parents=True, exist_ok=True)
    dest = music_dir / source_path.name

    if not source_path.exists():
        raise FileNotFoundError(f"File not found: {source_path}")

    shutil.copy2(source_path, dest)
    duration = _probe_duration(dest)

    entry = {
        "filename": dest.name,
        "title": dest.stem,
        "artist": "Unknown",
        "duration": duration,
        "genre": "lofi",
        "licence": "User provided",
    }

    index = _load_index(music_dir)
    # Remove any existing entry with same filename
    index = [e for e in index if e["filename"] != dest.name]
    index.append(entry)
    _save_index(music_dir, index)

    log.info("Added track: %s (%.1fs)", entry["title"], duration)
    return entry
