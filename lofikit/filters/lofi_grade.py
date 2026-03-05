"""Lofi colour grade filter — warm tones, desaturation, vignette."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .. import run_cmd
from .base import VideoFilter

log = logging.getLogger(__name__)


class LofiGrade(VideoFilter):
    """Warm colour grade with slight desaturation and subtle vignette.

    Applies: warm colour temperature, reduced saturation, soft vignette.
    Re-encodes at CRF 18 H.264 to maintain quality.
    """

    name = "lofi_grade"
    description = "Warm colour grade + desaturation + vignette"

    def apply(
        self,
        input_path: Path,
        output_path: Path,
        probe_data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Path:
        """Apply lofi colour grade using FFmpeg filtergraph."""
        # colortemperature: 6800K for warm tones
        # eq: saturation 0.85 for slight desaturation
        # vignette: PI/5 for subtle darkening at edges
        filtergraph = "colortemperature=6800,eq=saturation=0.85,vignette=PI/5"

        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-vf", filtergraph,
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "medium",
            "-pix_fmt", "yuv420p",
            "-an",
            str(output_path),
        ]
        run_cmd(cmd)
        return output_path
