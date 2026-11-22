"""Desenha a vizinhança de uma entidade do KG num ficheiro HTML (para mostrar na apresentação).

Porquê: um grafo percebe-se melhor a ver do que a ler Turtle. O script vai buscar a entidade e
todos os vizinhos a 1 salto (o mesmo que o chatbot vai usar para responder) e gera uma página com a
biblioteca vis-network: cada cor é uma classe da ontologia e cada seta tem o nome da relação.

Uso:
  python -m kg.visualize "seguro de habitação"            # -> data/kg/vis/seguro-de-habitacao.html
  python -m kg.visualize "fundos de pensões" --hops 2
"""
from __future__ import annotations

import argparse
import json
import webbrowser
from pathlib import Path

from rdflib import RDF, RDFS, Graph, Namespace, URIRef

from .build_kg import entity_iri

FL = Namespace("https://w3id.org/mealheiro/fl#")
ROOT = Path(__file__).resolve().parent.parent
RELATIONS = ["hasCost", "hasRisk", "regulatedBy", "relatedTo", "hasTopic"]
COLORS = {"Product": "#2f6fb0", "Concept": "#7a7a7a", "Cost": "#c0392b", "Risk": "#e67e22",
          "Right": "#27ae60", "Regulator": "#8e44ad", "Topic": "#b7950b"}

PAGE = """<!doctype html><html lang="pt"><head><meta charset="utf-8"><title>KG: {title}</title>
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<style>body{{font-family:sans-serif;margin:0}}#g{{width:100vw;height:92vh}}p{{margin:8px 12px}}</style></head>
<body><p><b>{title}</b>: {n} nós, {e} ligações. Cores: {legend}</p><div id="g"></div><script>
new vis.Network(document.getElementById("g"),{{nodes:new vis.DataSet({nodes}),edges:new vis.DataSet({edges})}},
{{edges:{{arrows:"to",font:{{size:11,align:"middle"}}}},nodes:{{shape:"dot",size:14,font:{{size:14}}}},physics:{{stabilization:true}}}});
</script></body></html>"""


def label_of(g: Graph, node: URIRef) -> str:
    return str(g.value(node, RDFS.label) or g.value(node, Namespace("http://www.w3.org/2004/02/skos/core#").prefLabel)
               or str(node).rsplit("#", 1)[-1].rsplit("/", 1)[-1])


def class_of(g: Graph, node: URIRef) -> str:
    for t in g.objects(node, RDF.type):
        name = str(t).rsplit("#", 1)[-1]
        if name in COLORS:
            return name
    return "Concept"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entity")
    ap.add_argument("--kg", type=Path, default=ROOT / "data" / "kg" / "kg.ttl")
    ap.add_argument("--hops", type=int, default=1)
    args = ap.parse_args()

    g = Graph()
    for f in (args.kg, ROOT / "kg" / "ontology.ttl", ROOT / "kg" / "topics.ttl"):
        g.parse(f)
    start = entity_iri(args.entity)
    if (start, RDF.type, None) not in g:
        raise SystemExit(f"Entidade não encontrada: {args.entity}")

    nodes, edges, frontier = {start}, set(), {start}
    for _ in range(args.hops):
        nxt = set()
        for n in frontier:
            for r in RELATIONS:
                for o in g.objects(n, FL[r]):
                    edges.add((n, r, o)); nxt.add(o)
                for s in g.subjects(FL[r], n):
                    edges.add((s, r, n)); nxt.add(s)
        frontier = nxt - nodes
        nodes |= nxt

    ids = {n: i for i, n in enumerate(nodes)}
    vis_nodes = [{"id": ids[n], "label": label_of(g, n), "color": COLORS[class_of(g, n)],
                  "title": class_of(g, n), "size": 24 if n == start else 14} for n in nodes]
    vis_edges = [{"from": ids[s], "to": ids[o], "label": r} for s, r, o in edges]
    legend = ", ".join(f'<span style="color:{c}">■ {k}</span>' for k, c in COLORS.items())
    out = ROOT / "data" / "kg" / "vis" / f"{str(start).rsplit('/', 1)[-1]}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(PAGE.format(title=args.entity, n=len(nodes), e=len(edges), legend=legend,
                               nodes=json.dumps(vis_nodes, ensure_ascii=False),
                               edges=json.dumps(vis_edges, ensure_ascii=False)), encoding="utf-8")
    print(f"Escrito: {out}  ({len(nodes)} nós, {len(edges)} ligações)")
    webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
