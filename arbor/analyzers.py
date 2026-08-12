"""Structural analyzers: tree, depth, extensions, duplicates, stats.

Every analyzer reads ONLY the canonical inventory JSON (never file contents)
and writes to <output_dir>/<case>-<artifact>.json. Output shapes are kept
byte-compatible JSON output so dashboard routes
can consume generic output without changes.
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict

from .inventory import extension_of, file_size, top_dir_of


def _artifact(cfg, name: str) -> str:
    return str(cfg.output_dir / f"{cfg.case}-{name}.json")


def _write(path: str, payload: dict) -> None:
    from pathlib import Path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, separators=(",", ":"))


def build_tree(cfg, data: dict) -> str:
    """Compact tree: [name, file_count, total_bytes, children[]]."""
    dirs = data["dirs"]
    files = data["files"]
    stats = data["stats"]

    root = {"c": {}, "f": 0, "b": 0, "d": True}
    for d in dirs:
        node = root
        for p in [x for x in d.split("/") if x]:
            node = node["c"].setdefault(p, {"c": {}, "f": 0, "b": 0, "d": True})
        node["d"] = True

    for path, meta in files.items():
        parts = [p for p in path.split("/") if p]
        leaf = root
        for p in parts:
            leaf = leaf["c"].setdefault(p, {"c": {}, "f": 0, "b": 0, "d": False})
        leaf["f"] += 1
        leaf["b"] += file_size(meta)

    def sum_node(node):
        f, b = node["f"], node["b"]
        for child in node["c"].values():
            f2, b2 = sum_node(child)
            f += f2
            b += b2
        node["f"], node["b"] = f, b
        return f, b

    sum_node(root)

    def to_node(name, node):
        children = [to_node(k, v) for k, v in node["c"].items()]
        children.sort(key=lambda c: (-c[1], c[0].lower()))
        return [name, node["f"], node["b"], children]

    tree = to_node(cfg.label, root)

    out = {
        "source": str(cfg.inventory.name),
        "depth": data.get("depth"),
        "stats": {"dirs": stats["dirs"], "files": stats["files"]},
        "total_bytes": root["b"],
        "bytes_from_files": len(files),
        "tree": tree,
    }
    path = _artifact(cfg, "tree")
    _write(path, out)
    print(f"[tree] {stats['dirs']:,} dirs, {stats['files']:,} files, "
          f"{root['b']:,} bytes, top-level: {len(tree[3])} -> {path}")
    return path


def build_depth(cfg, data: dict) -> str:
    depth_stats = defaultdict(lambda: {"files": 0, "bytes": 0, "dirs": 0})
    for d in data["dirs"]:
        depth_stats[d.count("/")]["dirs"] += 1
    for path, meta in data["files"].items():
        depth = path.count("/")
        depth_stats[depth]["files"] += 1
        depth_stats[depth]["bytes"] += file_size(meta)

    out = {"depths": [{"depth": d, **depth_stats[d]} for d in sorted(depth_stats)]}
    path = _artifact(cfg, "depth")
    _write(path, out)
    print(f"[depth] {len(out['depths'])} levels -> {path}")
    return path


def build_extensions(cfg, data: dict) -> str:
    ext_stats = defaultdict(lambda: {"files": 0, "bytes": 0})
    for path, meta in data["files"].items():
        ext = extension_of(meta.get("name", path.rsplit("/", 1)[-1]))
        ext_stats[ext]["files"] += 1
        ext_stats[ext]["bytes"] += file_size(meta)

    elist = sorted(ext_stats, key=lambda e: ext_stats[e]["files"], reverse=True)
    out = {
        "total_extensions": len(elist),
        "extensions": [{"ext": e, **ext_stats[e]} for e in elist],
    }
    path = _artifact(cfg, "extensions")
    _write(path, out)
    print(f"[ext] {len(elist)} extensions -> {path}")
    return path


def build_duplicates(cfg, data: dict) -> str:
    by_key = defaultdict(list)
    for path, meta in data["files"].items():
        name = meta.get("name", path.rsplit("/", 1)[-1])
        by_key[(name, file_size(meta))].append(path)

    dupes_list = [
        {"name": name, "size": size, "count": len(paths), "paths": paths[:10]}
        for (name, size), paths in by_key.items() if len(paths) > 1
    ]
    dupes_list.sort(key=lambda d: d["count"], reverse=True)

    total_dupes = sum(d["count"] for d in dupes_list)
    out = {
        "unique_dupe_keys": len(dupes_list),
        "total_dupe_files": total_dupes,
        "wasted_bytes_estimate": sum(d["size"] * (d["count"] - 1) for d in dupes_list),
        "duplicates": dupes_list[:500],
    }
    path = _artifact(cfg, "duplicates")
    _write(path, out)
    print(f"[dupes] {len(dupes_list):,} groups, {total_dupes:,} files, "
          f"{out['wasted_bytes_estimate']:,} bytes wasted -> {path}")
    return path


def build_stats(cfg, data: dict) -> str:
    """Case summary: totals + top directories by files and by bytes."""
    stats = data["stats"]
    total_bytes = sum(file_size(m) for m in data["files"].values())
    total_files = len(data["files"])
    total_dirs = len(data["dirs"])

    dir_bytes = defaultdict(int)
    dir_files = defaultdict(int)
    for path, meta in data["files"].items():
        top = top_dir_of(path)
        dir_bytes[top] += file_size(meta)
        dir_files[top] += 1

    top_by_bytes = sorted(dir_bytes.items(), key=lambda kv: -kv[1])[:25]
    top_by_files = sorted(dir_files.items(), key=lambda kv: -kv[1])[:25]

    out = {
        "case": cfg.case,
        "label": cfg.label,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "stats": {"dirs": total_dirs, "files": total_files, "bytes": total_bytes},
        "depth": data.get("depth"),
        "top_dirs_by_bytes": [{"path": p, "bytes": b, "files": dir_files[p]}
                              for p, b in top_by_bytes],
        "top_dirs_by_files": [{"path": p, "files": c, "bytes": dir_bytes[p]}
                              for p, c in top_by_files],
    }
    path = _artifact(cfg, "stats")
    _write(path, out)
    print(f"[stats] {total_dirs:,} dirs, {total_files:,} files, "
          f"{total_bytes:,} bytes -> {path}")
    return path


def analyze_all(cfg) -> list[str]:
    from .inventory import load_inventory, normalize_inventory

    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    data = normalize_inventory(load_inventory(cfg.inventory))
    paths = [
        build_tree(cfg, data),
        build_depth(cfg, data),
        build_extensions(cfg, data),
        build_duplicates(cfg, data),
        build_stats(cfg, data),
    ]
    return paths
