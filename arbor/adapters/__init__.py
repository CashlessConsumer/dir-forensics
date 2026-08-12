"""Adapters that turn a directory source into a canonical inventory JSON.

Each adapter emits the canonical contract consumed by the analyzers:
    {"depth": int, "dirs": [...], "files": {relpath: meta}, "stats": {...}}
"""
