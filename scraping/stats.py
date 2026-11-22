"""Resumo do corpus recolhido: páginas e palavras por fonte e por tema.

Uso:  python -m scraping.stats
"""
import json
from collections import Counter

from .common import RAW_DIR


def main() -> None:
    files = sorted(RAW_DIR.glob("*.jsonl"))
    if not files:
        print(f"Ainda não há ficheiros em {RAW_DIR}")
        return
    for path in files:
        records = [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]
        words = sum(len(r["text"].split()) for r in records)
        print(f"\n{path.name}: {len(records)} páginas, {words} palavras")
        for topic, n in Counter(r["topic"] for r in records).most_common():
            print(f"  {topic:<14}{n}")


if __name__ == "__main__":
    main()
