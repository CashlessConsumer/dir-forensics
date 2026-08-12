"""Case configuration: what defines one directory-forensics run.

A case is defined entirely by a YAML/JSON config file, so the same pipeline
can be pointed at any inventory (an Apache directory listing, an S3 bucket index, a local mirror,
another leak dump) without touching code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


@dataclass
class FlagRule:
    """One red-flag rule. Match semantics:

    1. If any `exclude_path` substring is in the lowercase relpath, the rule
       is skipped entirely for that file (e.g. Python310/site-packages).
    2. If `ext` is non-empty and the file extension is in it -> match.
    3. If `names` is non-empty and any substring is in the lowercase name -> match.
    Rules are evaluated in config order; the first match wins.
    """

    id: str
    severity: str = "medium"
    color: str = "#94a3b8"
    extensions: list[str] = field(default_factory=list)
    names: list[str] = field(default_factory=list)
    exclude_path: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "FlagRule":
        return cls(
            id=d.get("id", d.get("flag", "rule")),
            severity=d.get("severity", "medium"),
            color=d.get("color", "#94a3b8"),
            extensions=[e.lower().lstrip(".") for e in d.get("ext", [])],
            names=[n.lower() for n in d.get("names", [])],
            exclude_path=[p.lower() for p in d.get("exclude_path", [])],
        )


@dataclass
class CaseConfig:
    case: str
    label: str  # root node label in the tree, e.g. "example.com"
    inventory: Path  # canonical inventory JSON — the single source of truth
    output_dir: Path
    duckdb: Path | None = None
    flag_rules: list[FlagRule] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "CaseConfig":
        path = Path(path).resolve()
        raw = cls._read(path)
        base = path.parent
        case = raw["case"]

        # ── inventory: either explicit path or auto-generated from source ──
        inventory, label = cls._resolve_inventory(raw, base, path)

        # ── output dir: flat or nested ──
        out_raw = raw.get("output_dir") or raw.get("output", {}).get("dir", f"cases/{case}")
        output_dir = cls._resolve(out_raw, base)

        # ── flags: explicit list, defaults file, or none ──
        flag_rules = [FlagRule.from_dict(r) for r in raw.get("flags", [])]
        if not flag_rules and raw.get("flags_source") == "default":
            flag_rules = cls._load_default_flags(path)

        cfg = cls(
            case=case,
            label=label,
            inventory=inventory,
            output_dir=output_dir,
            flag_rules=flag_rules,
            metadata=raw.get("metadata", {}),
        )

        duckdb_raw = raw.get("duckdb") or raw.get("output", {}).get("duckdb")
        if duckdb_raw:
            cfg.duckdb = cls._resolve(duckdb_raw, base)
        return cfg

    @classmethod
    def _resolve_inventory(cls, raw: dict, base: Path, cfg_path: Path) -> tuple[Path, str]:
        """Return (inventory_path, label). Auto-scans if source.type == local_fs."""
        if raw.get("inventory"):
            label = raw.get("label", raw["case"])
            return cls._resolve(raw["inventory"], base), label

        source = raw.get("source")
        if not source:
            raise ValueError("config needs either 'inventory:' or 'source:' with a type")

        stype = source.get("type", "")
        spath = source.get("path", "")
        label = raw.get("label", Path(spath).name)

        if stype == "local_fs":
            scan_path = cls._resolve(spath, base)
            inv_out = base / f".inventory-cache" / f"{raw['case']}.json"
            inv_out.parent.mkdir(parents=True, exist_ok=True)
            from .adapters.local_fs import scan_directory
            scan_directory(scan_path, inv_out, url_base=source.get("url_base"))
            return inv_out, label

        raise ValueError(f"unsupported source type: {stype!r}")

    @classmethod
    def _load_default_flags(cls, cfg_path: Path) -> list[FlagRule]:
        """Load config/default-flags.yaml relative to the project root."""
        for candidate in (cfg_path.parent.parent / "config" / "default-flags.yaml",
                          cfg_path.parent / "default-flags.yaml"):
            if candidate.exists():
                if yaml:
                    raw = yaml.safe_load(candidate.read_text()) or {}
                else:
                    raw = json.loads(candidate.read_text())
                return [FlagRule.from_dict(r) for r in raw.get("flags", [])]
        return []

    @staticmethod
    def _read(path: Path) -> dict:
        if path.suffix in (".yaml", ".yml"):
            if yaml is None:
                raise RuntimeError("PyYAML required: pip install pyyaml")
            raw = yaml.safe_load(path.read_text()) or {}
        else:
            raw = json.loads(path.read_text())
        if "case" not in raw:
            raise ValueError(f"config {path} is missing required 'case' key")
        return raw

    @staticmethod
    def _resolve(p: str | Path, base: Path) -> Path:
        p = Path(p)
        return p if p.is_absolute() else (base / p).resolve()
