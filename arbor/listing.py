"""Apache `<pre>` autoindex listing parser (shared by crawl adapters).

Parses the classic mod_autoindex format:
    <pre><a href="subdir/">subdir/</a> 2024-01-15 10:00  -
    <a href="file.pdf">file.pdf</a> 2024-01-15 10:00  123K

Returns (subdirs, files):
  subdirs = [(dirname, full_url)]
  files   = [(filename, full_url, size_token)]
"""

from __future__ import annotations

from urllib.parse import urljoin


def parse_apache_listing(html_text: str, base_url: str) -> tuple[list[tuple[str, str]], list[tuple[str, str, str]]]:
    try:
        from bs4 import BeautifulSoup
    except ImportError as e:  # pragma: no cover
        raise SystemExit("pip install beautifulsoup4 lxml to use the Apache listing adapter") from e

    soup = BeautifulSoup(html_text, "lxml")
    pre = soup.find("pre")
    if not pre:
        return [], []

    subdirs: list[tuple[str, str]] = []
    files: list[tuple[str, str, str]] = []

    for a in pre.find_all("a"):
        href = a.get("href", "").strip()
        text = a.get_text(strip=True)
        if not href or href in ("/", "../", "./"):
            continue

        full_url = urljoin(base_url, href)

        # Size from the NavigableString sibling after the <a> tag
        size = ""
        sibling = a.next_sibling
        if sibling and isinstance(sibling, str) and sibling.strip():
            tokens = sibling.strip().split()
            if len(tokens) >= 3:
                size = tokens[-1]

        if href.endswith("/"):
            subdirs.append((text.rstrip("/"), full_url))
        else:
            files.append((text, full_url, size))

    return subdirs, files
