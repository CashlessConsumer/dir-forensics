"""Lightweight HTTP server for viewing dir-forensics artifacts.

Serves the case output directory + the bundled viewer UI on localhost.
Zero external dependencies — uses only Python stdlib (http.server).
"""

from __future__ import annotations

import json
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


VIEWER_DIR = Path(__file__).parent / "viewer"


def serve(output_dir: Path, case: str, port: int = 9173, open_browser: bool = True) -> int:
    """Start the viewer server for a case's output directory."""

    output_dir = output_dir.resolve()
    viewer_dir = VIEWER_DIR.resolve()

    html_template = (viewer_dir / "index.html").read_text()

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(output_dir), **kw)

        def do_GET(self):
            # Viewer UI routes
            if self.path == "/" or self.path == "":
                self._serve_html()
                return
            if self.path.startswith("/__viewer/"):
                self._serve_viewer_asset(self.path[len("/__viewer/"):])
                return
            super().do_GET()

        def _serve_html(self):
            html = html_template.replace("{{CASE}}", case)
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_viewer_asset(self, name: str):
            fp = viewer_dir / name
            if not fp.exists() or not fp.is_file():
                self.send_error(404)
                return
            data = fp.read_bytes()
            ct = {
                "styles.css": "text/css",
                "app.js": "application/javascript",
                "logo.svg": "image/svg+xml",
            }.get(name, "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *args):
            pass  # quiet

    # Check output dir has artifacts
    artifacts = list(output_dir.glob(f"{case}-*.json"))
    if not artifacts:
        print(f"[serve] warning: no artifacts matching '{case}-*.json' in {output_dir}")
        print(f"        run 'arbor all' first, then serve.")
    else:
        print(f"[serve] {len(artifacts)} artifacts found")

    url = f"http://localhost:{port}"
    print(f"[serve] Arbor viewer → {url}")
    print(f"[serve] case: {case}")
    print(f"[serve] serving from: {output_dir}")
    print(f"[serve] press Ctrl+C to stop")

    if open_browser:
        try:
            import threading
            import webbrowser
            threading.Timer(0.5, lambda: webbrowser.open(url)).start()
        except Exception:
            pass

    httpd = HTTPServer(("0.0.0.0", port), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[serve] stopped")
        httpd.shutdown()
    return 0
