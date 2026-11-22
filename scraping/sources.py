"""Per-source crawl settings: start URLs, allowed URL prefixes and patterns to skip."""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import unquote

COMMON_SKIP = [
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".zip", ".xls", ".xlsx", ".doc", ".docx", ".mp3", ".mp4",
    "/en/", "/user/", "/search", "?", "mailto:", "/print/",
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
    "todoscontam": Source(
        name="todoscontam",
        start_urls=["https://www.todoscontam.pt/"],
        allowed_prefixes=["https://www.todoscontam.pt/"],
    ),
    "bportugal": Source(
        name="bportugal",
        start_urls=["https://clientebancario.bportugal.pt/"],
        allowed_prefixes=["https://clientebancario.bportugal.pt/"],
    ),
    "asf": Source(
        name="asf",
        start_urls=["https://www.consumidor.asf.com.pt/"],
        allowed_prefixes=["https://www.consumidor.asf.com.pt/"],
        skip=["/app-", "podcast", "/documents/", "/web/guest/", "/o/"],
    ),
}
