"""Baseline (a): the LLM alone, no documents; abstention only by prompt instruction."""
from __future__ import annotations

from generation.llm import ABSTAIN, chat

SYSTEM = f"""És um assistente de literacia financeira para consumidores em Portugal.
Responde em português europeu, de forma curta e factual (no máximo 3 frases).
Se a pergunta pedir um conselho pessoal (o que a pessoa deve fazer com o seu dinheiro) ou se não
tiveres a certeza da resposta, responde exatamente: "{ABSTAIN}" """


def answer(question: str, model: str) -> dict:
    text = chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}], model=model)
    return {"answer": text, "contexts": []}
