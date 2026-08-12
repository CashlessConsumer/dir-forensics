"""Unit tests for arbor.inventory"""
import pytest
from pathlib import Path
from arbor.inventory import load_inventory, normalize_inventory

def test_load_inventory_known_path():
    """Load the real inventory-L15 and verify structure."""
    inv = load_inventory(Path("/home/workspace/BoBHack/crawler/inventories/inventory-L15.json"))
    assert inv["root"] == "/home/workspace/BoBHack/crawler"
    assert "files" in inv
    assert "dirs" in inv

def test_normalize_inventory_roundtrip():
    """normalize_inventory should preserve keys and types."""
    from arbor.inventory import normalize_inventory
    raw = {"root": "/test", "files": [{"name": "a", "size": 100}], "dirs": [{"name": "d", "files": 5}]}
    norm = normalize_inventory(raw)
    assert norm["root"] == "/test"
    assert len(norm["files"]) == 1
    assert norm["files"][0]["name"] == "a"

def test_normalize_inventory_empty():
    """Empty/invalid input should not crash."""
    norm = normalize_inventory({})
    assert norm == {}
