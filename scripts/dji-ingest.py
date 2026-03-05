#!/usr/bin/env python3
"""
DJI Action 5 Pro Ingest Tool

Imports videos from a DJI Action 5 Pro, organises by recording date,
losslessly stitches split files, and tracks what's already been imported.

Usage:
    dji-ingest.py                          # Auto-detect mounted DJI volume
    dji-ingest.py /Volumes/DJI_ACTION      # Explicit mount point
    dji-ingest.py --tag "sf-highway"       # Tag this import batch
    dji-ingest.py --dry-run                # Show what would happen
    dji-ingest.py --status                 # Show import history

DJI Action 5 Pro file structure:
    DCIM/
    └── 100MEDIA/ (101MEDIA, etc.)
        ├── DJI_20260222120000_0001_D.MP4   # Single recording
        ├── DJI_20260222130000_0002_D.MP4   # Split part 1 (>4GB)
        ├── DJI_20260222130000_0003_D.MP4   # Split part 2 (same timestamp)
        └── ...

Split files share the same timestamp prefix; sequential file numbers indicate parts.
"""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# --- Configuration ---

OUTPUT_BASE = Path.home() / "content" / "dji"
STATE_FILE = OUTPUT_BASE / ".ingest_state.json"
FFMPEG_CONCAT_TIMEOUT = 3600  # 1 hour max for stitching

# DJI Action 5 Pro naming pattern
# Format: DJI_YYYYMMDDHHMMSS_NNNN_D.MP4
# The _D suffix indicates video (vs _D for photo which is .JPG)
DJI_VIDEO_PATTERN = re.compile(
    r"^DJI_(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})_(\d{4})_D\.MP4$",
    re.IGNORECASE,
)

# Video extensions to consider
VIDEO_EXTENSIONS = {".mp4", ".mov"}


def find_dji_volume() -> Path | None:
    """Auto-detect mounted DJI Action camera volume."""
    if platform.system() != "Darwin":
        print("Auto-detect only supported on macOS. Specify mount point manually.")
        return None

    volumes = Path("/Volumes")
    candidates = []
    for vol in volumes.iterdir():
        if not vol.is_dir():
            continue
        dcim = vol / "DCIM"
        if dcim.is_dir():
            # Check for DJI-style files in any subfolder
            for media_dir in dcim.iterdir():
                if media_dir.is_dir():
                    for f in media_dir.iterdir():
                        if DJI_VIDEO_PATTERN.match(f.name):
                            candidates.append(vol)
                            break
                    if vol in candidates:
                        break

    if len(candidates) == 1:
        return candidates[0]
    elif len(candidates) > 1:
        print(f"Multiple DJI volumes found: {[str(c) for c in candidates]}")
        print("Specify one explicitly.")
        return None
    return None


def scan_videos(mount_point: Path) -> list[dict]:
    """Scan DJI volume for video files and parse metadata from filenames."""
    dcim = mount_point / "DCIM"
    if not dcim.is_dir():
        print(f"No DCIM directory found at {mount_point}")
        return []

    videos = []
    for media_dir in sorted(dcim.iterdir()):
        if not media_dir.is_dir():
            continue
        for f in sorted(media_dir.iterdir()):
            match = DJI_VIDEO_PATTERN.match(f.name)
            if not match:
                # Also grab any other video files (LRV previews, etc.)
                if f.suffix.lower() in VIDEO_EXTENSIONS and not f.name.startswith("."):
                    # Non-standard naming — include but can't parse timestamp
                    videos.append({
                        "path": f,
                        "filename": f.name,
                        "timestamp": None,
                        "sequence": 0,
                        "group_key": f.stem,
                        "size": f.stat().st_size,
                    })
                continue

            year, month, day, hour, minute, second, seq = match.groups()
            ts = datetime(int(year), int(month), int(day),
                         int(hour), int(minute), int(second))
            # Group key = timestamp (split files share the same timestamp)
            group_key = f"{year}{month}{day}{hour}{minute}{second}"

            videos.append({
                "path": f,
                "filename": f.name,
                "timestamp": ts,
                "sequence": int(seq),
                "group_key": group_key,
                "size": f.stat().st_size,
            })

    return videos


def group_split_files(videos: list[dict]) -> list[dict]:
    """
    Group videos by recording session. Split files share the same timestamp.
    Returns list of recording groups, each with ordered parts.
    """
    groups: dict[str, list[dict]] = {}
    ungrouped = []

    for v in videos:
        if v["timestamp"] is None:
            ungrouped.append(v)
            continue
        key = v["group_key"]
        groups.setdefault(key, []).append(v)

    # Sort parts within each group by sequence number
    recordings = []
    for key in sorted(groups.keys()):
        parts = sorted(groups[key], key=lambda x: x["sequence"])
        ts = parts[0]["timestamp"]
        total_size = sum(p["size"] for p in parts)
        recordings.append({
            "group_key": key,
            "timestamp": ts,
            "date_str": ts.strftime("%Y-%m-%d"),
            "time_str": ts.strftime("%H%M%S"),
            "parts": parts,
            "is_split": len(parts) > 1,
            "total_size": total_size,
        })

    # Add ungrouped files as individual recordings
    for v in ungrouped:
        recordings.append({
            "group_key": v["group_key"],
            "timestamp": None,
            "date_str": "unknown",
            "time_str": v["filename"],
            "parts": [v],
            "is_split": False,
            "total_size": v["size"],
        })

    return recordings


def file_hash(path: Path, chunk_size: int = 8192) -> str:
    """SHA-256 hash of first 1MB of file (fast fingerprint, not full hash)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        remaining = 1024 * 1024  # 1MB
        while remaining > 0:
            chunk = f.read(min(chunk_size, remaining))
            if not chunk:
                break
            h.update(chunk)
            remaining -= len(chunk)
    return h.hexdigest()


def load_state() -> dict:
    """Load ingest state from disk."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            print(f"Warning: corrupt state file at {STATE_FILE}, starting fresh")
    return {"imported": {}, "imports": []}


def save_state(state: dict):
    """Persist ingest state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def is_already_imported(state: dict, recording: dict) -> bool:
    """Check if a recording has already been imported (by group_key + first file hash)."""
    first_file = recording["parts"][0]["path"]
    fingerprint = f"{recording['group_key']}_{file_hash(first_file)}"
    return fingerprint in state.get("imported", {})


def mark_imported(state: dict, recording: dict, output_path: Path, tag: str | None):
    """Record that a recording has been imported."""
    first_file = recording["parts"][0]["path"]
    fingerprint = f"{recording['group_key']}_{file_hash(first_file)}"
    state.setdefault("imported", {})[fingerprint] = {
        "output": str(output_path),
        "imported_at": datetime.now().isoformat(),
        "source_files": [str(p["path"]) for p in recording["parts"]],
        "tag": tag,
    }


def stitch_files(parts: list[dict], output: Path) -> bool:
    """
    Losslessly concatenate split MP4 files using FFmpeg concat demuxer.
    This is lossless — no re-encoding, just container-level joining.
    """
    if len(parts) == 1:
        # Single file — just copy
        print(f"    Copying {parts[0]['filename']}...")
        shutil.copy2(parts[0]["path"], output)
        return True

    # Create concat file list
    concat_list = output.parent / f".concat_{output.stem}.txt"
    try:
        with open(concat_list, "w") as f:
            for part in parts:
                # FFmpeg concat demuxer needs escaped paths
                escaped = str(part["path"]).replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        print(f"    Stitching {len(parts)} parts...")
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",  # Lossless — stream copy, no re-encode
            "-movflags", "+faststart",
            str(output),
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=FFMPEG_CONCAT_TIMEOUT,
        )

        if result.returncode != 0:
            print(f"    FFmpeg error: {result.stderr[-500:]}")
            return False

        return True

    finally:
        if concat_list.exists():
            concat_list.unlink()


def format_size(size_bytes: int) -> str:
    """Human-readable file size."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def check_ffmpeg():
    """Verify FFmpeg is installed."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("FFmpeg not found. Install with: brew install ffmpeg")
        sys.exit(1)


def show_status(state: dict):
    """Display import history."""
    imports = state.get("imported", {})
    if not imports:
        print("No imports recorded yet.")
        return

    print(f"\n{'─' * 60}")
    print(f"  DJI Ingest History — {len(imports)} recording(s) imported")
    print(f"{'─' * 60}\n")

    # Group by date
    by_date: dict[str, list] = {}
    for fingerprint, info in imports.items():
        output = Path(info["output"])
        date = output.parent.name if output.parent.name != "dji" else "unknown"
        by_date.setdefault(date, []).append(info)

    for date in sorted(by_date.keys(), reverse=True):
        print(f"  📅 {date}")
        for info in by_date[date]:
            output = Path(info["output"])
            tag = f" [{info['tag']}]" if info.get("tag") else ""
            parts = len(info.get("source_files", []))
            parts_str = f" ({parts} parts stitched)" if parts > 1 else ""
            exists = "✓" if output.exists() else "✗ missing"
            print(f"    {exists} {output.name}{tag}{parts_str}")
        print()


def ingest(mount_point: Path, tag: str | None = None, dry_run: bool = False):
    """Main ingest pipeline."""
    check_ffmpeg()

    print(f"Scanning {mount_point}...")
    videos = scan_videos(mount_point)
    if not videos:
        print("No DJI video files found.")
        return

    recordings = group_split_files(videos)
    state = load_state()

    total_files = sum(len(r["parts"]) for r in recordings)
    total_size = sum(r["total_size"] for r in recordings)
    print(f"Found {len(recordings)} recording(s) ({total_files} files, {format_size(total_size)})\n")

    new_count = 0
    skip_count = 0

    for rec in recordings:
        date_str = rec["date_str"]
        time_str = rec["time_str"]
        parts = rec["parts"]

        # Build output filename
        if tag:
            out_name = f"{date_str}_{time_str}_{tag}.mp4"
        else:
            out_name = f"{date_str}_{time_str}.mp4"

        out_dir = OUTPUT_BASE / date_str
        out_path = out_dir / out_name

        # Check if already imported
        if is_already_imported(state, rec):
            print(f"  ⏭  {out_name} (already imported)")
            skip_count += 1
            continue

        parts_info = f" [{len(parts)} parts]" if rec["is_split"] else ""
        print(f"  📹 {out_name}{parts_info} ({format_size(rec['total_size'])})")

        if dry_run:
            print(f"    → would save to {out_path}")
            new_count += 1
            continue

        # Create output directory
        out_dir.mkdir(parents=True, exist_ok=True)

        # Stitch or copy
        if stitch_files(parts, out_path):
            mark_imported(state, rec, out_path, tag)
            save_state(state)
            output_size = out_path.stat().st_size
            print(f"    ✓ Saved ({format_size(output_size)})")
            new_count += 1
        else:
            print(f"    ✗ Failed to process")

    print(f"\nDone: {new_count} new, {skip_count} skipped")
    if dry_run and new_count > 0:
        print("(dry run — no files were copied)")


def main():
    parser = argparse.ArgumentParser(
        description="Import and organise videos from DJI Action 5 Pro",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              Auto-detect DJI volume, import all
  %(prog)s /Volumes/DJI_ACTION          Import from specific volume
  %(prog)s --tag "sf-golden-gate"       Tag this batch of imports
  %(prog)s --dry-run                    Preview without copying
  %(prog)s --status                     Show import history
        """,
    )
    parser.add_argument("mount_point", nargs="?", help="DJI camera mount point (auto-detected if omitted)")
    parser.add_argument("--tag", "-t", help="Tag for this import batch (e.g. 'sf-highway')")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Show what would happen without copying")
    parser.add_argument("--status", "-s", action="store_true", help="Show import history")
    parser.add_argument("--output", "-o", type=Path, default=OUTPUT_BASE, help=f"Output base directory (default: {OUTPUT_BASE})")

    args = parser.parse_args()

    global OUTPUT_BASE, STATE_FILE
    OUTPUT_BASE = args.output
    STATE_FILE = OUTPUT_BASE / ".ingest_state.json"

    if args.status:
        show_status(load_state())
        return

    if args.mount_point:
        mount = Path(args.mount_point)
    else:
        mount = find_dji_volume()
        if mount is None:
            print("Could not auto-detect DJI volume.")
            print("Plug in your DJI Action 5 Pro, or specify the mount point:")
            print(f"  {sys.argv[0]} /Volumes/DJI_ACTION")
            sys.exit(1)

    print(f"DJI volume: {mount}")

    if not mount.exists():
        print(f"Mount point does not exist: {mount}")
        sys.exit(1)

    ingest(mount, tag=args.tag, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
