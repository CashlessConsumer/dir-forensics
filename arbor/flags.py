"""Config-driven security-flag classification over the inventory.

Config-driven security-flag engine: flag rules
live in the case config (`flags:` list) instead of being hardcoded, and the
input is the canonical inventory JSON rather than the crawl DuckDB.

Match semantics per rule (config order, first match wins):
  1. If any `exclude_path` substring is in the lowercase relpath -> rule skipped
  2. If rule has `ext` and the file extension is in it -> match
  3. If rule has `names` and any substring is in the lowercase filename -> match

Output shape:
  {total, categories: {flag: {count, severity, color}}, files: [...]}
"""

from __future__ import annotations

import json
import time
from collections import Counter

from .inventory import extension_of, load_inventory, normalize_inventory, top_dir_of


def _match(rule, name_l: str, ext: str, path_l: str):
    if any(x in path_l for x in rule.exclude_path):
        return False
    if rule.extensions and ext in rule.extensions:
        return True
    if rule.names:
        for n in rule.names:
            if n in name_l:
                return True
    return False


def build_flags(cfg, data: dict) -> str:
    items = []
    for relpath, meta in data["files"].items():
        name = meta.get("name", relpath.rsplit("/", 1)[-1])
        ext = extension_of(name)
        path_l = relpath.lower()
        name_l = name.lower()
        for rule in cfg.flag_rules:
            if _match(rule, name_l, ext, path_l):
                items.append({
                    "name": name,
                    "ext": ext,
                    "flag": rule.id,
                    "severity": rule.severity,
                    "color": rule.color,
                    "top_dir": top_dir_of(relpath),
                    "path": relpath,
                    "url": meta.get("url", ""),
                })
                break

    summary = Counter(i["flag"] for i in items)
    rule_by_id = {r.id: r for r in cfg.flag_rules}
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total": len(items),
        "categories": {
            f: {"count": c, "severity": rule_by_id[f].severity, "color": rule_by_id[f].color}
            for f, c in summary.most_common()
        },
        "files": items,
    }
    path = cfg.output_dir / f"{cfg.case}-flags.json"
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"[flags] {len(items):,} flagged files across {len(summary)} categories -> {path}")
    for flag, c in summary.most_common():
        print(f"    {flag}: {c}")
    return str(path)


def flags_all(cfg) -> str:
    data = normalize_inventory(load_inventory(cfg.inventory))
    return build_flags(cfg, data)
