"""Unit tests for arbor.config — CaseConfig loading and defaults."""
import pytest
from pathlib import Path
from arbor.config import CaseConfig

@pytest.mark.parametrize("config_path", [
    Path("/home/workspace/Projects/dir-forensics/cases/demo.yaml"),
])
def test_case_config_loads(config_path):
    """CaseConfig.load() should succeed on a valid YAML config."""
    cfg = CaseConfig.load(str(config_path))
    # Case name comes from the YAML's 'case:' field
    assert cfg.case == "acme-demo"
    # Label auto-resolves from the YAML source section
    assert cfg.label == "acme-corp.example.org"
    assert cfg.inventory is not None
    assert cfg.output_dir is not None
    # Default flags should be loaded when flags_source: default
    assert len(cfg.flag_rules) > 0

def test_case_config_has_default_flags():
    """When flags_source: default is set, default-flags.yaml rules are loaded."""
    cfg = CaseConfig.load(str(Path("/home/workspace/Projects/dir-forensics/cases/demo.yaml")))
    assert len(cfg.flag_rules) > 0
