"""Índice de texto: pedaços de ~300 palavras, embeddings BGE-M3 e pesquisa com FAISS.

Porquê: o baseline (b) e o nosso sistema precisam de encontrar as 3–5 passagens do corpus mais
parecidas com a pergunta. Cada página de data/raw/*.jsonl é dividida em pedaços (parágrafos inteiros),
cada pedaço vira um vetor com o BGE-M3 (modelo multilingue, corre no Ollama) e o FAISS devolve
os vetores mais próximos do vetor da pergunta (produto interno de vetores normalizados = cosseno).

Uso:
  ollama pull bge-m3
  python -m retrieval.text_index build                 # cria data/index/
  python -m retrieval.text_index search "O que é a TANB?"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import faiss
import numpy as np
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
INDEX_DIR = ROOT / "data" / "index"
EMBED_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "bge-m3"
CHUNK_WORDS = 300


def embed(texts: list[str], batch: int = 16) -> np.ndarray:
    """Vetores BGE-M3 (normalizados) para uma lista de textos, pedidos ao Ollama em lotes."""
    out = []
    for i in range(0, len(texts), batch):
        resp = requests.post(EMBED_URL, json={"model": EMBED_MODEL, "input": texts[i:i + batch]}, timeout=600)
        resp.raise_for_status()
        out.extend(resp.json()["embeddings"])
    vecs = np.array(out, dtype="float32")
    faiss.normalize_L2(vecs)
    return vecs


def chunk_page(text: str, max_words: int = CHUNK_WORDS) -> list[str]:
    """Junta parágrafos inteiros até ~max_words palavras (não corta frases a meio)."""
    chunks, current, n = [], [], 0
    for para in [p.strip() for p in text.split("\n") if p.strip()]:
        words = len(para.split())
        if current and n + words > max_words:
            chunks.append("\n".join(current))
            current, n = [], 0
        current.append(para)
        n += words
    if current:
        chunks.append("\n".join(current))
    return chunks


def build() -> None:
    chunks = []
    for path in sorted(RAW_DIR.glob("*.jsonl")):
        for line in path.open(encoding="utf-8"):
            page = json.loads(line)
            for i, text in enumerate(chunk_page(page["text"])):
                chunks.append({"id": len(chunks), "url": page["url"], "title": page["title"],
                               "source": page["source"], "chunk": i, "text": text})
    print(f"{len(chunks)} pedaços de {len({c['url'] for c in chunks})} páginas; a calcular embeddings...", flush=True)
    # O título entra no texto do embedding: ajuda quando o pedaço não repete o tema da página
    vecs = embed([f"{c['title']}\n{c['text']}" for c in chunks])
    index = faiss.IndexFlatIP(vecs.shape[1])  # pesquisa exata; com ~1000 pedaços não é preciso mais
    index.add(vecs)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(INDEX_DIR / "text.faiss"))
    with (INDEX_DIR / "chunks.jsonl").open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"Escrito: {INDEX_DIR} ({index.ntotal} vetores de dimensão {vecs.shape[1]})")


class TextIndex:
    """Carrega o índice uma vez e responde a pesquisas."""

    def __init__(self) -> None:
        self.index = faiss.read_index(str(INDEX_DIR / "text.faiss"))
        self.chunks = [json.loads(l) for l in (INDEX_DIR / "chunks.jsonl").open(encoding="utf-8")]

    def search_vectors(self, qvecs: np.ndarray, k: int = 5) -> list[list[dict]]:
        scores, ids = self.index.search(qvecs, k)
        return [[{**self.chunks[i], "score": float(s)} for s, i in zip(row_s, row_i) if i >= 0]
                for row_s, row_i in zip(scores, ids)]

    def search(self, question: str, k: int = 5) -> list[dict]:
        return self.search_vectors(embed([question]), k)[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["build", "search"])
    ap.add_argument("query", nargs="?")
    ap.add_argument("-k", type=int, default=5)
    args = ap.parse_args()
    if args.command == "build":
        build()
    else:
        if not args.query:
            sys.exit("Indica a pergunta.")
        for r in TextIndex().search(args.query, args.k):
            print(f"{r['score']:.3f}  [{r['source']}] {r['title']}  ({r['url']})\n       {r['text'][:150]}...")


if __name__ == "__main__":
    main()
