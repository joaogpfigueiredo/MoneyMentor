"""Divide um "pacote" de páginas recolhidas no browser em ficheiros .html para a importação manual.

Porquê: o Todos Contam e o Portal do Cliente Bancário bloqueiam clientes automáticos. A recolha
foi feita num browser real (Chrome), com uma pessoa a passar as verificações e 1,5–2,5 s entre
páginas. O browser grava um único JSON {url: html}; este script escreve um .html por página, com
o comentário "saved from url" (o mesmo que o Ctrl+S do browser põe), para o import_saved_html.

Uso:
  python -m scraping.split_browser_bundle ~/Downloads/mealheiro_bportugal.json --source bportugal
  python -m scraping.import_saved_html --source bportugal
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .common import DATA_DIR


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bundle", type=Path, help="JSON {url: html} gravado pelo browser")
    ap.add_argument("--source", required=True, help="pasta de destino em data/manual_html/")
    args = ap.parse_args()

    pages = json.loads(args.bundle.read_text(encoding="utf-8"))
    folder = DATA_DIR / "manual_html" / args.source
    folder.mkdir(parents=True, exist_ok=True)
    for url, html in pages.items():
        name = url.rstrip("/").rsplit("/", 1)[-1][:60] or "index"
        name = f"{name}-{hashlib.sha1(url.encode()).hexdigest()[:6]}.html"
        comment = f"<!-- saved from url=({len(url):04d}){url} -->\n"
        (folder / name).write_text(comment + html, encoding="utf-8")
    print(f"{len(pages)} página(s) escritas em {folder}")


if __name__ == "__main__":
    main()
