"""Pydantic schema for the LLM extraction: only ontology classes, relations and topics are allowed."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

EntityType = Literal["Product", "Concept", "Cost", "Risk", "Right"]
RelationType = Literal["hasCost", "hasRisk", "regulatedBy", "relatedTo"]
RegulatorName = Literal["Banco de Portugal", "CMVM", "ASF"]

TopicCode = Literal[
    "necessidades-desejos", "despesas-rendimentos", "risco-incerteza", "planeamento",
    "meios-pagamento", "contas-bancarias", "emprestimos", "sistema-financeiro", "seguros",
    "objetivos-poupanca", "aplicacoes-poupanca",
    "necessidades-capacidades", "custos-credito", "responsabilidades-credito",
    "etica-responsabilidade",
    "informacao-financeira", "prevencao-fraude",
]

REGULATOR_IRIS = {"Banco de Portugal": "BancoDePortugal", "CMVM": "CMVM", "ASF": "ASF"}
REGULATOR_WORDS = ("banco de portugal", "bdp", "cmvm", "asf", "comissão do mercado de valores",
                   "autoridade de supervisão")


class Entity(BaseModel):
    label: str = Field(description="Nome canónico em português, no singular (ex.: 'crédito habitação').")
    type: EntityType
    definition: Optional[str] = Field(None, description="Definição curta retirada do texto, em português.")
    aliases: List[str] = Field(default_factory=list, description="Sinónimos ou siglas (ex.: 'TAEG').")
    topics: List[TopicCode] = Field(default_factory=list)


class Relation(BaseModel):
    subject: str = Field(description="label de uma entidade desta extração")
    relation: RelationType
    object: str = Field(description="label de outra entidade desta extração, ou o supervisor em regulatedBy")


class Extraction(BaseModel):
    entities: List[Entity]
    relations: List[Relation] = Field(default_factory=list)

    def drop_dangling(self) -> List[str]:
        """Drop regulator entities and relations whose endpoints do not exist; return warnings."""
        kept, warnings = [], []
        regulators = [e for e in self.entities
                      if any(w == e.label.strip().lower() or e.label.lower().startswith(w) for w in REGULATOR_WORDS)]
        for e in regulators:
            warnings.append(f"entity dropped (it is a regulator): {e.label}")
        self.entities = [e for e in self.entities if e not in regulators]
        labels = {e.label.strip().lower() for e in self.entities}
        for r in self.relations:
            subj_ok = r.subject.strip().lower() in labels
            if r.relation == "regulatedBy":
                obj_ok = r.object in REGULATOR_IRIS
            else:
                obj_ok = r.object.strip().lower() in labels
            if subj_ok and obj_ok:
                kept.append(r)
            else:
                warnings.append(f"relation dropped: {r.subject} --{r.relation}--> {r.object}")
        self.relations = kept
        return warnings
