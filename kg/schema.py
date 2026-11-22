"""Esquema Pydantic da extração: a ontologia vista do lado do LLM.

O LLM recebe um excerto de texto e devolve JSON com este formato. Os tipos `Literal`
fazem com que só existam as classes, relações e temas da ontologia. Qualquer outra coisa
é rejeitada pela validação, e o JSON Schema gerado daqui é passado ao Ollama para
restringir a própria geração (structured outputs).

Fica em dois níveis:
  1. Pydantic (aqui): forma do JSON, valores permitidos.       -> erro = pedir de novo ao LLM
  2. SHACL (shapes.ttl): regras sobre o grafo já construído.     -> erro = facto descartado/auditado
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

EntityType = Literal["Product", "Concept", "Cost", "Risk", "Right"]
RelationType = Literal["hasCost", "hasRisk", "regulatedBy", "relatedTo"]
RegulatorName = Literal["Banco de Portugal", "CMVM", "ASF"]

# Códigos dos subtemas em kg/topics.ttl (fl:t-<código>)
TopicCode = Literal[
    "necessidades-desejos", "despesas-rendimentos", "risco-incerteza", "planeamento",
    "meios-pagamento", "contas-bancarias", "emprestimos", "sistema-financeiro", "seguros",
    "objetivos-poupanca", "aplicacoes-poupanca",
    "necessidades-capacidades", "custos-credito", "responsabilidades-credito",
    "etica-responsabilidade",
    "informacao-financeira", "prevencao-fraude",
]

REGULATOR_IRIS = {"Banco de Portugal": "BancoDePortugal", "CMVM": "CMVM", "ASF": "ASF"}
# Nomes que NÃO podem ser entidades extraídas: os supervisores já existem na ontologia
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
        """Remove relações cujas pontas não existem e devolve avisos.
        Não rejeitamos a extração toda por causa de uma relação má."""
        kept, warnings = [], []
        regulators = [e for e in self.entities
                      if any(w == e.label.strip().lower() or e.label.lower().startswith(w) for w in REGULATOR_WORDS)]
        for e in regulators:
            warnings.append(f"entidade descartada (é um supervisor): {e.label}")
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
                warnings.append(f"relação descartada: {r.subject} --{r.relation}--> {r.object}")
        self.relations = kept
        return warnings
