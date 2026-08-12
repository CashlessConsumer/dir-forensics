"""Unit tests for arbor.flags"""
import pytest
from pathlib import Path
from arbor.flags import build_flags, flags_all

def test_build_flags_with_real_config():
    """build_flags should process an inventory and write output JSON."""
    from arbor.config import CaseConfig
    cfg = CaseConfig(
        case="test",
        inventory=Path("/home/workspace/Projects/dir-forensics/cases/demo.yaml"),
        output_dir=Path("/tmp/test-flag-output"),
        flag_rules=[],
    )
    # Minimal inventory structure
    from arbor.inventory import normalize_inventory, load_inventory
    inv = load_inventory(Path("/home/workspace/Projects/dir-forensics/tests/data/demo_inventory_small.json"))
    data = normalize_inventory(inv)
    path = build_flags(cfg, data)
    assert Path(path).exists()
    import json
    with open(path) as f:
        out = json.load(f)
    assert "categories" in out
    assert "files" in out

def test_flags_all_uses_inventory():
    """flags_all should process inventory via config."""
    from arbor.config import CaseConfig
    cfg = CaseConfig(
        case="test",
        inventory=Path("/home/workspace/Projects/dir-forensics/cases/demo.yaml"),
        output_dir=Path("/tmp/test-flag-output2"),
        flag_rules=[],
    )
    result = flags_all(cfg)
    assert isinstance(result, str)
    import json
    # result should be a JSON string path
    assert "categories" in result or Path(result).exists()
