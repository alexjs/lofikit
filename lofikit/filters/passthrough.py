"""Passthrough filter — no-op, stream copies the video."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from .base import VideoFilter

log = logging.getLogger(__name__)


class Passthrough(VideoFilter):
    """Default filter that does nothing (stream copy)."""

    name = "passthrough"
    description = "No-op filter, passes video through unchanged"

    def apply(
        self,
        input_path: Path,
        output_path: Path,
        probe_data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Path:
        """Copy input to output unchanged."""
        log.debug("Passthrough: copying %s to %s", input_path, output_path)
        shutil.copy2(input_path, output_path)
        return output_path
