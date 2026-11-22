"""KG numbers: nodes per class, links per relation, attributes, provenance and most-linked entities.

Usage: python -m kg.stats [--kg data/kg/kg.ttl]
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from rdflib import RDF, RDFS, Graph, Namespace

FL = Namespace("https://w3id.org/mealheiro/fl#")
ROOT = Path(__file__).resolve().parent.parent
RELATIONS = ["hasCost", "hasRisk", "regulatedBy", "relatedTo", "hasTopic"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kg", type=Path, default=ROOT / "data" / "kg" / "kg.ttl")
    args = ap.parse_args()
    g = Graph().parse(args.kg)

    classes = Counter(str(o).split("#")[-1] for o in g.objects(None, RDF.type) if str(o).startswith(str(FL)))
    print(f"File: {args.kg}  ({len(g)} triples)\n")
    print(f"NODES (entities): {sum(classes.values())}")
    for c, n in classes.most_common():
        print(f"  fl:{c:<10} {n}")

    print(f"\nLINKS between nodes: {sum(len(list(g.subject_objects(FL[r]))) for r in RELATIONS)}")
    for r in RELATIONS:
        print(f"  fl:{r:<12} {len(list(g.subject_objects(FL[r])))}")
    print(f"\nATTRIBUTES: {len(list(g.subject_objects(FL.definition)))} definitions (fl:definition), "
          f"{len(list(g.subject_objects(RDFS.label)))} names (rdfs:label)")

    statements = set(g.subjects(RDF.type, RDF.Statement))
    sources = {o for s in statements for o in g.objects(s, Namespace("http://www.w3.org/ns/prov#").wasDerivedFrom)}
    print(f"PROVENANCE: {len(statements)} facts described by rdf:Statement, from {len(sources)} pages")

    labels = Graph().parse(ROOT / "kg" / "ontology.ttl")
    degree = Counter()
    for r in RELATIONS[:4]:
        for s, o in g.subject_objects(FL[r]):
            degree[s] += 1
            degree[o] += 1
    print("\nMost-linked entities:")
    for node, n in degree.most_common(10):
        label = g.value(node, RDFS.label) or labels.value(node, RDFS.label) or str(node).rsplit("#", 1)[-1]
        print(f"  {n:>3}  {label}")


if __name__ == "__main__":
    main()
