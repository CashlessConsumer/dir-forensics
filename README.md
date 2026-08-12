# dir-forensics

Generic metadata-only directory forensics pipeline. Point it at any directory tree — a web crawl inventory, a local filesystem, an S3 bucket index — and get structural analysis, duplicate detection, security flags, and dedup budgets. **No file contents are ever read.**

## Quick Start (zero setup)

```bash
git clone https://github.com/cashlessconsumer/dir-forensics.git
cd dir-forensics
pip install -e ".[dev]"

# Generate synthetic data + run full pipeline + launch viewer
python -m dirforensics.cli demo cases/demo.yaml --verbose
python -m dirforensics.cli serve cases/demo.yaml
# → open http://localhost:8765
```

The `demo` command generates ~700 fictional files across a fake corporate directory, runs all analysis stages, and produces 6 JSON artifacts. The `serve` command launches an interactive dashboard.

## What It Does

```
inventory.json (Apache crawl / local walk / synthetic demo)
        │
        ├── ingest    → DuckDB (queryable metadata store)
        ├── analyze   → tree, depth, extensions, duplicates, stats (5 artifacts)
        ├── flags     → security-flag classification (config-driven rules)
        └── tier0     → dedup collapse + LLM request budget estimation
```

Every analyzer reads **only** metadata (filenames, paths, sizes). No file contents, no PII.

## Your Own Data

### Option A: Local directory

```bash
# Scan a local directory into an inventory JSON
python -m dirforensics.adapters.local_fs /path/to/archive --out inventory.json

# Create a case config (copy cases/demo.yaml as template)
cp cases/demo.yaml cases/my-case.yaml
# Edit: set inventory, output_dir, case, label

# Run
python -m dirforensics.cli all cases/my-case.yaml --verbose
python -m dirforensics.cli serve cases/my-case.yaml
```

### Option B: Apache directory listing crawl

For crawling an HTTP server with Apache-style `<pre>` autoindex listings:

```bash
pip install -e ".[crawl]"
python -m dirforensics.adapters.apache_listing \
    --url http://example.org/files/ \
    --max-depth 15 \
    --output inventory.json
```

Supports SOCKS5 proxy (Tor) via `--proxy socks5://127.0.0.1:9050`.

### Option C: Custom adapter

Any tool that produces a JSON file matching the canonical inventory contract works:

```json
{
  "depth": 15,
  "dirs": ["", "folder1", "folder1/subfolder"],
  "files": {
    "folder1/document.pdf": {"name": "document.pdf", "url": "...", "size": "12345"},
    "folder1/subfolder/data.csv": {"name": "data.csv", "url": "...", "size": "6789"}
  },
  "stats": {"dirs": 3, "files": 2}
}
```

## Output Artifacts

| Stage | Files | Description |
|-------|-------|-------------|
| **ingest** | `<case>.duckdb` | Queryable DuckDB with `dirs` and `files` tables |
| **analyze** | `<case>-tree.json` | Compact recursive tree: `[name, fileCount, bytes, children[]]` |
| | `<case>-depth.json` | Per-depth breakdown: dirs, files, bytes at each level |
| | `<case>-extensions.json` | File extension stats: count + total bytes per extension |
| | `<case>-duplicates.json` | Duplicate file groups: same-name files across directories |
| | `<case>-stats.json` | Summary: total dirs, files, bytes, depth |
| **flags** | `<case>-flags.json` | Security-flagged files matched by configurable rules |
| **tier0** | `<case>-tier0.json` | Dedup collapse: exact + near-duplicate groups, logical file count, LLM request budget |

## Security Flags

Flag rules are defined in YAML — fully configurable per case. The default ruleset (`config/default-flags.yaml`) includes 10 categories:

| Category | Severity | Matches |
|----------|----------|---------|
| Cert/Key | critical | `.pem`, `.key`, `.crt`, `.p12`, `.jks` |
| Credentials | critical | filenames containing `password`, `secret`, `credential`, `token`, `.env` |
| Database | high | `.bak`, `.db`, `.sqlite`, `.mdb` |
| Mobile Binary | high | `.apk`, `.ipa`, `.aab` |
| Packet Capture | high | `.pcap`, `.pcapng`, `.cap` |
| Infra Config | high | `firewall`, `vpn`, `siem`, `router` in filename |
| SQL | medium | `.sql`, `.ddl`, `.dml` |
| Config | medium | `.env`, `.conf`, `.ini`, `.cfg`, `.xml` |
| VAPT Report | medium | `vapt`, `vulnerability`, `pentest`, `security audit` |
| Backup | low | `.bak`, `.old`, `.gz`, `.tar`, `.zip`, `.iso` |

Customize by editing the `flags:` section in your case YAML.

## Viewer Dashboard

The `serve` command launches a zero-dependency HTTP server (Python stdlib only) with an interactive dashboard:

- **Overview** — total dirs, files, size, avg file size
- **Tree** — collapsible directory tree with file/byte counts
- **Extensions** — bar chart of top extensions by count + size
- **Depth** — table of dirs/files/bytes per directory level
- **Duplicates** — duplicate file groups with wasted space
- **Flags** — security-flagged files, filterable by category/severity
- **Tier0** — dedup collapse stats and request budget

Dark/light theme toggle. All data stays local — no telemetry, no external requests.

## Architecture

```
dirforensics/
├── config.py          # CaseConfig dataclass + YAML loader
├── inventory.py       # Canonical inventory loading, DuckDB ingest
├── analyzers.py       # Structural analysis (tree, depth, ext, dupes, stats)
├── flags.py           # Config-driven security-flag classification
├── tier0.py           # Dedup collapse + request budget estimation
├── listing.py         # Apache <pre> autoindex parser
├── demo.py            # Synthetic data generator (for zero-setup demo)
├── serve.py           # HTTP server + viewer dashboard
├── adapters/
│   ├── apache_listing.py  # Async BFS crawler (HTTP/SOCKS5)
│   └── local_fs.py        # Local filesystem walker
└── viewer/
    ├── index.html     # Dashboard shell
    ├── styles.css     # Dark/light theme
    └── app.js         # Tabbed dashboard renderer
```

## Requirements

- Python ≥ 3.10
- Core: `duckdb`, `beautifulsoup4`, `lxml`, `pyyaml`
- Crawl (optional): `aiohttp`, `aiohttp-socks`
- Dev: `pytest`, `ruff`

## License

MIT
