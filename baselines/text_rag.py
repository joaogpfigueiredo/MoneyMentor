"""Baseline (b): RAG só com texto (réplica simples de Eleuterio et al., SLATE 2025).

Porquê: é a abordagem habitual. O LLM recebe as 5 passagens do corpus mais parecidas com a
pergunta (BGE-M3 + FAISS, retrieval/text_index.py), responde só com base nelas e cita-as com [n].
O nosso sistema (c) acrescenta os factos do KG a isto, por isso a comparação (b) vs (c) mede o KG.
"""
from __future__ import annotations

from generation.llm import ABSTAIN, chat

K = 5

SYSTEM = f"""És um assistente de literacia financeira para consumidores em Portugal.
Recebes uma pergunta e passagens numeradas de fontes oficiais (Banco de Portugal, CMVM, ASF, Todos Contam).
Regras:
1. Responde em português europeu, de forma curta (no máximo 3 frases), usando SÓ a informação das passagens.
2. Cita as passagens que usaste com o número entre parênteses retos, por exemplo [2].
3. Se as passagens não tiverem a resposta, ou se a pergunta pedir um conselho pessoal (o que a pessoa deve
   fazer com o seu dinheiro), responde exatamente: "{ABSTAIN}" """


def build_prompt(question: str, passages: list[dict]) -> str:
    blocks = [f"[{i}] {p['title']} ({p['url']})\n{p['text']}" for i, p in enumerate(passages, 1)]
    return "Passagens:\n\n" + "\n\n".join(blocks) + f"\n\nPergunta: {question}"


def answer(question: str, model: str, passages: list[dict]) -> dict:
    text = chat([{"role": "system", "content": SYSTEM},
                 {"role": "user", "content": build_prompt(question, passages)}], model=model)
    return {"answer": text,
            "contexts": [{"url": p["url"], "title": p["title"], "score": round(p["score"], 4), "text": p["text"]}
                         for p in passages]}
