"""Configuração de cada fonte: onde começar e que links seguir.

O crawler só segue links que comecem por um dos `allowed_prefixes` e que não
contenham nenhum dos `skip`. Assim fica no site certo, na versão portuguesa,
e não descarrega imagens, PDFs nem páginas de pesquisa.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import unquote

# Extensões e padrões a ignorar em todas as fontes
COMMON_SKIP = [
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".zip", ".xls", ".xlsx", ".doc", ".docx", ".mp3", ".mp4",
    "/en/", "/user/", "/search", "?", "mailto:", "/print/",
    # páginas legais/institucionais sem conteúdo financeiro
    "privacidade", "cookies", "direitos-de-autor", "termos-e-condi", "acessibilidade", "mapa-do-site",
]


@dataclass
class Source:
    name: str
    start_urls: list[str]
    allowed_prefixes: list[str]
    skip: list[str] = field(default_factory=list)

    def accepts(self, url: str) -> bool:
        if not any(url.startswith(p) for p in self.allowed_prefixes):
            return False
        lowered = unquote(url).lower()
        return not any(s in lowered for s in COMMON_SKIP + self.skip)


SOURCES = {
    # Plano Nacional de Formação Financeira (BdP, CMVM e ASF).
    # Nota (09/11/2026): o site está atrás de Cloudflare e devolve um desafio anti-bot.
    # Usar import_saved_html.py com páginas guardadas no browser.
    "todoscontam": Source(
        name="todoscontam",
        start_urls=["https://www.todoscontam.pt/"],
        allowed_prefixes=["https://www.todoscontam.pt/"],
    ),
    # Portal do Cliente Bancário do Banco de Portugal.
    # Nota (09/11/2026): devolve um desafio anti-bot ("A verificar se a ligação é segura").
    "bportugal": Source(
        name="bportugal",
        start_urls=["https://clientebancario.bportugal.pt/"],
        allowed_prefixes=["https://clientebancario.bportugal.pt/"],
    ),
    # Portal do Consumidor da ASF (seguros e fundos de pensões). Acessível e permitido pelo robots.txt.
    "asf": Source(
        name="asf",
        start_urls=["https://www.consumidor.asf.com.pt/"],
        allowed_prefixes=["https://www.consumidor.asf.com.pt/"],
        skip=["/app-", "podcast", "/documents/", "/web/guest/", "/o/"],
    ),
}
