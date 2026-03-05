"""Video filter plugin system with auto-discovery."""

from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Any

from .base import VideoFilter

log = logging.getLogger(__name__)

# Registry of discovered filters
_registry: dict[str, type[VideoFilter]] = {}


def _discover_filters() -> None:
    """Scan the filters package for VideoFilter subclasses."""
    if _registry:
        return  # Already discovered

    package_dir = Path(__file__).parent

    for importer, modname, ispkg in pkgutil.iter_modules([str(package_dir)]):
        if modname == "base":
            continue
        try:
            module = importlib.import_module(f".{modname}", package=__package__)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, VideoFilter)
                    and attr is not VideoFilter
                    and attr.name
                ):
                    _registry[attr.name] = attr
        except Exception as e:
            log.warning("Failed to load filter module %s: %s", modname, e)


def get_filter(name: str) -> VideoFilter:
    """Get a filter instance by name."""
    _discover_filters()
    if name not in _registry:
        available = ", ".join(sorted(_registry.keys()))
        raise ValueError(f"Unknown filter '{name}'. Available: {available}")
    return _registry[name]()


def list_filters() -> dict[str, str]:
    """Return dict of filter name -> description."""
    _discover_filters()
    return {name: cls.description for name, cls in sorted(_registry.items())}


def apply_filters(
    input_path: Path,
    output_path: Path,
    filter_names: list[str],
    probe_data: dict[str, Any] | None = None,
    temp_dir: Path | None = None,
) -> Path:
    """Apply a chain of filters in sequence.

    If no filters are specified, uses passthrough (returns input unchanged).
    """
    if not filter_names:
        filter_names = ["passthrough"]

    import tempfile

    current = input_path
    for i, name in enumerate(filter_names):
        filt = get_filter(name)
        if i == len(filter_names) - 1:
            # Last filter writes to final output
            dest = output_path
        else:
            # Intermediate filters write to temp files
            suffix = f"_filter_{i}.mp4"
            if temp_dir:
                dest = temp_dir / f"filtered{suffix}"
            else:
                dest = output_path.parent / f"temp{suffix}"

        log.info("Applying filter: %s", name)
        current = filt.apply(current, dest, probe_data=probe_data)

    return current


__all__ = ["VideoFilter", "get_filter", "list_filters", "apply_filters"]
