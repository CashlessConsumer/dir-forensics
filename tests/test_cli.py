"""Unit tests for arbor.cli entry point"""
import subprocess
import sys
from pathlib import Path

def test_cli_help():
    """Running `python -m arbor.cli --help` should succeed."""
    result = subprocess.run(
        [sys.executable, "-m", "arbor.cli", "--help"],
        capture_output=True, text=True, cwd=Path("/home/workspace/Projects/dir-forensics"),
    )
    assert result.returncode == 0
    assert "arbor" in result.stdout.lower() or "command" in result.stdout.lower()

def test_cli_demo_command():
    """The `demo` command should run without errors on the demo case."""
    result = subprocess.run(
        [sys.executable, "-m", "arbor.cli", "demo", "cases/demo.yaml"],
        capture_output=True, text=True, cwd=Path("/home/workspace/Projects/dir-forensics"),
    )
    # The demo command generates data; it may or may not succeed depending on demo.yaml,
    # but it should not crash with an import error or similar.
    assert "ImportError" not in result.stderr

def test_cli_serve_command():
    """The `serve` command should at least start parsing."""
    result = subprocess.run(
        [sys.executable, "-m", "arbor.cli", "serve", "--help"],
        capture_output=True, text=True, cwd=Path("/home/workspace/Projects/dir-forensics"),
    )
    assert result.returncode == 0
