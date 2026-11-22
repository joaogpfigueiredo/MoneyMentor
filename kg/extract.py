"""Extração de factos com um LLM local (Ollama), restrita à ontologia.

Para cada página de data/raw/<fonte>.jsonl:
  1. Divide o texto em pedaços de ~400 palavras (um modelo de 8B extrai melhor de textos curtos).
  2. Envia ao LLM um prompt com a ontologia (classes, relações, temas) e um exemplo.
  3. Passa ao Ollama o JSON Schema do kg/schema.py: o modelo só pode gerar JSON com
     aquela forma (structured outputs). Temperatura 0 para ser reprodutível.
  4. Valida com Pydantic; se falhar, tenta mais uma vez e mostra ao modelo o erro.
  5. Grava em data/kg/extractions/<fonte>.jsonl. Depois corre-se:  python -m kg.build_kg

Uso:
  python -m kg.extract --source asf --limit 3           # testar com 3 páginas
  python -m kg.extract --source asf --match "seguro de"  # só páginas com isto no título
  python -m kg.extract --source asf --model qwen3:8b    # tudo (retoma onde parou)
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Optional

import requests
from pydantic import ValidationError

from .schema import Extraction

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "kg" / "extractions"
OLLAMA_URL = "http://localhost:11434/api/chat"
CHUNK_WORDS = 400

SYSTEM_PROMPT = """És um extrator de conhecimento sobre literacia financeira em Portugal.
Lês um excerto de uma página oficial (Banco de Portugal, CMVM, ASF ou Todos Contam) e devolves JSON.

TIPOS DE ENTIDADE (usa só estes):
- Product: produto que um consumidor pode contratar (depósito a prazo, crédito habitação, seguro de vida, PPR, cartão de crédito).
- Concept: ideia financeira que não é um produto (inflação, juro composto, spread, Euribor, TAEG como conceito).
- Cost: dinheiro que o CONSUMIDOR paga por um produto (comissão de manutenção, prémio de seguro, juros, franquia,
  imposto do selo). Prazos, reembolsos, períodos e obrigações NÃO são custos: são Concept.
- Risk: algo que pode correr mal ao consumidor (risco de taxa de juro, perda de capital, sobre-endividamento).
- Right: direito legal do consumidor (livre resolução, reembolso antecipado, reclamação, serviços mínimos bancários).

RELAÇÕES (usa só estas):
- hasCost: Product -> Cost
- hasRisk: Product -> Risk
- regulatedBy: Product -> "Banco de Portugal" | "CMVM" | "ASF"
- relatedTo: qualquer entidade -> qualquer entidade (só se o texto as ligar explicitamente)

TEMAS (campo topics; códigos do Referencial de Educação Financeira):
necessidades-desejos, despesas-rendimentos, risco-incerteza, planeamento, meios-pagamento,
contas-bancarias, emprestimos, sistema-financeiro, seguros, objetivos-poupanca, aplicacoes-poupanca,
necessidades-capacidades, custos-credito, responsabilidades-credito, etica-responsabilidade,
informacao-financeira, prevencao-fraude

REGRAS:
1. Extrai SÓ o que está escrito no excerto. Não uses conhecimento próprio. Na dúvida, não incluas.
2. label: nome em português europeu, minúsculas, singular (ex.: "depósito a prazo").
3. definition: uma ou duas frases tiradas do texto, em português. Omite se o texto não definir a entidade.
4. Nas relações, subject e object têm de ser labels de entidades que listaste (exceto o supervisor em regulatedBy).
   Usa regulatedBy só se o texto disser que aquele produto é supervisionado por essa entidade.
5. NÃO cries entidades para o Banco de Portugal, a CMVM, a ASF nem para empresas: os supervisores só aparecem em regulatedBy.
6. Temas: usa os de crédito (necessidades-capacidades, custos-credito, responsabilidades-credito) só para crédito
   e empréstimos; seguros usa "seguros"; no máximo 2 temas por entidade.
7. Ignora menus, avisos de cookies, contactos e notícias institucionais.
8. Se o excerto não tiver conhecimento útil, devolve {"entities": [], "relations": []}."""

# Exemplo (anotado à mão) que mostra ao modelo o formato e o nível de detalhe pretendidos
EXAMPLE_TEXT = (
    "O seguro multirriscos oferece um conjunto de coberturas facultativas de danos no imóvel ou no seu "
    "recheio, podendo também incluir uma cobertura de responsabilidade civil. O prémio é calculado em "
    "função das coberturas contratadas. Em relação à habitação, o único seguro obrigatório é o seguro de "
    "incêndio, apenas para os edifícios em regime de propriedade horizontal."
)
EXAMPLE_JSON = {
    "entities": [
        {"label": "seguro multirriscos habitação", "type": "Product", "aliases": ["seguro multirriscos"],
         "definition": "Seguro com um conjunto de coberturas facultativas de danos no imóvel ou no seu recheio, que pode incluir responsabilidade civil.",
         "topics": ["seguros"]},
        {"label": "prémio de seguro", "type": "Cost",
         "definition": "Valor pago pelo seguro, calculado em função das coberturas contratadas.", "topics": ["seguros"]},
        {"label": "seguro de incêndio", "type": "Product",
         "definition": "Único seguro obrigatório na habitação, apenas para edifícios em regime de propriedade horizontal.",
         "topics": ["seguros"]},
    ],
    "relations": [
        {"subject": "seguro multirriscos habitação", "relation": "hasCost", "object": "prémio de seguro"},
        {"subject": "seguro multirriscos habitação", "relation": "relatedTo", "object": "seguro de incêndio"},
    ],
}


def chunk_text(text: str, max_words: int = CHUNK_WORDS) -> list[str]:
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


def build_messages(title: str, chunk: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Título: Seguro de Habitação\n\nExcerto:\n{EXAMPLE_TEXT}"},
        {"role": "assistant", "content": json.dumps(EXAMPLE_JSON, ensure_ascii=False)},
        {"role": "user", "content": f"Título: {title}\n\nExcerto:\n{chunk}"},
    ]


NUM_CTX = 4096  # prompt (~1500 tokens) + resposta; menos contexto = menos memória na GPU
NUM_PREDICT = 2048  # máximo de tokens da resposta


def call_llm(messages: list[dict], model: str) -> str:
    resp = requests.post(OLLAMA_URL, timeout=600, json={
        "model": model,
        "messages": messages,
        "format": Extraction.model_json_schema(),  # restringe a geração ao esquema da ontologia
        "stream": False,
        "think": False,                            # Qwen3: sem "raciocínio" escondido, resposta direta
        # num_predict limita a resposta: evita que o modelo entre em ciclo a repetir entidades
        "options": {"temperature": 0, "num_ctx": NUM_CTX, "num_predict": NUM_PREDICT},
    })
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def extract_chunk(title: str, chunk: str, model: str, retries: int = 1) -> Optional[Extraction]:
    messages = build_messages(title, chunk)
    for attempt in range(retries + 1):
        try:
            raw = call_llm(messages, model)
        except requests.exceptions.Timeout:
            print("    [timeout] o modelo demorou demasiado; salto este pedaço", flush=True)
            return None
        try:
            return Extraction.model_validate_json(raw)
        except ValidationError as err:
            if attempt == retries:
                print(f"    [inválido] desisto deste pedaço: {err.error_count()} erro(s)")
                return None
            # Mostra o erro ao modelo e pede outra vez
            messages += [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"O JSON não é válido: {err}. Corrige e devolve só o JSON."},
            ]
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, help="nome do ficheiro em data/raw (ex.: asf)")
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--limit", type=int, default=None, help="só as primeiras N páginas (para testar)")
    ap.add_argument("--out", type=Path, default=None, help="ficheiro de saída (por omissão data/kg/extractions/<fonte>.jsonl)")
    ap.add_argument("--match", default=None, help="só páginas cujo título contenha este texto")
    args = ap.parse_args()

    pages = [json.loads(l) for l in (RAW_DIR / f"{args.source}.jsonl").open(encoding="utf-8") if l.strip()]
    if args.match:
        pages = [p for p in pages if args.match.lower() in p["title"].lower()]
    pages = pages[: args.limit] if args.limit else pages
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = args.out or OUT_DIR / f"{args.source}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    done = set()
    if out_path.exists():
        for line in out_path.open(encoding="utf-8"):
            rec = json.loads(line)
            done.add((rec["url"], rec["chunk"]))

    with out_path.open("a", encoding="utf-8") as out:
        for i, page in enumerate(pages, 1):
            chunks = chunk_text(page["text"])
            print(f"[{i}/{len(pages)}] {page['title'][:60]} ({len(chunks)} pedaço(s))", flush=True)
            for c, chunk in enumerate(chunks):
                if (page["url"], c) in done:
                    continue
                t0 = time.time()
                ex = extract_chunk(page["title"], chunk, args.model)
                if ex is None:
                    continue
                out.write(json.dumps({
                    "url": page["url"], "chunk": c, "model": args.model,
                    "extraction": ex.model_dump(),
                }, ensure_ascii=False) + "\n")
                out.flush()
                print(f"    pedaço {c}: {len(ex.entities)} entidades, {len(ex.relations)} relações ({time.time() - t0:.0f}s)", flush=True)
    print(f"\nEscrito: {out_path}\nA seguir:  python -m kg.build_kg")


if __name__ == "__main__":
    main()
