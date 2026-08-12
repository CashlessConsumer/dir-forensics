"""Adapter: generic async BFS crawler for Apache `<pre>` directory listings.

A parameterized async BFS crawler for Apache directory listings with
no target-specific coupling: base URL, SOCKS proxy, concurrency, depth,
checkpoint and output paths are all CLI/config driven.

Usage:
    python -m arbor.adapters.apache_listing \\
        --base-url http://host/path/ --out inventory.json \\
        [--socks 127.0.0.1:9060] [--concurrency 12] [--max-depth 99]
        [--checkpoint crawl-checkpoint.json] [--inventory-every 5]
        [--resume]

Features:
- Async aiohttp (+ aiohttp_socks for Tor/any SOCKS5)
- BFS with depth tracking, per-level checkpointing and resume
- Apache <pre> listing parser (arbor.listing)
- Per-depth inventory generation (JSON + markdown) at every N levels
- Exponential backoff retry, graceful SIGINT checkpoint save

Note: when no --socks is given, it crawls directly over plain HTTP(S).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from ..listing import parse_apache_listing
from ..inventory import parse_size_token

DEFAULT_CONCURRENCY = 12
DEFAULT_MAX_DEPTH = 99
DEFAULT_RETRY_DELAY = 2
DEFAULT_MAX_RETRIES = 6
CHECKPOINT_INTERVAL = 60
PROGRESS_INTERVAL = 5


class CrawlerState:
    """Serialisable crawler state with set→list serialisation for JSON."""

    __slots__ = ("base_url", "queue", "visited", "all_dirs", "all_files",
                 "retry_counts", "stats", "started", "completed_levels",
                 "last_checkpoint_time", "batch_count")

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/") + "/"
        self.queue: list[tuple[str, int]] = []          # (relpath, depth)
        self.visited: set[str] = set()
        self.all_dirs: set[str] = set()
        self.all_files: dict[str, dict] = {}
        self.retry_counts: dict[str, int] = {}
        self.stats: dict[str, int] = {"fetched": 0, "errors": 0,
                                      "dirs": 0, "files": 0, "bytes": 0}
        self.started: str = datetime.now(timezone.utc).isoformat()
        self.completed_levels: set[int] = set()
        self.last_checkpoint_time: float = 0
        self.batch_count: int = 0

    def to_dict(self) -> dict:
        return {
            "base_url": self.base_url,
            "queue": self.queue,
            "visited": sorted(self.visited),
            "all_dirs": sorted(self.all_dirs),
            "all_files": {k: v for k, v in sorted(self.all_files.items())},
            "retry_counts": self.retry_counts,
            "stats": self.stats,
            "started": self.started,
            "completed_levels": sorted(self.completed_levels),
            "batch_count": self.batch_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CrawlerState":
        st = cls(d.get("base_url", ""))
        st.queue = [(q[0], q[1]) for q in d.get("queue", [])]
        st.visited = set(d.get("visited", []))
        st.all_dirs = set(d.get("all_dirs", []))
        st.all_files = {k: v for k, v in d.get("all_files", {}).items()}
        st.retry_counts = d.get("retry_counts", {})
        st.stats = d.get("stats", st.stats)
        st.started = d.get("started", st.started)
        st.completed_levels = set(d.get("completed_levels", []))
        st.batch_count = d.get("batch_count", 0)
        return st

    def save_checkpoint(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(self.to_dict(), f)
        tmp.rename(path)
        self.last_checkpoint_time = time.monotonic()

    @classmethod
    def load_checkpoint(cls, path: Path) -> "CrawlerState | None":
        if not path.exists():
            return None
        try:
            with open(path) as f:
                return cls.from_dict(json.load(f))
        except Exception as e:
            print(f"[!] Error loading checkpoint: {e}", file=sys.stderr)
            return None


class ListingCrawler:
    def __init__(self, state: CrawlerState, *, concurrency: int = DEFAULT_CONCURRENCY,
                 max_depth: int = DEFAULT_MAX_DEPTH, proxy: str = "",
                 retry_delay: float = DEFAULT_RETRY_DELAY, max_retries: int = DEFAULT_MAX_RETRIES):
        self.state = state
        self.concurrency = concurrency
        self.max_depth = max_depth
        self.proxy = proxy  # "socks5://host:port" or ""
        self.retry_delay = retry_delay
        self.max_retries = max_retries
        self.sem = asyncio.Semaphore(concurrency)
        self._shutdown = False
        self._stats_lock = asyncio.Lock()
        self._last_progress = 0.0
        self._fetch_times: list[float] = []
        self._start_wall = time.monotonic()
        self._connector = None
        self._timeout = None
        self._session: asyncio.Future | None = None

    def _signal_handler(self):
        self._shutdown = True
        print("\n[!] Shutdown requested — saving checkpoint…", flush=True)

    async def _fetch(self, url: str) -> tuple[str | None, bool]:
        """Fetch a URL. Returns (html|None, hard_fail)."""
        import aiohttp

        session = self._session
        if session is None:
            return None, False
        try:
            async with session.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    return None, True
                ct = resp.headers.get("Content-Type", "")
                if "text" not in ct and "html" not in ct:
                    return None, True
                text = await resp.text()
                async with self._stats_lock:
                    self.state.stats["bytes"] += len(text)
                return text, False
        except (asyncio.TimeoutError, OSError):
            return None, False
        except Exception:
            return None, True  # decode errors etc — retry pointless

    async def _fetch_with_retry(self, url: str, relpath: str) -> str | None:
        max_attempts = 1 + self.max_retries
        for attempt in range(1, max_attempts + 1):
            if self._shutdown:
                return None
            html, hard_fail = await self._fetch(url)
            if html is not None:
                async with self._stats_lock:
                    self.state.stats["fetched"] += 1
                return html
            async with self._stats_lock:
                self.state.stats["errors"] += 1
                self.state.retry_counts[relpath] = attempt
            if hard_fail or attempt >= max_attempts:
                return None
            delay = min(self.retry_delay * (2 ** (attempt - 1)), 60)
            print(f"  ⚠  [{relpath[:80]}] attempt {attempt}/{max_attempts} failed, retry in {delay}s", flush=True)
            await asyncio.sleep(delay)
        return None

    async def _process_dir(self, relpath: str, depth: int):
        if self._shutdown:
            return
        async with self.sem:
            if relpath in self.state.visited:
                return
            self.state.visited.add(relpath)

            url = self.state.base_url + urllib.parse.quote(relpath)
            html = await self._fetch_with_retry(url, relpath)
            if html is None:
                return

            subdirs, files = parse_apache_listing(html, url)
            self.state.all_dirs.add(relpath)
            async with self._stats_lock:
                self.state.stats["dirs"] += 1

            for fname, f_url, fsize in files:
                f_rel = relpath + fname
                meta = {"name": fname, "url": f_url, "size": fsize}
                b = parse_size_token(fsize)
                if b is not None:
                    meta["size_bytes"] = b
                self.state.all_files[f_rel] = meta
                async with self._stats_lock:
                    self.state.stats["files"] += 1

            next_depth = depth + 1
            for dname, _ in subdirs:
                d_rel = relpath + dname + "/"
                if next_depth <= self.max_depth and d_rel not in self.state.visited and d_rel not in self.state.all_dirs:
                    self.state.queue.append((d_rel, next_depth))
                    self.state.all_dirs.add(d_rel)

    def _generate_inventory(self, depth: int, out: Path, inv_dir: Path, prefix: str):
        inv_dir.mkdir(parents=True, exist_ok=True)
        depth_dirs = [d for d in self.state.all_dirs if d.rstrip("/").count("/") <= depth]
        depth_files = {fp: m for fp, m in self.state.all_files.items() if fp.count("/") - 1 <= depth}
        depth_dirs.sort()
        depth_files = dict(sorted(depth_files.items()))

        json_data = {
            "depth": depth,
            "dirs": depth_dirs,
            "files": depth_files,
            "stats": {"dirs": len(depth_dirs), "files": len(depth_files)},
        }
        json_path = inv_dir / f"{prefix}-L{depth}.json"
        with open(json_path, "w") as f:
            json.dump(json_data, f, indent=2)

        md_lines = [
            f"# Directory Inventory — Depth 0–{depth}",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            f"Directories: {len(depth_dirs)}",
            f"Files: {len(depth_files)}",
            "",
            "## Directory Tree",
            "",
        ]
        for dr in depth_dirs:
            indent = "  " * dr.rstrip("/").count("/")
            label = urllib.parse.unquote(dr.rstrip("/")).rsplit("/", 1)[-1] if dr.rstrip("/") else "/"
            md_lines.append(f"{indent}- {label}/")
        md_lines += ["", "## Files by Directory", ""]
        current = ""
        for fp, meta in depth_files.items():
            dirpart = "/".join(fp.split("/")[:-1]) or "/"
            if dirpart != current:
                md_lines += ["", f"### {urllib.parse.unquote(dirpart)}"]
                current = dirpart
            line = f"- {urllib.parse.unquote(meta.get('name', fp.rsplit('/', 1)[-1]))}"
            if meta.get("size"):
                line += f"  ({meta['size']})"
            md_lines.append(line)
        md_path = inv_dir / f"{prefix}-L{depth}.md"
        with open(md_path, "w") as f:
            f.write("\n".join(md_lines))

        print(f"  ✓ Inventory L0–{depth}: {len(depth_dirs)} dirs, {len(depth_files)} files -> {json_path.name}", flush=True)

    def _show_progress(self, force: bool = False):
        now = time.monotonic()
        if not force and now - self._last_progress < PROGRESS_INTERVAL:
            return
        self._last_progress = now
        s = self.state.stats
        elapsed = now - self._start_wall
        rate = s["fetched"] / elapsed if elapsed > 0 else 0
        qlen = len(self.state.queue)
        eta = f"ETA {qlen / rate:.0f}s" if rate > 0 else ""
        depth_counts: dict[int, int] = {}
        for _, d in self.state.queue:
            depth_counts[d] = depth_counts.get(d, 0) + 1
        depth_str = " ".join(f"L{d}:{c}" for d, c in sorted(depth_counts.items()))
        err_pct = 100 * s["errors"] / (s["fetched"] + s["errors"]) if (s["fetched"] + s["errors"]) else 0
        print(f"  [{elapsed:7.0f}s] fetched {s['fetched']:6d}  err {s['errors']:4d} ({err_pct:4.1f}%)  "
              f"dirs {s['dirs']:5d}  files {s['files']:6d}  queue {qlen:5d}  {rate:5.1f}/s  {eta}",
              flush=True)
        if depth_str:
            print(f"  Queue depths: {depth_str}  |  Downloaded: {s['bytes'] / 1e6:.1f} MB", flush=True)

    async def run(self, checkpoint_path: Path, out: Path, inv_dir: Path, prefix: str,
                  inventory_every: int):
        import aiohttp

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._signal_handler)
            except NotImplementedError:
                pass

        if self.proxy:
            from aiohttp_socks import ProxyConnector, ProxyType

            host, _, port = self.proxy.partition(":")
            self._connector = ProxyConnector(host=host, port=int(port), proxy_type=ProxyType.SOCKS5, rdns=True)
        else:
            self._connector = aiohttp.TCPConnector(limit=self.concurrency)
        self._session = aiohttp.ClientSession(connector=self._connector)

        if not self.state.queue:
            self.state.queue.append(("", 0))

        try:
            while self.state.queue and not self._shutdown:
                batch = []
                while self.state.queue and len(batch) < self.concurrency * 4:
                    batch.append(self.state.queue.pop(0))
                tasks = [self._process_dir(rel, dep) for rel, dep in batch]
                await asyncio.gather(*tasks)

                now = time.monotonic()
                if now - self.state.last_checkpoint_time >= CHECKPOINT_INTERVAL:
                    self.state.save_checkpoint(checkpoint_path)
                    self._show_progress(force=True)
                else:
                    self._show_progress()

                # Emit inventory snapshots at configured level boundaries
                for rel, dep in batch:
                    if dep not in self.state.completed_levels and dep % inventory_every == 0:
                        self.state.completed_levels.add(dep)
                        self._generate_inventory(dep, out, inv_dir, prefix)
                        self.state.batch_count += 1
        finally:
            self.state.save_checkpoint(checkpoint_path)
            await self._session.close()

        print(f"\nDone: {self.state.stats['dirs']} dirs, {self.state.stats['files']} files, "
              f"{self.state.stats['bytes'] / 1e6:.1f} MB crawled", flush=True)


def write_final_inventory(state: CrawlerState, out: Path):
    """Emit the canonical inventory JSON at crawl completion."""
    dirs = sorted(state.all_dirs)
    files = dict(sorted(state.all_files.items()))
    payload = {
        "depth": max((d.rstrip("/").count("/") for d in dirs), default=0),
        "dirs": dirs,
        "files": files,
        "stats": {"dirs": len(dirs), "files": len(files)},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"final inventory -> {out}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generic Apache directory-listing crawler")
    ap.add_argument("--base-url", required=True, help="base URL ending in / (e.g. http://host/dump/)")
    ap.add_argument("--out", required=True, help="output canonical inventory JSON")
    ap.add_argument("--socks", default="", help="SOCKS5 proxy host:port (e.g. 127.0.0.1:9060 for Tor)")
    ap.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    ap.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH)
    ap.add_argument("--checkpoint", default="", help="checkpoint file path (default: <out>.checkpoint.json)")
    ap.add_argument("--inv-dir", default="", help="directory for per-depth inventory snapshots (default: <out>.inventories)")
    ap.add_argument("--inventory-every", type=int, default=5, help="emit a snapshot every N completed depth levels (0=never)")
    ap.add_argument("--prefix", default="inventory", help="filename prefix for snapshots")
    ap.add_argument("--resume", action="store_true", help="resume from checkpoint")
    args = ap.parse_args(argv)

    out = Path(args.out)
    checkpoint = Path(args.checkpoint) if args.checkpoint else out.with_suffix(".checkpoint.json")
    inv_dir = Path(args.inv_dir) if args.inv_dir else out.with_suffix(".inventories")

    state = None
    if args.resume:
        state = CrawlerState.load_checkpoint(checkpoint)
        if state:
            print(f"resumed from {checkpoint}: {state.stats['dirs']} dirs, {state.stats['files']} files", flush=True)
    if state is None:
        state = CrawlerState(args.base_url)

    crawler = ListingCrawler(
        state,
        concurrency=args.concurrency,
        max_depth=args.max_depth,
        proxy=args.socks,
    )
    try:
        asyncio.run(crawler.run(checkpoint, out, inv_dir, args.prefix, args.inventory_every))
    except KeyboardInterrupt:
        print("interrupted — checkpoint saved, re-run with --resume", flush=True)
        return 130

    write_final_inventory(state, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
