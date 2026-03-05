"""Abstract base class for video filters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class VideoFilter(ABC):
    """Base class for all video filters.

    Subclasses must define `name`, `description`, and implement `apply()`.
    """

    name: str = ""
    description: str = ""

    @abstractmethod
    def apply(
        self,
        input_path: Path,
        output_path: Path,
        probe_data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Path:
        """Apply the filter to a video file.

        Args:
            input_path: Path to the input video.
            output_path: Path where the filtered video should be written.
            probe_data: Video metadata from video.probe() (resolution, fps, etc.).
            **kwargs: Additional filter-specific parameters.

        Returns:
            Path to the output file.
        """
        ...
