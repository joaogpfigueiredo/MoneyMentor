"""Split a browser-collected JSON bundle {url: html} into .html files for import_saved_html.

Usage: python -m scraping.split_browser_bundle ~/Downloads/mealheiro_bportugal.json --source bportugal
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .common import DATA_DIR


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bundle", type=Path, help="JSON {url: html} saved by the browser")
    ap.add_argument("--source", required=True, help="target folder under data/manual_html/")
    args = ap.parse_args()

    pages = json.loads(args.bundle.read_text(encoding="utf-8"))
    folder = DATA_DIR / "manual_html" / args.source
    folder.mkdir(parents=True, exist_ok=True)
    for url, html in pages.items():
        name = url.rstrip("/").rsplit("/", 1)[-1][:60] or "index"
        name = f"{name}-{hashlib.sha1(url.encode()).hexdigest()[:6]}.html"
        comment = f"<!-- saved from url=({len(url):04d}){url} -->\n"
        (folder / name).write_text(comment + html, encoding="utf-8")
    print(f"{len(pages)} page(s) written to {folder}")


if __name__ == "__main__":
    main()
