# AGENTS.md — dir-forensics

Generic metadata-only directory forensics pipeline. Config-driven, no file contents.

## Architecture

```
inventory.json (Apache crawl / local walk / synthetic demo)
        │
        ├── ingest    → DuckDB
        ├── analyze   → tree, depth, extensions, duplicates, stats
        ├── flags     → security-flag classification (config-driven rules)
        ├── tier0     → dedup collapse + LLM request budget
        └── serve     → interactive web dashboard (stdlib HTTP server)
```

## Key Modules

| Module | Purpose |
|--------|---------|
| `dirforensics/config.py` | `CaseConfig` dataclass + YAML loader |
| `dirforensics/inventory.py` | Canonical inventory loading, normalization, DuckDB ingest |
| `dirforensics/analyzers.py` | Structural analysis (tree, depth, ext, dupes, stats) |
| `dirforensics/flags.py` | Config-driven security-flag classification |
| `dirforensics/tier0.py` | Dedup collapse + request budget estimation |
| `dirforensics/listing.py` | Apache `<pre>` autoindex parser |
| `dirforensics/demo.py` | Synthetic data generator (zero-setup demo) |
| `dirforensics/serve.py` | HTTP server + viewer dashboard |
| `dirforensics/adapters/apache_listing.py` | Async BFS crawler (Tor/HTTP) |
| `dirforensics/adapters/local_fs.py` | Local filesystem walker |
| `dirforensics/cli.py` | CLI entry point |

## Case Configs

- `cases/demo.yaml` — Zero-setup demo (generates synthetic data, runs full pipeline)

## Conventions

- Metadata only. No PII, no file contents.
- First match wins for flags (a file gets exactly one category).
- All output goes to `<output_dir>/<case>-<artifact>.json`.
- Viewer assets are bundled in `dirforensics/viewer/` and served by `serve.py`.

## CLI

```bash
python -m dirforensics.cli <command> <case.yaml> [--verbose] [--port PORT]
# commands: demo, ingest, analyze, flags, tier0, all, serve
```
