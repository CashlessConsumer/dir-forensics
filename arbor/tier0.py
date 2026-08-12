"""Tier 0 — deterministic normalization: collapse the raw inventory into a
minimal "logical file universe" BEFORE any LLM summarization.

Logical-file collapse (same dedup approach, same grouping, same output
shape). Removes:

  1. Exact duplicates   (same basename + same byte size)
  2. Timestamp/branch copies (same semantic basename differing only by a
     date stamp, version marker, tenant/branch id, or trailing digits)

Output: <case>-tier0.json
  {generated_at, method, stats, exact_dupe_groups, near_dupe_groups,
   request_budget_rows_per_request, top_near_dupe_keys}

Metadata-only. No PII, no file contents.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict

from .inventory import file_size, load_inventory

TS_PATS = [
    re.compile(r"[-_\s]?\d{4}[-_]\d{2}[-_]\d{2}"),   # 2025-03-14 / 2025_03_14
    re.compile(r"[-_\s]?\d{8}"),                      # 20250314
    re.compile(r"[-_\s]?\d{6}"),                      # 250314
    re.compile(r"[_\- ]?v\d{1,2}(\.\d{1,2})*", re.I),  # _v2, -v1.2
    re.compile(r"[\s(]*\d{1,3}[\s)]*$"),              # trailing (2), 3, 12
    re.compile(r"[_\- ]?(copy|backup|bk|bak|orig|final|new|old|sent|rev|updated|latest|draft|temp|tmp)", re.I),
    re.compile(r"[_\- ]+\d{1,6}[_\- ]?$"),            # trailing _123456 / branch codes
]
BRANCH_CODE = re.compile(r"[_\- ]?b\d{2,6}[_\- ]?$", re.I)  # _B12345 / -b2345678


def normalize_key(relpath: str) -> str:
    """Fold a path to a canonical 'logical file' key (no extension, no size)."""
    base = os.path.basename(relpath)
    stem, _ = os.path.splitext(base)
    s = stem.lower()
    for pat in TS_PATS + [BRANCH_CODE]:
        s = pat.sub("", s)
    s = re.sub(r"\s+", "", s)
    s = s.strip(" _-")
    return s or base.lower()


def build_logical_files(cfg, data: dict) -> tuple[dict, dict, list]:
    """Deterministic tier-0 collapse: return (logical_files, stats,
    top_near_dupe_keys). Shared by tier0_all() and any tier1/tier2 LLM
    runner so the summarized universe never drifts."""
    files = {rp: file_size(m) for rp, m in data["files"].items()}
    raw_dirs = len(data["dirs"])
    n_raw = len(files)
    total_bytes_raw = sum(files.values())

    exact = defaultdict(list)
    for relpath, size in files.items():
        exact[(os.path.basename(relpath).lower(), size)].append(relpath)
    exact_groups = [g for g in exact.values() if len(g) > 1]
    exact_bytes = sum(files[g[0]] * (len(g) - 1) for g in exact_groups)

    dropped_exact: set[str] = set()
    for g in exact_groups:
        dropped_exact.update(g[1:])

    remaining = {rp: sz for rp, sz in files.items() if rp not in dropped_exact}
    near = defaultdict(list)
    for relpath, size in remaining.items():
        near[normalize_key(relpath)].append(relpath)
    near_groups = [g for g in near.values() if len(g) > 1]

    dropped_near: set[str] = set()
    for g in near_groups:
        dropped_near.update(g[1:])

    logical = {rp: sz for rp, sz in remaining.items() if rp not in dropped_near}
    n_logical = len(logical)
    logical_bytes = sum(logical.values())

    stats = {
        "raw_files": n_raw,
        "raw_dirs": raw_dirs,
        "raw_bytes": total_bytes_raw,
        "exact_dupe_files_dropped": len(dropped_exact),
        "exact_dupe_bytes_wasted": exact_bytes,
        "near_dupe_files_dropped": len(dropped_near),
        "total_dropped": n_raw - n_logical,
        "logical_files": n_logical,
        "logical_bytes": logical_bytes,
        "reduction_pct": round(100 * (n_raw - n_logical) / n_raw, 2) if n_raw else 0.0,
        "exact_dupe_groups": len(exact_groups),
        "near_dupe_groups": len(near_groups),
    }
    top_near_dupe_keys = [
        {"key": k, "variants": len(g)}
        for k, g in sorted(near.items(), key=lambda x: -len(x[1]))[:25]
    ]
    return logical, stats, top_near_dupe_keys


def tier0_all(cfg) -> str:
    from .inventory import normalize_inventory

    data = normalize_inventory(load_inventory(cfg.inventory))
    logical, stats, top_near_dupe_keys = build_logical_files(cfg, data)
    n_logical = stats["logical_files"]

    request_budget = {}
    for batch in (50, 100, 200, 500, 1000):
        request_budget[str(batch)] = -(-n_logical // batch)  # ceil

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "method": "arbor.tier0",
        "stats": stats,
        "exact_dupe_groups": stats["exact_dupe_groups"],
        "near_dupe_groups": stats["near_dupe_groups"],
        "request_budget_rows_per_request": request_budget,
        "top_near_dupe_keys": top_near_dupe_keys,
    }

    path = cfg.output_dir / f"{cfg.case}-tier0.json"
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=1)

    s = stats
    print(f"[tier0] raw {s['raw_files']:,} files / {s['raw_dirs']:,} dirs / {s['raw_bytes']/1e9:.1f} GB")
    print(f"        exact dupes: {s['exact_dupe_files_dropped']:,} dropped ({s['exact_dupe_bytes_wasted']/1e9:.1f} GB wasted)")
    print(f"        near dupes : {s['near_dupe_files_dropped']:,} dropped")
    print(f"        LOGICAL    : {s['logical_files']:,} ({s['reduction_pct']:.1f}% reduction)")
    print(f"        budget     : {payload['request_budget_rows_per_request']}")
    print(f"        -> {path}")
    return str(path)
