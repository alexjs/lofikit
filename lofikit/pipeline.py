"""Main render pipeline orchestrator."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from . import audio, endcard, video
from .filters import apply_filters

log = logging.getLogger(__name__)

# Default paths
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / "output"
DEFAULT_MUSIC_DIR = Path(__file__).parent.parent / "music"
DEFAULT_ENDCARD = Path(__file__).parent.parent / "assets" / "endcard.png"


def render(
    input_path: Path,
    output_path: Path | None = None,
    filter_names: list[str] | None = None,
    music_dir: Path | None = None,
    endcard_path: Path | None = None,
    endcard_duration: float = 20.0,
    endcard_fade: float = 2.0,
    crossfade: float = 4.0,
    fade_in: float = 3.0,
    fade_out: float = 3.0,
    no_endcard: bool = False,
    keep_temp: bool = False,
    exclude_tracks_files: list[Path] | None = None,
) -> Path:
    """Run the full render pipeline.

    Steps:
        1. Probe input video
        2. Strip audio
        3. Apply visual filters
        4. Append end card
        5. Select and compose audio
        6. Mux final video + audio
        7. Clean up temp files
    """
    video.check_ffmpeg()

    if not input_path.exists():
        raise FileNotFoundError(f"Input video not found: {input_path}")

    music_dir = music_dir or DEFAULT_MUSIC_DIR
    endcard_path = endcard_path or DEFAULT_ENDCARD
    filter_names = filter_names or []

    # Resolve output path
    if output_path is None:
        output_dir = DEFAULT_OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{input_path.stem}_lofi.mp4"
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate placeholder endcard if none exists
    if not no_endcard and not endcard_path.exists():
        log.info("No end card found, generating placeholder...")
        endcard.generate_placeholder(endcard_path)

    # Step 1: Probe
    log.info("Probing input video: %s", input_path)
    info = video.probe(input_path)
    log.info(
        "Video: %dx%d, %.1fs, %s @ %.1f fps",
        info["width"], info["height"], info["duration"],
        info["codec"], info["fps"],
    )

    tmp_dir = Path(tempfile.mkdtemp(prefix="lofikit_"))
    if keep_temp:
        log.info("Temp files: %s", tmp_dir)

    try:
        # Step 2: Strip audio
        log.info("Stripping original audio...")
        silent_video = tmp_dir / "silent.mp4"
        video.strip_audio(input_path, silent_video)

        # Step 3: Apply visual filters
        has_filters = bool(filter_names) and filter_names != ["passthrough"]
        if has_filters:
            log.info("Applying filters: %s", ", ".join(filter_names))
            filtered_video = tmp_dir / "filtered.mp4"
            apply_filters(
                silent_video, filtered_video, filter_names,
                probe_data=info, temp_dir=tmp_dir,
            )
        else:
            filtered_video = silent_video

        # Step 4: Append end card
        if no_endcard:
            video_with_endcard = filtered_video
            total_duration = info["duration"]
        else:
            log.info("Appending end card (%.0fs)...", endcard_duration)
            video_with_endcard = tmp_dir / "with_endcard.mp4"
            endcard.append_endcard(
                filtered_video,
                endcard_path,
                video_with_endcard,
                width=info["width"],
                height=info["height"],
                fps=info["fps"],
                codec=info["codec"],
                rotation=info.get("rotation", 0),
                duration=endcard_duration,
                fade_duration=endcard_fade,
                temp_dir=tmp_dir,
            )
            total_duration = info["duration"] + endcard_duration - endcard_fade

        # Build exclusion set from blacklist + previous track manifests
        exclude: set[str] = set()
        blacklist = music_dir / "blacklist.txt"
        sources = [blacklist, *(exclude_tracks_files or [])]
        for ef in sources:
            if ef.exists():
                exclude.update(
                    line.strip() for line in ef.read_text().splitlines() if line.strip()
                )

        # Step 5: Select and compose audio
        log.info("Composing audio (%.1fs target)...", total_duration)
        tracks = audio.select_tracks(
            music_dir, total_duration, crossfade=crossfade, exclude=exclude or None,
        )
        composed_audio = tmp_dir / "audio.m4a"
        audio.compose_audio(
            tracks,
            target_duration=total_duration,
            crossfade=crossfade,
            fade_in=fade_in,
            fade_out=fade_out,
            output_path=composed_audio,
        )

        # Step 6: Mux
        log.info("Muxing final video...")
        video.mux(video_with_endcard, composed_audio, output_path)
    finally:
        if not keep_temp:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
        else:
            log.info("Temp files kept at: %s", tmp_dir)

    # Summary
    final_size = output_path.stat().st_size / (1024 * 1024)
    log.info("Render complete!")
    log.info("Output: %s (%.1f MB)", output_path, final_size)
    log.info("Duration: %.1fs (video) + %.1fs (end card)", info["duration"],
             endcard_duration if not no_endcard else 0)
    log.info("Tracks used: %s", ", ".join(t.stem for t in tracks))

    # Write track manifest alongside output
    manifest = output_path.with_suffix(".tracks.txt")
    manifest.write_text("\n".join(t.name for t in tracks) + "\n")
    log.info("Track manifest: %s", manifest)

    return output_path
