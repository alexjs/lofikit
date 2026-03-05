# LofiKit

Convert raw video footage into polished lofi YouTube videos from the command line.

Strips the original audio, overlays royalty-free lofi music with crossfades, and maintains source video quality by avoiding re-encoding. One command in, YouTube-ready video out.

## Why

I wanted a one-command pipeline for my YouTube channel. Record footage, run one command, get a video with lofi music, crossfades, and an end card. No editing software, no timeline dragging, no manual audio sync. LofiKit is that pipeline.

The initial codebase was generated in a single session using [Claude Code](https://docs.anthropic.com/en/docs/claude-code) from an architecture spec (see [ARCHITECTURE.md](ARCHITECTURE.md)). Subsequent iterations refined the pipeline based on real-world usage.

## Prerequisites

- **Python 3.12+**
- **FFmpeg**
- **yt-dlp** (optional) — for downloading music from YouTube

## Installation

```bash
git clone https://github.com/alexjs/lofikit.git
cd lofikit

python3 -m venv .venv
source .venv/bin/activate

pip install -e .

lofikit --version
```

## Quick Start

```bash
# 1. Add some lofi music tracks
lofikit library add ~/Music/chill_track.mp3

# Or download from YouTube (requires yt-dlp)
lofikit library sync --url "https://www.youtube.com/watch?v=..."

# 2. Render your video
lofikit render my_footage.mp4

# 3. Output lands in output/my_footage_lofi.mp4
```

## Usage

### Render a video

```bash
# Basic — strips audio, overlays lofi music, outputs to output/
lofikit render input.mp4

# Custom output path
lofikit render input.mp4 --output my_video.mp4

# Apply the lofi colour grade filter
lofikit render input.mp4 --filter lofi_grade

# With end card (off by default)
lofikit render input.mp4 --endcard
lofikit render input.mp4 --endcard --endcard-image assets/my_card.png

# Keep temp files for debugging
lofikit render input.mp4 --keep-temp
```

### Avoid track reuse across videos

Each render writes a `.tracks.txt` manifest alongside the output. Pass previous manifests to avoid reusing the same music:

```bash
lofikit render video1.mp4
lofikit render video2.mp4 --exclude-tracks output/video1_lofi.tracks.txt
lofikit render video3.mp4 \
  --exclude-tracks output/video1_lofi.tracks.txt \
  --exclude-tracks output/video2_lofi.tracks.txt
```

### Blacklist copyrighted tracks

If YouTube flags a track, add its filename to `music/blacklist.txt` (one per line). These are automatically excluded from all future renders.

```
# music/blacklist.txt
Artist - Copyrighted Song.mp3
Another Bad Track.mp3
```

### Manage music library

```bash
# Download tracks from YouTube (single video or playlist)
lofikit library sync --url "https://www.youtube.com/watch?v=..."
lofikit library sync --url "https://www.youtube.com/playlist?list=..."

# Cap downloads (default: 50)
lofikit library sync --url "..." --max-tracks 20

# List all cached tracks
lofikit library list

# Manually add a local track
lofikit library add ~/Music/lofi_beat.mp3
```

### Inspect a video

```bash
lofikit info input.mp4
```

Shows resolution, duration, codec, FPS, rotation, and audio codec.

### Verbosity

```bash
lofikit -v render input.mp4    # Debug output (shows FFmpeg commands)
lofikit -q render input.mp4    # Quiet (suppress FFmpeg output)
lofikit -s render input.mp4    # Silent (no output at all)
```

## How It Works

1. **Probe** input video (resolution, codec, FPS, rotation)
2. **Strip** original audio (stream copy, no re-encode)
3. **Apply visual filters** if requested (re-encodes at high quality CRF 18)
4. **Append end card** if `--endcard` flag is set
5. **Select music** tracks randomly from library to cover video duration
6. **Crossfade** tracks together (default 4s overlap)
7. **Fade** audio in (3s) and out (3s)
8. **Mux** video + composed audio into final MP4

Video is stream-copied (not re-encoded) unless filters are applied, so rendering is fast even for long 4K footage.

## Visual Filters

Filters are optional and disabled by default.

| Filter | Description |
|---|---|
| `passthrough` | No-op, passes video through unchanged |
| `lofi_grade` | Warm colour temperature, slight desaturation, subtle vignette |

```bash
lofikit render input.mp4 --filter lofi_grade
```

### Custom filters

Drop a Python file in `lofikit/filters/` that subclasses `VideoFilter`:

```python
from lofikit.filters.base import VideoFilter
from pathlib import Path

class MyFilter(VideoFilter):
    name = "my_filter"
    description = "My custom filter"

    def apply(self, input_path, output_path, probe_data=None, **kwargs):
        # Your FFmpeg filter logic here
        ...
        return output_path
```

It auto-registers and becomes available via `--filter my_filter`.

## DJI Ingest

A standalone helper script for importing footage from a DJI Action 5 Pro. See [scripts/dji-ingest.py](scripts/dji-ingest.py) for full usage.

```bash
python scripts/dji-ingest.py              # Auto-detect mounted DJI camera
python scripts/dji-ingest.py --dry-run    # Preview without copying
python scripts/dji-ingest.py --status     # Show import history
```

Auto-detects mounted DJI volumes, organises files by recording date, losslessly stitches split recordings (>4GB files), and tracks import history to avoid duplicates.

## CLI Reference

```
lofikit render INPUT_PATH [OPTIONS]
  -o, --output PATH             Output file path
  -f, --filter TEXT             Visual filter (repeatable)
  --music-dir PATH              Music tracks directory
  --endcard                     Append end card (off by default)
  --endcard-image PATH          End card image (PNG)
  --endcard-duration FLOAT      End card duration [default: 20.0]
  --crossfade FLOAT             Audio crossfade seconds [default: 4.0]
  --exclude-tracks PATH         Previous .tracks.txt to exclude (repeatable)
  --keep-temp                   Keep temporary files
  -v, --verbose                 Debug output
  -q, --quiet                   Suppress FFmpeg output
  -s, --silent                  Suppress all output

lofikit library sync [OPTIONS]
  --url TEXT                    YouTube URL to download (repeatable)
  --max-tracks INT              Max tracks per URL [default: 50]
  --music-dir PATH              Music directory

lofikit library list [--music-dir PATH]
lofikit library add TRACK_PATH [--music-dir PATH]
lofikit info INPUT_PATH
```

## Project Structure

```
lofikit/
├── lofikit/             # Python package
│   ├── __init__.py      # Shared run_cmd helper
│   ├── cli.py           # Click CLI entry point
│   ├── pipeline.py      # Main orchestrator
│   ├── video.py         # FFmpeg video operations (probe, strip, mux)
│   ├── audio.py         # Music selection + crossfading
│   ├── endcard.py       # End card generation and append
│   ├── music_library.py # Track download and indexing
│   └── filters/         # Visual filter plugins
│       ├── base.py      # Abstract base filter
│       ├── passthrough.py
│       └── lofi_grade.py
├── scripts/
│   └── dji-ingest.py   # DJI Action 5 Pro import helper
├── assets/              # End card image
├── music/               # Cached music tracks (gitignored)
├── output/              # Rendered videos (gitignored)
├── tests/               # Test suite
└── pyproject.toml
```

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install pytest

pytest tests/ -v
```

## License

MIT
