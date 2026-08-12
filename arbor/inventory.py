"""Canonical inventory loading + DuckDB ingestion.

Canonical inventory contract (what every adapter/crawler produces):

    {
      "depth": 15,                       # optional: max crawl depth
      "dirs": ["", "a/", "a/b/"],        # directory relpaths, trailing /
      "files": {                         # relpath -> metadata dict
        "a/b/report.pdf": {
          "name": "report.pdf",          # optional (defaults to basename)
          "size": "1234",                # optional: string or int
          "url": "...",                  # optional: source URL
          "decoded_url": "...",          # optional
          ...                            # any extra fields pass through
        }
      },
      "stats": {"dirs": 3, "files": 1}   # optional: precomputed counts
    }
"""

from __future__ import annotations

import json
import re
import urllib.parse
from pathlib import Path

_SIZE_TOKEN = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*([kmgt]?i?b?)?\s*$", re.IGNORECASE
)
_MULT = {"": 1, "b": 1, "kb": 1000, "kib": 1024, "k": 1000,
         "mb": 1000**2, "mib": 1024**2, "m": 1000**2,
         "gb": 1000**3, "gib": 1024**3, "g": 1000**3,
         "tb": 1000**4, "tib": 1024**4, "t": 1000**4}


def load_inventory(path: str | Path) -> dict:
    with open(path) as f:
        return json.load(f)


def file_size(meta: dict) -> int:
    """Best-effort byte size from a file metadata dict."""
    for key in ("size_bytes", "size"):
        v = meta.get(key)
        if v is None:
            continue
        if isinstance(v, (int, float)):
            return int(v)
        s = str(v).strip()
        if s.isdigit():
            return int(s)
        m = _SIZE_TOKEN.match(s)
        if m:
            return int(float(m.group(1)) * _MULT.get(m.group(2).lower() or "", 1))
    return 0


def parse_size_token(token: str) -> int | None:
    """Parse an Apache-style size token ('123K', '1.5M', '4.2G', '723')."""
    m = _SIZE_TOKEN.match(token or "")
    if not m:
        return None
    return int(float(m.group(1)) * _MULT.get(m.group(2).lower() or "", 1))


def extension_of(name: str) -> str:
    if "." in name:
        return name.rsplit(".", 1)[-1].lower()
    return "(none)"


def top_dir_of(relpath: str) -> str:
    for part in relpath.split("/"):
        if part:
            return part
    return ""


def parent_of(relpath: str) -> str:
    """Directory part of a file relpath ('' when the file sits at root)."""
    idx = relpath.rfind("/")
    return relpath[:idx] if idx >= 0 else ""


def normalize_inventory(data: dict) -> dict:
    """Coerce a raw inventory dict to the canonical shape (in place)."""
    data.setdefault("dirs", [])
    data.setdefault("files", {})
    data.setdefault("stats", {})
    files = data["files"]
    for relpath, meta in files.items():
        if not isinstance(meta, dict):
            meta = {"size": meta}
            files[relpath] = meta
        meta.setdefault("name", relpath.rsplit("/", 1)[-1])
        meta.setdefault("url", "")
        meta.setdefault("decoded_url", urllib.parse.unquote(meta["url"]))
    data["stats"].setdefault("dirs", len(data["dirs"]))
    data["stats"].setdefault("files", len(files))
    return data


def ingest_duckdb(cfg, data: dict) -> None:
    """Load canonical inventory into the case DuckDB (dirs + files tables).

    Schema is adapter-agnostic so any crawler output works.
    """
    import duckdb

    db_path = cfg.duckdb or (cfg.output_dir / f"{cfg.case}.duckdb")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    conn.execute("DROP TABLE IF EXISTS dirs")
    conn.execute("DROP TABLE IF EXISTS files")
    conn.execute(
        """CREATE TABLE dirs(
            relpath VARCHAR, top_dir VARCHAR, depth INTEGER)"""
    )
    conn.execute(
        """CREATE TABLE files(
            "name" VARCHAR, "extension" VARCHAR, parent_relpath VARCHAR,
            top_dir VARCHAR, depth INTEGER, url VARCHAR, decoded_url VARCHAR,
            size_known BOOLEAN, size_bytes BIGINT)"""
    )

    dir_rows = []
    for d in data["dirs"]:
        dir_rows.append((d, top_dir_of(d), d.count("/")))
    conn.executemany("INSERT INTO dirs VALUES (?,?,?)", dir_rows)

    file_rows = []
    for relpath, meta in data["files"].items():
        sz = file_size(meta)
        name = meta.get("name", relpath.rsplit("/", 1)[-1])
        file_rows.append((
            name,
            extension_of(name),
            parent_of(relpath),
            top_dir_of(relpath),
            relpath.count("/"),
            meta.get("url", ""),
            meta.get("decoded_url", ""),
            "size" in meta or "size_bytes" in meta,
            sz,
        ))
    conn.executemany("INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?)", file_rows)
    conn.close()

    print(f"[ingest] {len(dir_rows):,} dirs, {len(file_rows):,} files -> {db_path}")
