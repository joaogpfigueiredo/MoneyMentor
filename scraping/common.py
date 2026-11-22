"""Peças partilhadas pelos scrapers.

1. PoliteSession: faz pedidos HTTP "educados" (respeita o robots.txt, espera 1-2 s
   entre pedidos e identifica-se com um User-Agent honesto).
2. extract_page: usa o trafilatura para tirar o texto principal de uma página
   (sem menus, rodapés nem cookies).
3. guess_topic: atribui um tema grosseiro por palavras-chave (mais tarde mapeado para SKOS).
4. JsonlWriter: escreve um registo por linha em data/raw/<fonte>.jsonl.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib import robotparser
from urllib.parse import unquote, urldefrag, urlparse

import html5lib
import lxml.html
import requests
import trafilatura

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
HTML_CACHE_DIR = DATA_DIR / "html_cache"

USER_AGENT = "MealheiroBot/0.1 (projeto academico Knowledge and Language, Universidade de Coimbra)"
MIN_WORDS = 80  # páginas com menos palavras são índices/menus, não interessam

# Sufixos de título do género " - Site PC - ASF" ou " | Banco de Portugal"
TITLE_SUFFIX = re.compile(r"\s+[-|–]\s+(Site .*|ASF|Banco de Portugal|Todos Contam|Portal do Cliente Banc[aá]rio)$")
# Linhas de navegação que o trafilatura às vezes deixa passar
BOILERPLATE_LINES = {"Migalhas de pão", "Partilhar", "Imprimir", "Voltar ao topo"}

# Textos que aparecem nas páginas de desafio anti-bot. Se os virmos, PARAMOS:
# contornar estas proteções não é aceitável (nem ética nem legalmente).
CHALLENGE_MARKERS = (
    "Just a moment...",
    "Attention Required! | Cloudflare",
    "A verificar se a ligação é segura",
    "Checking if the site connection is secure",
)


class BlockedError(Exception):
    """O site respondeu com uma página anti-bot: não insistimos."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PoliteSession:
    """Sessão HTTP que respeita o robots.txt e espaça os pedidos."""

    def __init__(self, min_delay: float = 1.0, max_delay: float = 2.0):
        self.http = requests.Session()
        self.http.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "pt-PT,pt;q=0.9"})
        self.min_delay, self.max_delay = min_delay, max_delay
        self._last_request = 0.0
        self._robots: dict[str, robotparser.RobotFileParser] = {}

    # robots.txt
    def _robots_for(self, url: str) -> robotparser.RobotFileParser:
        p = urlparse(url)
        root = f"{p.scheme}://{p.netloc}"
        if root not in self._robots:
            rp = robotparser.RobotFileParser()
            try:
                r = self.http.get(root + "/robots.txt", timeout=20)
                if r.status_code in (401, 403):
                    rp.disallow_all = True  # sem acesso ao robots.txt: por precaução, nada é permitido
                elif r.status_code >= 400:
                    rp.allow_all = True  # o site não tem robots.txt: tudo é permitido
                else:
                    rp.parse(r.text.splitlines())
            except requests.RequestException:
                rp.disallow_all = True
            rp.modified()
            self._robots[root] = rp
        return self._robots[root]

    def allowed(self, url: str) -> bool:
        return self._robots_for(url).can_fetch(USER_AGENT, url)

    # pedidos
    def _wait(self, url: str) -> None:
        delay = random.uniform(self.min_delay, self.max_delay)
        crawl_delay = self._robots_for(url).crawl_delay(USER_AGENT)
        if crawl_delay:
            delay = max(delay, float(crawl_delay))
        elapsed = time.monotonic() - self._last_request
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request = time.monotonic()

    def get(self, url: str) -> Optional[requests.Response]:
        """Devolve a resposta (200), ou None se o robots.txt proibir ou houver erro.
        Lança BlockedError se aparecer um desafio anti-bot."""
        if not self.allowed(url):
            print(f"  [robots.txt] proibido: {url}")
            return None
        self._wait(url)
        try:
            r = self.http.get(url, timeout=30)
        except requests.RequestException as e:
            print(f"  [erro] {url}: {e}")
            return None
        if r.status_code in (403, 429, 503) and any(m in r.text for m in CHALLENGE_MARKERS):
            raise BlockedError(f"{urlparse(url).netloc} devolveu um desafio anti-bot (HTTP {r.status_code}).")
        if r.status_code != 200:
            print(f"  [HTTP {r.status_code}] {url}")
            return None
        return r


# Cache de HTML: permite voltar a extrair texto sem voltar a pedir as páginas
def cache_path(url: str) -> Path:
    return HTML_CACHE_DIR / (hashlib.sha1(url.encode("utf-8")).hexdigest() + ".html")


# Extração
BLOCK_TAGS = {"h1", "h2", "h3", "h4", "h5", "p", "li", "tr", "dt", "dd", "div", "section", "article", "br", "table", "ul", "ol"}


def _text(el) -> str:
    return " ".join("".join(el.itertext()).split())


def main_text(html: str) -> tuple[str, str]:
    """Plano B: texto dos blocos (títulos, parágrafos, listas, tabelas) da zona de conteúdo.
    Usado quando o trafilatura não reconhece a estrutura da página (ex.: Portal do Cliente Bancário).
    O html5lib lê o HTML com as mesmas regras do browser: o HTML do BdP tem tags mal fechadas e
    o parser do lxml punha o conteúdo "dentro" do menu."""
    doc = html5lib.parse(html, treebuilder="lxml", namespaceHTMLElements=False).getroot()
    title = (doc.findtext(".//title") or "").strip()
    main = (doc.xpath("//main") or doc.xpath('//*[@role="main"]') or [None])[0]
    if main is None or len(_text(main).split()) < MIN_WORDS:
        # No Portal do Cliente Bancário o texto fica fora do <main>: usa-se o <body> sem menus nem rodapé
        main = doc.find(".//body")
        if main is None:
            return title, ""
    junk = " or ".join(f"contains(@class,'{c}')" for c in ("menu", "navigation", "footer", "breadcrumb", "cookie"))
    for bad in main.xpath(f".//script|.//style|.//nav|.//header|.//footer|.//form|.//button|.//*[{junk}]"):
        if bad.getparent() is not None:
            bad.getparent().remove(bad)
    # Uma quebra de linha à volta de cada bloco (div, p, br, títulos, listas...) e depois o texto todo:
    # assim apanha-se também texto solto dentro de <div> ou entre <br>, que o trafilatura perde
    for el in main.iter():
        if isinstance(el.tag, str) and el.tag in BLOCK_TAGS:
            el.text = "\n" + (el.text or "")
            el.tail = "\n" + (el.tail or "")
    lines = []
    for raw in "".join(main.itertext()).split("\n"):
        line = " ".join(raw.split())
        if line and (not lines or line != lines[-1]):
            lines.append(line)
    return title, "\n".join(lines)


def extract_page(html: str, url: str) -> Optional[dict]:
    """Texto principal e título de uma página HTML, ou None se não houver conteúdo útil."""
    out = trafilatura.extract(
        html,
        url=url,
        output_format="json",
        with_metadata=True,
        include_comments=False,
        include_tables=True,
        favor_precision=True,
    )
    data = json.loads(out) if out else {}
    text, title = data.get("text") or "", data.get("title") or ""
    fallback_title, fallback = main_text(html)
    if len(fallback.split()) > 1.2 * len(text.split()):
        # O trafilatura perdeu texto (acordeões, texto fora de <p>, página fora do <main>): usa o plano B
        title, text = title or fallback_title, fallback
    lines = [ln for ln in text.splitlines() if ln.strip() not in BOILERPLATE_LINES]
    text = "\n".join(lines).strip()
    if len(text.split()) < MIN_WORDS:
        return None
    title = title.strip()
    while TITLE_SUFFIX.search(title):
        title = TITLE_SUFFIX.sub("", title)
    return {"title": title, "text": text}


def extract_links(html: str, base_url: str) -> set[str]:
    """Todos os links <a href> da página, em forma absoluta e sem #fragmento."""
    try:
        doc = lxml.html.fromstring(html)
    except (ValueError, lxml.etree.ParserError):
        return set()
    doc.make_links_absolute(base_url, resolve_base_href=True)
    links = set()
    for el, attr, link, _ in doc.iterlinks():
        if el.tag == "a" and attr == "href" and link.startswith("http"):
            links.add(urldefrag(link)[0])
    return links


# Tema por palavras-chave. A ordem conta: ganha o primeiro tema que aparecer.
TOPIC_KEYWORDS = [
    ("seguros", ["seguro", "sinistro", "apolice", "resseguro"]),
    ("credito", ["credito", "emprestimo", "hipoteca", "habitacao", "consolidado", "leasing", "locacao"]),
    ("juros", ["juro", "taeg", "tan ", "euribor", "indexante", "spread"]),
    ("depositos", ["deposito", "poupanca", "conta-servicos-minimos", "conta a ordem", "conta-a-ordem"]),
    ("investimento", ["investi", "acoes", "obrigac", "fundo", "cripto", "valores mobiliarios", "ppr"]),
    ("pagamentos", ["pagamento", "transferencia", "cartao", "mb way", "cheque", "comissao", "comissoes"]),
    ("direitos", ["reclama", "direito", "fraude", "burla", "phishing", "livro de reclamacoes"]),
    ("orcamento", ["orcamento", "divida", "endividamento", "planeamento financeiro"]),
]


def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def guess_topic(url: str, title: str) -> str:
    """Tema aproximado a partir do URL e do título. É só uma etiqueta inicial;
    o KG usa depois os temas SKOS do Referencial de Educação Financeira."""
    hay = _normalize(unquote(url).replace("-", " ") + " " + title) + " "
    for topic, words in TOPIC_KEYWORDS:
        if any(w in hay for w in words):
            return topic
    return "outro"


# Escrita
class JsonlWriter:
    """Acrescenta registos a data/raw/<fonte>.jsonl e ignora URLs já guardados (para retomar)."""

    def __init__(self, source: str):
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        self.path = RAW_DIR / f"{source}.jsonl"
        self.source = source
        self.done: set[str] = set()
        if self.path.exists():
            with self.path.open(encoding="utf-8") as f:
                self.done = {json.loads(line)["url"] for line in f if line.strip()}

    def write(self, url: str, title: str, text: str, retrieved_at: Optional[str] = None) -> bool:
        if url in self.done:
            return False
        record = {
            "url": url,
            "title": title,
            "text": text,
            "source": self.source,
            "topic": guess_topic(url, title),
            "retrieved_at": retrieved_at or utc_now(),
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.done.add(url)
        return True
