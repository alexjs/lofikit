"""LofiKit — convert GoPro footage into lofi YouTube videos."""

from __future__ import annotations

import logging
import subprocess
from typing import Any

__version__ = "0.1.0"

log = logging.getLogger(__name__)

# Module-level flag: when True, FFmpeg stderr is suppressed
ffmpeg_quiet: bool = False


def run_cmd(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """Run a subprocess, capturing stdout and optionally suppressing stderr.

    Stdout is always captured (needed for ffprobe JSON parsing).
    Stderr flows to the terminal by default, but is suppressed when
    ffmpeg_quiet is True (--quiet flag).
    """
    log.debug("Running: %s", " ".join(str(c) for c in cmd))
    stderr = subprocess.DEVNULL if ffmpeg_quiet else None
    return subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=stderr, text=True, check=True, **kwargs
    )
