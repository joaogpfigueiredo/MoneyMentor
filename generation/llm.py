"""Shared local LLM call (Ollama), so all compared systems use the same model and options."""
from __future__ import annotations

import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "qwen3:8b"
ABSTAIN = "Não posso responder com segurança."


def chat(messages: list[dict], model: str = DEFAULT_MODEL, temperature: float = 0.0,
         num_ctx: int = 4096, num_predict: int = 400) -> str:
    resp = requests.post(OLLAMA_URL, timeout=900, json={
        "model": model,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {"temperature": temperature, "num_ctx": num_ctx, "num_predict": num_predict},
    })
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def is_abstention(answer: str) -> bool:
    return "não posso responder" in answer.lower()
