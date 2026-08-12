#!/usr/bin/env python3
"""arbor — generic metadata-only directory forensics pipeline.

A case is defined by a YAML config. The CLI runs stages in order:
    demo     → generate synthetic data + run full pipeline (zero setup)
    ingest   → load inventory + write DuckDB
    analyze  → tree, depth, extensions, duplicates, stats (5 artifacts)
    flags    → config-driven security-flag classification
    tier0    → logical-file collapse (dedupe ~24x → 1x)
    all      → ingest + analyze + flags + tier0
    serve    → local web viewer (interactive dashboard)

Every analyzer reads ONLY the canonical inventory JSON (never file contents).
Outputs land in <output_dir>/<case>-<artifact>.json.

Usage:
    python -m arbor.cli demo cases/demo.yaml     # zero-setup: generate data + analyze
    python -m arbor.cli all cases/my-case.yaml
    python -m arbor.cli serve cases/demo.yaml --port 8765
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from .config import CaseConfig
from .inventory import load_inventory, ingest_duckdb
from .analyzers import build_tree, build_depth, build_extensions, build_duplicates, build_stats
from .flags import flags_all
from .tier0 import tier0_all


def _stage(label: str, fn, verbose: bool):
    t0 = time.time()
    result = fn()
    dt = time.time() - t0
    if verbose:
        if isinstance(result, Path):
            print(f"  ✓ {label:12s} {dt:5.2f}s  → {result}")
        else:
            print(f"  ✓ {label:12s} {dt:5.2f}s")
    return result


def cmd_ingest(cfg: CaseConfig, verbose: bool = False) -> Path:
    def _do():
        data = load_inventory(cfg.inventory)
        ingest_duckdb(cfg, data)
        return cfg.duckdb
    return _stage("ingest", _do, verbose)


def cmd_analyze(cfg: CaseConfig, verbose: bool = False) -> list[Path]:
    def _do():
        data = load_inventory(cfg.inventory)
        paths = [
            build_tree(cfg, data),
            build_depth(cfg, data),
            build_extensions(cfg, data),
            build_duplicates(cfg, data),
            build_stats(cfg, data),
        ]
        return paths
    return _stage("analyze", _do, verbose)


def cmd_flags(cfg: CaseConfig, verbose: bool = False) -> Path:
    return _stage("flags", lambda: flags_all(cfg), verbose)


def cmd_tier0(cfg: CaseConfig, verbose: bool = False) -> Path:
    return _stage("tier0", lambda: tier0_all(cfg), verbose)


def cmd_all(cfg: CaseConfig, verbose: bool = False):
    print(f"[arbor] case: {cfg.case}")
    cmd_ingest(cfg, verbose)
    cmd_analyze(cfg, verbose)
    cmd_flags(cfg, verbose)
    cmd_tier0(cfg, verbose)
    print(f"[arbor] done → {cfg.output_dir}/")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="arbor",
        description="Generic metadata-only directory forensics pipeline",
    )
    ap.add_argument("command", choices=["demo", "ingest", "analyze", "flags", "tier0", "all", "serve"])
    ap.add_argument("config", help="path to case YAML/JSON config")
    ap.add_argument("-v", "--verbose", action="store_true", help="print per-stage timings")
    ap.add_argument("--port", type=int, default=8765, help="port for serve command (default: 8765)")
    args = ap.parse_args(argv)

    cfg = CaseConfig.load(Path(args.config))

    if args.command == "demo":
        from .demo import generate
        data = generate()
        os.makedirs(os.path.dirname(str(cfg.inventory)) or ".", exist_ok=True)
        with open(cfg.inventory, "w") as f:
            json.dump(data, f, separators=(",", ":"))
        print(f"[demo] {data['stats']['files']:,} files / {data['stats']['dirs']:,} dirs → {cfg.inventory}")
        cmd_all(cfg, args.verbose)
    elif args.command == "ingest":
        cmd_ingest(cfg, args.verbose)
    elif args.command == "analyze":
        cmd_analyze(cfg, args.verbose)
    elif args.command == "flags":
        cmd_flags(cfg, args.verbose)
    elif args.command == "tier0":
        cmd_tier0(cfg, args.verbose)
    elif args.command == "all":
        cmd_all(cfg, args.verbose)
    elif args.command == "serve":
        from .serve import serve
        return serve(cfg.output_dir, cfg.case, args.port)

    return 0


if __name__ == "__main__":
    sys.exit(main())
