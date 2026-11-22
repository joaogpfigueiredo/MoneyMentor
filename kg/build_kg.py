"""Build the RDF KG from the JSON extractions (direct triples + reified provenance) and filter it with SHACL.

Usage:
  python -m kg.build_kg
  python -m kg.build_kg --input kg/examples/*.jsonl
  python -m kg.build_kg --no-shacl
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import unicodedata
from pathlib import Path

from pydantic import ValidationError
from pyshacl import validate
from rdflib import RDF, RDFS, Graph, Literal, Namespace, URIRef
from rdflib.namespace import PROV, SH, SKOS

from .schema import REGULATOR_IRIS, Extraction

KG_DIR = Path(__file__).resolve().parent
OUT_DIR = KG_DIR.parent / "data" / "kg"
FL = Namespace("https://w3id.org/mealheiro/fl#")
KG = Namespace("https://w3id.org/mealheiro/kg/")


def slug(text: str) -> str:
    """'Crédito à Habitação' -> 'credito-a-habitacao'."""
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def singular(word: str) -> str:
    """Rough Portuguese singular: 'pensoes' -> 'pensao', 'anuais' -> 'anual', 'seguros' -> 'seguro'."""
    if len(word) <= 3 or not word.endswith("s"):
        return word
    for plural, sing in (("oes", "ao"), ("aes", "ao"), ("ais", "al"), ("eis", "el"), ("res", "r")):
        if word.endswith(plural):
            return word[: -len(plural)] + sing
    return word[:-1]


def entity_iri(label: str) -> URIRef:
    """Entity IRI: the label slug with every word singularised, so plural variants share one node."""
    return KG["-".join(singular(w) for w in slug(label).split("-"))]


def bind_prefixes(g: Graph) -> None:
    g.bind("fl", FL)
    g.bind("kg", KG)
    g.bind("skos", SKOS)
    g.bind("prov", PROV)


def add_fact(g: Graph, s: URIRef, p: URIRef, o, source: URIRef) -> None:
    """Add the triple plus an rdf:Statement (hash IRI) linking it to its source."""
    g.add((s, p, o))
    h = hashlib.sha1(f"{s}|{p}|{o}|{source}".encode("utf-8")).hexdigest()[:16]
    st = KG[f"fact/{h}"]
    g.add((st, RDF.type, RDF.Statement))
    g.add((st, RDF.subject, s))
    g.add((st, RDF.predicate, p))
    g.add((st, RDF.object, o))
    g.add((st, PROV.wasDerivedFrom, source))


def add_extraction(g: Graph, ex: Extraction, url: str, warnings: list[str]) -> None:
    source = URIRef(url)
    iri = {}
    for e in ex.entities:
        node = entity_iri(e.label)
        iri[e.label.strip().lower()] = node
        existing = set(g.objects(node, RDF.type))
        if existing and FL[e.type] not in existing:
            warnings.append(f"type conflict for {e.label}: {e.type} ignored (already {existing.pop().split('#')[-1]})")
        elif not existing:
            g.add((node, RDF.type, FL[e.type]))
        if not any(g.objects(node, RDFS.label)):
            g.add((node, RDFS.label, Literal(e.label.strip(), lang="pt")))
        elif e.label.strip() != str(g.value(node, RDFS.label)):
            g.add((node, SKOS.altLabel, Literal(e.label.strip(), lang="pt")))
        for alias in e.aliases:
            g.add((node, SKOS.altLabel, Literal(alias.strip(), lang="pt")))
        g.add((node, PROV.wasDerivedFrom, source))
        if e.definition:
            add_fact(g, node, FL.definition, Literal(e.definition.strip(), lang="pt"), source)
        for code in e.topics:
            add_fact(g, node, FL.hasTopic, FL[f"t-{code}"], source)

    for r in ex.relations:
        s = iri[r.subject.strip().lower()]
        if r.relation == "regulatedBy":
            o = FL[REGULATOR_IRIS[r.object]]
        else:
            o = iri[r.object.strip().lower()]
        add_fact(g, s, FL[r.relation], o, source)


def load_extractions(paths: list[str], warnings: list[str]) -> Graph:
    """Each line: {"url": ..., "extraction": {"entities": [...], "relations": [...]}}"""
    g = Graph()
    bind_prefixes(g)
    for path in paths:
        for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            rec = json.loads(line)
            try:
                ex = Extraction.model_validate(rec["extraction"])
            except ValidationError as err:
                warnings.append(f"{Path(path).name}:{n} rejected by Pydantic: {err.error_count()} error(s)")
                continue
            warnings.extend(ex.drop_dangling())
            add_extraction(g, ex, rec["url"], warnings)
    return g


def shacl_filter(data: Graph) -> tuple[Graph, list[str]]:
    """Validate with pySHACL and remove failing facts until the graph conforms; return (graph, report lines)."""
    background = Graph().parse(KG_DIR / "ontology.ttl").parse(KG_DIR / "topics.ttl")
    shapes = Graph().parse(KG_DIR / "shapes.ttl")
    clean = Graph()
    bind_prefixes(clean)
    clean += data
    lines: list[str] = []

    for _ in range(5):
        conforms, report, _ = validate(clean + background, shacl_graph=shapes, advanced=True)
        if conforms:
            break
        for result in report.subjects(RDF.type, SH.ValidationResult):
            focus = report.value(result, SH.focusNode)
            path = report.value(result, SH.resultPath)
            value = report.value(result, SH.value)
            msg = report.value(result, SH.resultMessage)
            lines.append(f"- {clean.qname(focus) if isinstance(focus, URIRef) else focus} | "
                         f"{clean.qname(path) if path else '-'} | {value if value is not None else '-'} | {msg}")
            if report.value(result, SH.sourceShape) == FL.ProductOnlyShape:
                for p in (FL.hasCost, FL.hasRisk, FL.regulatedBy):
                    clean.remove((focus, p, None))
            elif (focus, RDF.type, RDF.Statement) in clean:
                triple = (clean.value(focus, RDF.subject), clean.value(focus, RDF.predicate),
                          clean.value(focus, RDF.object))
                if None not in triple:
                    clean.remove(triple)
                clean.remove((focus, None, None))
            elif value is not None and path is not None:
                clean.remove((focus, path, value))
            else:
                clean.remove((focus, None, None))
                clean.remove((None, None, focus))

        for st in list(clean.subjects(RDF.type, RDF.Statement)):
            triple = (clean.value(st, RDF.subject), clean.value(st, RDF.predicate), clean.value(st, RDF.object))
            if None in triple or triple not in clean:
                clean.remove((st, None, None))
    return clean, lines


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", nargs="+", default=[str(OUT_DIR / "extractions" / "*.jsonl")])
    ap.add_argument("--output", type=Path, default=OUT_DIR / "kg.ttl")
    ap.add_argument("--no-shacl", action="store_true", help="ablation: skip the SHACL filter")
    args = ap.parse_args()

    paths = sorted({p for pattern in args.input for p in glob.glob(pattern)})
    if not paths:
        print(f"No extraction files in {args.input}")
        return
    warnings: list[str] = []
    g = load_extractions(paths, warnings)
    n_facts = len(list(g.subjects(RDF.type, RDF.Statement)))
    print(f"Read {len(paths)} file(s): {len(g)} triples, {n_facts} sourced facts")
    for w in warnings:
        print(f"  [warning] {w}")

    report_lines = []
    if not args.no_shacl:
        g, report_lines = shacl_filter(g)
        kept = len(list(g.subjects(RDF.type, RDF.Statement)))
        print(f"SHACL: {len(report_lines)} violation(s); facts kept: {kept}/{n_facts}")
        for line in report_lines:
            print("  " + line)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(args.output, format="turtle")
    report_path = args.output.with_name(args.output.stem + "_shacl_report.txt")
    report_path.write_text("\n".join(report_lines) or "No violations.", encoding="utf-8")
    print(f"Written: {args.output} ({len(g)} triples) and {report_path.name}")


if __name__ == "__main__":
    main()
