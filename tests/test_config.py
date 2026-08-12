"""Unit tests for arbor config"""
import pytest
from pathlib import Path
from arbor.config import CaseConfig

def test_case_config_defaults():
    """A CaseConfig with no args should have defaults."""
    cfg = CaseConfig()
    assert cfg.name == "default"
    assert cfg.inventory is None
    assert cfg.flags_source is None

def test_case_config_from_yaml():
    """Load a real YAML case config."""
    cfg = CaseConfig.from_yaml(Path("cases/demo.yaml"))
    assert cfg.name == "demo"
    assert cfg.inventory is not None
    assert cfg.flags_source == "default"

def test_case_config_flags_source_default():
    """flags_source: default should auto-load default-flags.yaml."""
    cfg = CaseConfig.from_yaml(Path("cases/demo.yaml"))
    assert cfg.flags_source == "default"
    # The default flags file should exist and be loadable
    from arbor.flags import load_flags
    flags = load_flags(Path.cwd() / "config" / "default-flags.yaml")
    assert "min_file_size" in flags
