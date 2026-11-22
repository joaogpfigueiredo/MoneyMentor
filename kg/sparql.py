"""SPARQL queries over the KG (Fuseki or in-memory rdflib); ONE_HOP returns an entity's facts with sources.

Usage:
  python -m kg.sparql "seguro multirriscos habitação"
  python -m kg.sparql "seguro de incêndio" --endpoint http://localhost:3030/mealheiro/sparql
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from rdflib import Graph

PREFIXES = """
PREFIX fl:   <https://w3id.org/mealheiro/fl#>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX prov: <http://www.w3.org/ns/prov#>
"""

LABELS = PREFIXES + """
SELECT ?entity ?type ?label WHERE {
  ?entity a ?type ; rdfs:label|skos:altLabel ?label .
  FILTER(STRSTARTS(STR(?type), STR(fl:)))
}
"""

ONE_HOP = PREFIXES + """
SELECT ?sLabel ?p ?oLabel ?source WHERE {
  ?st a rdf:Statement ;
      rdf:subject ?s ; rdf:predicate ?p ; rdf:object ?o ;
      prov:wasDerivedFrom ?source .
  FILTER(?s = ?entity || ?o = ?entity)
  OPTIONAL { ?s rdfs:label ?sl }
  OPTIONAL { ?o rdfs:label|skos:prefLabel ?ol }
  BIND(COALESCE(?sl, STR(?s)) AS ?sLabel)
  BIND(COALESCE(?ol, ?o) AS ?oLabel)
}
ORDER BY ?p
"""


def run(query: str, kg_path: Optional[Path] = None, endpoint: Optional[str] = None) -> list[dict]:
    """Run the query on Fuseki (if an endpoint is given) or on a Turtle file with rdflib."""
    if endpoint:
        from SPARQLWrapper import JSON, SPARQLWrapper
        sw = SPARQLWrapper(endpoint)
        sw.setQuery(query)
        sw.setReturnFormat(JSON)
        rows = sw.query().convert()["results"]["bindings"]
        return [{k: v["value"] for k, v in r.items()} for r in rows]
    here = Path(__file__).resolve().parent
    g = Graph().parse(kg_path).parse(here / "ontology.ttl").parse(here / "topics.ttl")
    return [{str(k): str(v) for k, v in r.asdict().items()} for r in g.query(query)]


def find_entity(label: str, **kw) -> Optional[str]:
    """Match a name against rdfs:label/skos:altLabel, ignoring case, accents and plurals."""
    from .build_kg import entity_iri
    key = entity_iri(label)
    for r in run(LABELS, **kw):
        if entity_iri(r["label"]) == key:
            return r["entity"]
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entity", help="entity name (rdfs:label or alias)")
    ap.add_argument("--kg", type=Path, default=Path("data/kg/kg.ttl"))
    ap.add_argument("--endpoint", default=None)
    args = ap.parse_args()
    kw = {"endpoint": args.endpoint} if args.endpoint else {"kg_path": args.kg}

    entity = find_entity(args.entity, **kw)
    if not entity:
        print(f"Entity not found: {args.entity}")
        return
    print(f"Entity: {entity}\n")
    q = ONE_HOP.replace("?entity", f"<{entity}>")
    for r in run(q, **kw):
        print(f"- {r['sLabel']}  {r['p'].split('#')[-1]}  {r['oLabel'][:90]}\n    source: {r['source']}")


if __name__ == "__main__":
    main()
