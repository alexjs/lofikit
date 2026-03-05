# Architecture — LofiKit

> This architecture spec was written to drive [Claude Code](https://docs.anthropic.com/en/docs/claude-code), which generated the initial codebase in a single session. It remains the authoritative reference for the project structure and design decisions.

## What This Is

A CLI tool that converts raw video footage into polished lofi YouTube videos. Strips original audio, overlays royalty-free lofi music with crossfades, and maintains video quality by stream-copying wherever possible.

## Tech Stack

- **Language**: Python 3.12+
- **Video processing**: FFmpeg via `subprocess` (list form, no shell)
- **Audio downloads**: yt-dlp (optional, for pulling tracks from YouTube)
- **CLI framework**: Click
- **Package management**: pip / pyproject.toml

## Project Layout

```
lofikit/
├── lofikit/
│   ├── __init__.py          # Shared run_cmd helper, ffmpeg_quiet flag
│   ├── cli.py               # Click CLI entry point
│   ├── pipeline.py          # Main render orchestrator
│   ├── video.py             # FFmpeg video ops (probe, strip_audio, mux)
│   ├── audio.py             # Track selection, crossfading, fade in/out
│   ├── endcard.py           # End card generation and append (opt-in)
│   ├── music_library.py     # yt-dlp download, local scan, index management
│   └── filters/             # Visual filter plugin system
│       ├── __init__.py      # Auto-discovery and registry
│       ├── base.py          # Abstract VideoFilter base class
│       ├── passthrough.py   # No-op (stream copy)
│       └── lofi_grade.py    # Warm colour grade + desaturation + vignette
├── scripts/
│   └── dji-ingest.py        # Standalone DJI Action 5 Pro import tool
├── assets/                   # Static assets (end card image)
├── music/                    # Downloaded/added tracks + index.json (gitignored)
├── output/                   # Rendered videos + .tracks.txt manifests (gitignored)
├── tests/                    # pytest suite (mocked FFmpeg calls)
└── pyproject.toml
```

## Core Pipeline

```
Input video (any MP4, 4K/1080p)
  → Probe (resolution, codec, fps, rotation)
  → Strip original audio (stream copy, -map 0:v)
  → [Optional] Apply visual filters (re-encodes at CRF 18/22)
  → Select N tracks from music library to cover video duration
  → Crossfade tracks (default 4s overlap)
  → Fade audio in (3s) and out (3s)
  → Mux video + composed audio → final MP4
  → Write .tracks.txt manifest alongside output
```

## Design Decisions

### Stream Copy by Default

Video is never re-encoded unless filters are applied. This keeps rendering fast even for long 4K footage. A 30-minute 4K render completes in under a minute on most machines. When filters require re-encoding, quality is kept high: CRF 18 (H.264) or CRF 22 (H.265).

### Subprocess Handling

All FFmpeg/ffprobe calls go through `run_cmd()` in `__init__.py`:
- List form (no `shell=True`) — safe from injection
- `stdout=subprocess.PIPE` captures output for ffprobe JSON parsing
- `stderr` flows to terminal by default so FFmpeg errors are visible
- `--quiet` / `--silent` flags suppress stderr via `subprocess.DEVNULL`

### Track Manifests and Blacklist

Copyright management is a real problem when producing YouTube content at any volume. Rather than building a complex rights database, LofiKit uses two simple mechanisms:
- Each render writes `output/<name>.tracks.txt` (one filename per line)
- `--exclude-tracks` accepts previous manifests to avoid reuse across videos
- `music/blacklist.txt` is auto-loaded every render to permanently exclude flagged tracks

### Music Library

- Tracks stored as MP3/WAV/M4A in `music/`
- `music/index.json` holds metadata (filename, title, artist, duration, genre, licence)
- `lofikit library sync --url` downloads via yt-dlp; without `--url` scans local files
- `--max-tracks` (default 50) caps downloads to prevent pulling infinite radio mixes

### Filter Plugin System

Extensibility without complexity. New filters are a single Python file:
- `filters/base.py` defines `VideoFilter` ABC with `apply(input_path, output_path, **kwargs)`
- Drop a `.py` file in `filters/` — auto-discovered and registered by name
- Filters chain in order: `--filter lofi_grade --filter letterbox`

## Scope

LofiKit is deliberately single-video, single-command. Batch processing is left to shell scripting (`for f in *.mp4; do lofikit render "$f"; done`). There is no GUI, no web interface, and no built-in YouTube upload. The tool does one thing well: turn a video file into a lofi video file.

## Code Style

- Type hints throughout
- `pathlib.Path` not string paths
- `logging` module, not print (CLI output via Click)
- `subprocess.run` with list args and `check=True`
- Small, testable functions

## Testing

- `tests/` directory with pytest
- FFmpeg calls mocked in unit tests
- 33 tests covering audio, video, CLI, filters, music library, and pipeline
