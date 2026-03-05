"""Tests for filter plugin system."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from lofikit.filters import get_filter, list_filters
from lofikit.filters.base import VideoFilter
from lofikit.filters.passthrough import Passthrough


def test_passthrough_copies_file(tmp_path: Path) -> None:
    """Test passthrough filter copies file unchanged."""
    src = tmp_path / "input.mp4"
    dst = tmp_path / "output.mp4"
    src.write_text("video data")

    filt = Passthrough()
    result = filt.apply(src, dst)

    assert result == dst
    assert dst.read_text() == "video data"


def test_get_filter_passthrough() -> None:
    """Test filter registry finds passthrough."""
    filt = get_filter("passthrough")
    assert isinstance(filt, Passthrough)


def test_get_filter_lofi_grade() -> None:
    """Test filter registry finds lofi_grade."""
    filt = get_filter("lofi_grade")
    assert filt.name == "lofi_grade"


def test_get_filter_unknown() -> None:
    """Test unknown filter raises ValueError."""
    with pytest.raises(ValueError, match="Unknown filter"):
        get_filter("nonexistent")


def test_list_filters() -> None:
    """Test listing available filters."""
    filters = list_filters()
    assert "passthrough" in filters
    assert "lofi_grade" in filters


def test_lofi_grade_calls_ffmpeg() -> None:
    """Test lofi_grade filter runs correct ffmpeg command."""
    from lofikit.filters.lofi_grade import LofiGrade

    with patch("subprocess.run") as mock_run:
        filt = LofiGrade()
        filt.apply(Path("in.mp4"), Path("out.mp4"))

    cmd = mock_run.call_args[0][0]
    assert "-vf" in cmd
    vf = cmd[cmd.index("-vf") + 1]
    assert "colortemperature" in vf
    assert "vignette" in vf
