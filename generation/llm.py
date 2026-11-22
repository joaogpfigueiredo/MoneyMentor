"""Chamada ao LLM local (Ollama), partilhada pelos baselines e pelo sistema final.

Porquê um módulo só: os três sistemas a comparar usam o mesmo modelo e as mesmas opções,
para que a única diferença entre eles seja o contexto que o LLM recebe (nada, texto, ou KG + texto).
"""
from __future__ import annotations

import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "qwen3:8b"
ABSTAIN = "Não posso responder com segurança."  # frase fixa: torna a abstenção fácil de detetar


def chat(messages: list[dict], model: str = DEFAULT_MODEL, temperature: float = 0.0,
         num_ctx: int = 4096, num_predict: int = 400) -> str:
    resp = requests.post(OLLAMA_URL, timeout=900, json={
        "model": model,
        "messages": messages,
        "stream": False,
        "think": False,  # Qwen3: resposta direta, sem "raciocínio" escondido
        "options": {"temperature": temperature, "num_ctx": num_ctx, "num_predict": num_predict},
    })
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def is_abstention(answer: str) -> bool:
    return "não posso responder" in answer.lower()
