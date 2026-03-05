"""Click CLI entry point for LofiKit."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from . import __version__


def _setup_logging(verbose: bool, quiet: bool, silent: bool) -> None:
    """Configure logging based on verbosity flags."""
    if silent:
        logging.disable(logging.CRITICAL)
        return

    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format="%(message)s" if not verbose else "%(levelname)s: %(message)s",
        stream=sys.stderr,
    )


@click.group()
@click.version_option(version=__version__)
@click.option("-v", "--verbose", is_flag=True, help="Enable debug output.")
@click.option("-q", "--quiet", is_flag=True, help="Suppress FFmpeg output, show only lofikit messages.")
@click.option("-s", "--silent", is_flag=True, help="Suppress all output.")
@click.pass_context
def cli(ctx: click.Context, verbose: bool, quiet: bool, silent: bool) -> None:
    """LofiKit — convert GoPro footage into lofi YouTube videos."""
    import lofikit

    _setup_logging(verbose, quiet, silent)

    # Set module-level ffmpeg quiet flag
    lofikit.ffmpeg_quiet = quiet or silent

    ctx.ensure_object(dict)
    ctx.obj["silent"] = silent


@cli.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", "output_path", type=click.Path(path_type=Path), default=None,
              help="Output file path. Default: output/<input>_lofi.mp4")
@click.option("-f", "--filter", "filters", multiple=True,
              help="Visual filter to apply (can be repeated). E.g. --filter lofi_grade")
@click.option("--music-dir", type=click.Path(path_type=Path), default=None,
              help="Directory containing music tracks.")
@click.option("--endcard", is_flag=True, default=False,
              help="Append end card to video (off by default).")
@click.option("--endcard-image", type=click.Path(path_type=Path), default=None,
              help="Path to end card image (PNG).")
@click.option("--endcard-duration", type=float, default=20.0, show_default=True,
              help="End card duration in seconds.")
@click.option("--crossfade", type=float, default=4.0, show_default=True,
              help="Audio crossfade duration in seconds.")
@click.option("--exclude-tracks", "exclude_tracks", multiple=True,
              type=click.Path(exists=True, path_type=Path),
              help="Path to .tracks.txt manifest to exclude (can be repeated).")
@click.option("--keep-temp", is_flag=True, help="Keep temporary files (don't clean up).")
@click.pass_context
def render(
    ctx: click.Context,
    input_path: Path,
    output_path: Path | None,
    filters: tuple[str, ...],
    music_dir: Path | None,
    endcard: bool,
    endcard_image: Path | None,
    endcard_duration: float,
    crossfade: float,
    exclude_tracks: tuple[Path, ...],
    keep_temp: bool,
) -> None:
    """Render a lofi video from input footage.

    Takes a GoPro MP4 file, strips audio, overlays lofi music with
    crossfades, and appends a branded end card.
    """
    from . import pipeline

    silent = ctx.obj.get("silent", False)

    if not silent:
        click.echo(click.style(f"LofiKit v{__version__}", fg="cyan", bold=True))
        click.echo(f"Input: {input_path}")

    try:
        result = pipeline.render(
            input_path=input_path,
            output_path=output_path,
            filter_names=list(filters),
            music_dir=music_dir,
            endcard_path=endcard_image,
            endcard_duration=endcard_duration,
            crossfade=crossfade,
            no_endcard=not endcard,
            keep_temp=keep_temp,
            exclude_tracks_files=list(exclude_tracks) if exclude_tracks else None,
        )
        if not silent:
            click.echo()
            click.echo(click.style("Done!", fg="green", bold=True))
            click.echo(f"Output: {result}")
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        raise SystemExit(1)


@cli.group()
def library() -> None:
    """Manage the music library."""
    pass


@library.command("sync")
@click.option("--music-dir", type=click.Path(path_type=Path), default=None,
              help="Music directory.")
@click.option("--url", "urls", multiple=True,
              help="YouTube video or playlist URL to download (can be repeated).")
@click.option("--max-tracks", type=int, default=50, show_default=True,
              help="Max tracks to download per URL (prevents infinite radio mixes).")
@click.pass_context
def library_sync(ctx: click.Context, music_dir: Path | None, urls: tuple[str, ...], max_tracks: int) -> None:
    """Download tracks from YouTube via yt-dlp.

    Accepts single video URLs or playlist URLs. Without --url, scans
    the music directory for any existing audio files.

    yt-dlp output streams to your terminal. Press Ctrl+C to stop
    downloading early — tracks already on disk will still be indexed.

    \b
    Examples:
      lofikit library sync --url "https://www.youtube.com/watch?v=..."
      lofikit library sync --url "https://www.youtube.com/playlist?list=..."
      lofikit library sync   # scans music/ for local .mp3/.wav files
    """
    from . import music_library

    silent = ctx.obj.get("silent", False)
    music_dir = music_dir or music_library.DEFAULT_MUSIC_DIR

    if not silent:
        if urls:
            click.echo("Downloading from YouTube...")
        else:
            click.echo(f"No --url provided. Scanning {music_dir} for local tracks...")
    try:
        count = music_library.sync(
            music_dir,
            playlists=list(urls) if urls else None,
            max_tracks=max_tracks,
        )
        if not silent:
            click.echo(click.style(f"Indexed {count} new tracks.", fg="green"))
    except SystemExit:
        raise
    except Exception as e:
        if not silent:
            click.echo(click.style(f"Sync failed: {e}", fg="red"), err=True)
            click.echo("Falling back to local scan...")
        count = music_library.scan_local(music_dir)
        if not silent:
            click.echo(f"Found {count} local tracks.")


@library.command("list")
@click.option("--music-dir", type=click.Path(path_type=Path), default=None,
              help="Music directory.")
def library_list(music_dir: Path | None) -> None:
    """Show cached music tracks."""
    from . import music_library

    music_dir = music_dir or music_library.DEFAULT_MUSIC_DIR
    tracks = music_library.list_tracks(music_dir)

    if not tracks:
        click.echo("No tracks found. Run 'lofikit library sync' or add tracks manually.")
        return

    click.echo(click.style(f"Music Library ({len(tracks)} tracks):", bold=True))
    click.echo()

    for i, track in enumerate(tracks, 1):
        duration = track.get("duration", 0)
        mins = int(duration // 60)
        secs = int(duration % 60)
        click.echo(
            f"  {i:3d}. {track['title'][:50]:<50s} "
            f"{track.get('artist', 'Unknown')[:20]:<20s} "
            f"{mins}:{secs:02d}"
        )

    total_duration = sum(t.get("duration", 0) for t in tracks)
    total_mins = int(total_duration // 60)
    total_secs = int(total_duration % 60)
    click.echo()
    click.echo(f"  Total: {total_mins}:{total_secs:02d}")


@library.command("add")
@click.argument("track_path", type=click.Path(exists=True, path_type=Path))
@click.option("--music-dir", type=click.Path(path_type=Path), default=None,
              help="Music directory.")
@click.pass_context
def library_add(ctx: click.Context, track_path: Path, music_dir: Path | None) -> None:
    """Add a music track to the library."""
    from . import music_library

    silent = ctx.obj.get("silent", False)
    music_dir = music_dir or music_library.DEFAULT_MUSIC_DIR

    entry = music_library.add_track(track_path, music_dir)
    if not silent:
        duration = entry["duration"]
        mins = int(duration // 60)
        secs = int(duration % 60)
        click.echo(click.style(f"Added: {entry['title']} ({mins}:{secs:02d})", fg="green"))


@cli.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
def info(input_path: Path) -> None:
    """Show video file details."""
    from . import video

    video.check_ffmpeg()

    try:
        data = video.probe(input_path)
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        raise SystemExit(1)

    duration = data["duration"]
    mins = int(duration // 60)
    secs = int(duration % 60)

    click.echo(click.style("Video Info:", bold=True))
    click.echo(f"  File:       {input_path}")
    click.echo(f"  Resolution: {data['width']}x{data['height']}")
    click.echo(f"  Duration:   {mins}:{secs:02d} ({duration:.1f}s)")
    click.echo(f"  Codec:      {data['codec']}")
    click.echo(f"  FPS:        {data['fps']}")
    click.echo(f"  Rotation:   {data['rotation']}°" if data.get('rotation') else "")
    click.echo(f"  Audio:      {data['audio_codec'] or 'None'}")


if __name__ == "__main__":
    cli()
