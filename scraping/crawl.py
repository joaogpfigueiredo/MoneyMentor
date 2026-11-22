"""Crawler simples em largura (BFS) para uma fonte.

Como funciona:
  1. Começa nos start_urls da fonte e mantém uma fila de páginas por visitar.
  2. Para cada página: pede-a com PoliteSession (robots.txt e 1-2 s de pausa),
     ou lê-a da cache se já a tivermos descarregado.
  3. Junta à fila os links novos que a fonte aceita.
  4. Extrai o texto com o trafilatura e, se tiver conteúdo, escreve uma linha em data/raw/<fonte>.jsonl.
  5. Se o site mostrar um desafio anti-bot, pára e explica o que fazer.

Uso:
  python -m scraping.crawl --source asf --max-pages 200
"""
from __future__ import annotations

import argparse
import sys
from collections import deque

from .common import HTML_CACHE_DIR, BlockedError, JsonlWriter, PoliteSession, cache_path, extract_links, extract_page
from .sources import SOURCES, Source


def fetch_html(session: PoliteSession, url: str) -> tuple[str, str] | None:
    """Devolve (html, url_final). Usa a cache em disco para não repetir pedidos."""
    cached = cache_path(url)
    if cached.exists():
        return cached.read_text(encoding="utf-8"), url
    resp = session.get(url)
    if resp is None or "text/html" not in resp.headers.get("Content-Type", ""):
        return None
    HTML_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached.write_text(resp.text, encoding="utf-8")
    return resp.text, resp.url


def crawl(source: Source, max_pages: int) -> None:
    session = PoliteSession()
    writer = JsonlWriter(source.name)
    queue = deque(source.start_urls)
    seen = set(queue)
    visited = saved = 0

    while queue and visited < max_pages:
        url = queue.popleft()
        visited += 1
        result = fetch_html(session, url)
        if result is None:
            continue
        html, final_url = result

        for link in extract_links(html, final_url):
            if link not in seen and source.accepts(link):
                seen.add(link)
                queue.append(link)

        page = extract_page(html, final_url)
        if page and writer.write(final_url, page["title"], page["text"]):
            saved += 1
            print(f"[{visited}/{max_pages}] + {page['title'][:70]}")

    print(f"\nVisitadas: {visited} | novas páginas guardadas: {saved} | total no ficheiro: {len(writer.done)}")
    print(f"Por visitar na fila: {len(queue)} | ficheiro: {writer.path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, choices=sorted(SOURCES))
    ap.add_argument("--max-pages", type=int, default=300)
    args = ap.parse_args()
    try:
        crawl(SOURCES[args.source], args.max_pages)
    except BlockedError as e:
        print(f"\nBLOQUEADO: {e}")
        print("Não contornamos proteções anti-bot. Alternativa: guardar as páginas no browser")
        print(f"(Ctrl+S, 'Página Web, apenas HTML') em data/manual_html/{args.source}/ e correr:")
        print(f"  python -m scraping.import_saved_html --source {args.source}")
        sys.exit(2)


if __name__ == "__main__":
    main()
