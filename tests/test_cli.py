"""Tests for the CLI."""

from __future__ import annotations

from click.testing import CliRunner

from lofikit.cli import cli


def test_cli_help() -> None:
    """Test CLI shows help."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "LofiKit" in result.output


def test_cli_version() -> None:
    """Test CLI shows version."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_render_help() -> None:
    """Test render command help."""
    runner = CliRunner()
    result = runner.invoke(cli, ["render", "--help"])
    assert result.exit_code == 0
    assert "--filter" in result.output
    assert "--output" in result.output
    assert "--endcard" in result.output
    assert "--exclude-tracks" in result.output


def test_library_help() -> None:
    """Test library command help."""
    runner = CliRunner()
    result = runner.invoke(cli, ["library", "--help"])
    assert result.exit_code == 0
    assert "sync" in result.output
    assert "list" in result.output
    assert "add" in result.output


def test_info_help() -> None:
    """Test info command help."""
    runner = CliRunner()
    result = runner.invoke(cli, ["info", "--help"])
    assert result.exit_code == 0
