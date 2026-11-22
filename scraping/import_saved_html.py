"""Importa páginas guardadas à mão no browser para o mesmo formato JSONL do crawler.

Porquê: o Todos Contam e o Portal do Cliente Bancário bloqueiam clientes automáticos
com um desafio anti-bot. Uma pessoa a ler o site no browser não é bloqueada, por isso
guardamos as páginas relevantes à mão (Ctrl+S, "Página Web, apenas HTML") e este
script faz o resto: descobre o URL original, extrai o texto e escreve o JSONL.

Uso:
  python -m scraping.import_saved_html --source todoscontam
  (lê data/manual_html/todoscontam/*.html)
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
    """Procura o URL original: <link rel=canonical>, depois og:url e por fim o comentário 'saved from url'."""
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
    ap.add_argument("--dir", type=Path, default=None, help="pasta com os .html (por omissão data/manual_html/<fonte>)")
    args = ap.parse_args()

    folder = args.dir or DATA_DIR / "manual_html" / args.source
    files = sorted(list(folder.glob("*.html")) + list(folder.glob("*.htm")))
    if not files:
        print(f"Nenhum .html em {folder}")
        return

    writer = JsonlWriter(args.source)
    saved = 0
    for f in files:
        html = f.read_text(encoding="utf-8", errors="replace")
        url = original_url(html)
        if not url:
            print(f"  [sem URL] {f.name}: não encontrei o URL original, ignorado")
            continue
        page = extract_page(html, url)
        if not page:
            print(f"  [vazio] {f.name}: pouco texto, ignorado")
            continue
        # A data de recolha é o momento em que o ficheiro foi guardado no browser
        when = datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
        if writer.write(url, page["title"], page["text"], retrieved_at=when):
            saved += 1
            print(f"  + {page['title'][:70]}  <- {f.name}")

    print(f"\n{saved} páginas novas em {writer.path} (total: {len(writer.done)})")


if __name__ == "__main__":
    main()
