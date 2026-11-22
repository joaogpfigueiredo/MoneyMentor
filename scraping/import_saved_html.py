"""Import pages saved in a browser (data/manual_html/<source>/*.html) into the crawler's JSONL format.

Usage: python -m scraping.import_saved_html --source todoscontam
"""
from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import lxml.html

from .common import DATA_DIR, JsonlWriter, extract_page
from .sources import SOURCES

SAVED_FROM = re.compile(r"saved from url=\(\d+\)(\S+)")


def original_url(html: str) -> Optional[str]:
    """Find the page URL: canonical link, then og:url, then the 'saved from url' comment."""
    try:
        doc = lxml.html.fromstring(html)
        for xpath in ('//link[@rel="canonical"]/@href', '//meta[@property="og:url"]/@content'):
            found = doc.xpath(xpath)
            if found and found[0].startswith("http"):
                return found[0].strip()
    except (ValueError, lxml.etree.ParserError):
        pass
    m = SAVED_FROM.search(html[:2000])
    return m.group(1).split(" ")[0].rstrip("-->").strip() if m else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, choices=sorted(SOURCES))
    ap.add_argument("--dir", type=Path, default=None, help="folder with the .html files (default data/manual_html/<source>)")
    args = ap.parse_args()

    folder = args.dir or DATA_DIR / "manual_html" / args.source
    files = sorted(list(folder.glob("*.html")) + list(folder.glob("*.htm")))
    if not files:
        print(f"No .html files in {folder}")
        return

    writer = JsonlWriter(args.source)
    saved = 0
    for f in files:
        html = f.read_text(encoding="utf-8", errors="replace")
        url = original_url(html)
        if not url:
            print(f"  [no URL] {f.name}: original URL not found, skipped")
            continue
        page = extract_page(html, url)
        if not page:
            print(f"  [empty] {f.name}: too little text, skipped")
            continue
        when = datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
        if writer.write(url, page["title"], page["text"], retrieved_at=when):
            saved += 1
            print(f"  + {page['title'][:70]}  <- {f.name}")

    print(f"\n{saved} new pages in {writer.path} (total: {len(writer.done)})")


if __name__ == "__main__":
    main()
