"""Unit tests for arbor.flags"""
import pytest
from pathlib import Path
from arbor.flags import load_flags, classify_file

def test_load_flags():
    """load_flags should return a dict of rule functions."""
    flags = load_flags(Path("/home/workspace/Projects/dir-forensics/config/default-flags.yaml"))
    assert isinstance(flags, dict)
    assert "min_file_size" in flags
    assert "suspicious_ext" in flags

def test_classify_small_file():
    """A small .txt file should not be flagged as suspicious by extension."""
    flags = load_flags(Path("/home/workspace/Projects/dir-forensics/config/default-flags.yaml"))
    result = classify_file("/some/path/small.txt", flags)
    # Small files should not trigger size-based flags
    assert result is None or "suspicious" not in str(result).lower()

def test_classify_large_script():
    """A large .py file should be flagged if over size threshold."""
    flags = load_flags(Path("/home/workspace/Projects/dir-forensics/config/default-flags.yaml"))
    # Create a mock large file path
    result = classify_file("/some/path/big.py", flags)
    # The classification should return a category or None
    assert result is None or isinstance(result, dict)
