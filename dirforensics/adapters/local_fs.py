"""Adapter: walk a local directory tree into a canonical inventory JSON.

Metadata-only: relpath, name, size, mtime. Never reads file contents.

Usage:
    python -m dirforensics.adapters.local_fs <dir> --out inventory.json \
        [--url-base https://example.com/root] [--max-depth N]

The --url-base option attaches synthetic source URLs (useful when the local
tree is a mirror of a live listing, e.g. a downloaded dump).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path


def walk_to_inventory(root: str, url_base: str = "", max_depth: int | None = None) -> dict:
    root = os.path.abspath(root)
    dirs: list[str] = [""]
    files: dict[str, dict] = {}
    max_d = 0

    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if max_depth is not None and depth > max_depth:
            dirnames[:] = []
            continue
        if rel != ".":
            dirs.append(rel.replace(os.sep, "/") + "/")
        max_d = max(max_d, depth)

        for fn in filenames:
            fpath = os.path.join(dirpath, fn)
            rp = os.path.relpath(fpath, root).replace(os.sep, "/")
            try:
                st = os.stat(fpath)
                size = st.st_size
                mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
            except OSError:
                size, mtime = 0, ""
            meta: dict = {"name": fn, "size": size}
            if mtime:
                meta["mtime"] = mtime
            if url_base:
                meta["url"] = url_base.rstrip("/") + "/" + urllib.parse.quote(rp)
                meta["decoded_url"] = url_base.rstrip("/") + "/" + rp
            files[rp] = meta

    return {
        "depth": max_d,
        "dirs": sorted(dirs),
        "files": dict(sorted(files.items())),
        "stats": {"dirs": len(dirs), "files": len(files)},
    }


def scan_directory(root: str, out: Path, url_base: str = "", max_depth: int | None = None) -> None:
    """Scan directory and write inventory JSON. Used by CaseConfig auto-scan."""
    data = walk_to_inventory(root, url_base, max_depth)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[local_fs] scanned {data['stats']['files']:,} files / {data['stats']['dirs']:,} dirs -> {out}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Walk a local directory into a canonical inventory JSON")
    ap.add_argument("dir", help="directory to walk")
    ap.add_argument("--out", required=True, help="output inventory JSON path")
    ap.add_argument("--url-base", default="", help="optional base URL to synthesize file URLs from")
    ap.add_argument("--max-depth", type=int, default=None, help="only walk up to this depth")
    args = ap.parse_args(argv)

    data = walk_to_inventory(args.dir, args.url_base, args.max_depth)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(data, f, indent=2)
    print(f"scanned {data['stats']['files']:,} files / {data['stats']['dirs']:,} dirs -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
