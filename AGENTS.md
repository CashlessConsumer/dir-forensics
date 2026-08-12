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
| `arbor/config.py` | `CaseConfig` dataclass + YAML loader |
| `arbor/inventory.py` | Canonical inventory loading, normalization, DuckDB ingest |
| `arbor/analyzers.py` | Structural analysis (tree, depth, ext, dupes, stats) |
| `arbor/flags.py` | Config-driven security-flag classification |
| `arbor/tier0.py` | Dedup collapse + request budget estimation |
| `arbor/listing.py` | Apache `<pre>` autoindex parser |
| `arbor/demo.py` | Synthetic data generator (zero-setup demo) |
| `arbor/serve.py` | HTTP server + viewer dashboard |
| `arbor/adapters/apache_listing.py` | Async BFS crawler (Tor/HTTP) |
| `arbor/adapters/local_fs.py` | Local filesystem walker |
| `arbor/cli.py` | CLI entry point |

## Case Configs

- `cases/demo.yaml` — Zero-setup demo (generates synthetic data, runs full pipeline)

## Conventions

- Metadata only. No PII, no file contents.
- First match wins for flags (a file gets exactly one category).
- All output goes to `<output_dir>/<case>-<artifact>.json`.
- Viewer assets are bundled in `arbor/viewer/` and served by `serve.py`.

## CLI

```bash
python -m arbor.cli <command> <case.yaml> [--verbose] [--port PORT]
# commands: demo, ingest, analyze, flags, tier0, all, serve
```
