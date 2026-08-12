"""Unit tests for arbor.analyzers"""
import pytest
from pathlib import Path
from arbor.analyzers import build_tree, build_depth, build_extensions, build_duplicates, build_stats

def test_build_tree():
    """build_tree from a tiny inventory dict."""
    inv = {
        "root": "/test",
        "files": [
            {"name": "a.txt", "size": 50, "ext": ".txt"},
            {"name": "b.py", "size": 200, "ext": ".py"},
            {"name": "c.txt", "size": 30, "ext": ".txt"},
        ],
        "dirs": [
            {"name": "sub", "files": [{"name": "d.txt", "size": 10, "ext": ".txt"}], "dirs": []},
        ],
    }
    tree = build_tree(inv)
    assert tree[0] == "/test"  # root name
    # Should have 3 top-level files + 1 in subdir
    leaf_names = [n for n, _, _ in tree[1]] if len(tree) > 1 else []
    assert "a.txt" in leaf_names

def test_build_depth():
    """build_depth should compute max depth and level stats."""
    inv = {
        "root": "/test",
        "files": [{"name": "a.txt", "size": 10}],
        "dirs": [
            {"name": "d1", "files": [], "dirs": [{"name": "d2", "files": [], "dirs": []}]},
        ],
    }
    depth = build_depth(inv)
    assert depth["max_depth"] == 2  # root -> d1 -> d2
    assert len(depth["levels"]) == 3  # depth 0, 1, 2

def test_build_extensions():
    """build_extensions should count by extension."""
    inv = {
        "root": "/test",
        "files": [
            {"name": "a.txt", "size": 10},
            {"name": "b.py", "size": 20},
            {"name": "c.txt", "size": 5},
        ],
        "dirs": [],
    }
    ext = build_extensions(inv)
    assert ext["total_extensions"] == 2  # .txt and .py
    assert ext["extensions"][".txt"]["count"] == 2
    assert ext["extensions"][".py"]["count"] == 1

def test_build_duplicates():
    """build_duplicates should identify duplicate keys."""
    inv = {
        "root": "/test",
        "files": [
            {"name": "a.txt", "path": "/t/a.txt"},
            {"name": "b.txt", "path": "/t/b.txt"},
            {"name": "c.txt", "path": "/t/c.txt"},
        ],
        "dirs": [],
    }
    # Files with same extension but different names -> no duplicates by name
    dup = build_duplicates(inv)
    assert dup["total_dupe_keys"] == 0  # all filenames differ

def test_build_stats():
    """build_stats should compute summary numbers."""
    inv = {
        "root": "/test",
        "files": [
            {"name": "a.txt", "size": 100},
            {"name": "b.py", "size": 200},
        ],
        "dirs": [{"name": "d1", "files": [{"name": "c.txt", "size": 50}], "dirs": []}],
    }
    stats = build_stats(inv)
    assert stats["total_files"] == 3
    assert stats["total_bytes"] == 350
    assert stats["total_dirs"] == 1
