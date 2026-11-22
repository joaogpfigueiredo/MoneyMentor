"""Carrega a ontologia, os temas e o KG validado no Fuseki (Graph Store Protocol).

Substitui o grafo por omissão do dataset: correr duas vezes não duplica nada.

Uso:
  docker compose up -d
  python -m kg.load_fuseki                      # data/kg/kg.ttl
  python -m kg.load_fuseki --kg data/kg/exemplo.ttl
"""
from __future__ import annotations

import argparse
from pathlib import Path

import requests
from rdflib import Graph

KG_DIR = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kg", type=Path, default=KG_DIR.parent / "data" / "kg" / "kg.ttl")
    ap.add_argument("--fuseki", default="http://localhost:3030/mealheiro")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="mealheiro")
    args = ap.parse_args()

    g = Graph()
    for path in (KG_DIR / "ontology.ttl", KG_DIR / "topics.ttl", args.kg):
        g.parse(path)
    body = g.serialize(format="turtle").encode("utf-8")

    r = requests.put(
        f"{args.fuseki}/data?default",
        data=body,
        headers={"Content-Type": "text/turtle; charset=utf-8"},
        auth=(args.user, args.password),
        timeout=120,
    )
    r.raise_for_status()
    print(f"Carregados {len(g)} triplos em {args.fuseki} (HTTP {r.status_code})")
    print(f"Testar: python -m kg.sparql \"seguro de incêndio\" --endpoint {args.fuseki}/sparql")


if __name__ == "__main__":
    main()
