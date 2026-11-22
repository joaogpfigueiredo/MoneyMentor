"""Shared scraping helpers: polite HTTP session, text extraction, topic guess and JSONL writer."""
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

USER_AGENT = "MealheiroBot/0.1 (Knowledge and Language academic project, University of Coimbra)"
MIN_WORDS = 80

TITLE_SUFFIX = re.compile(r"\s+[-|–]\s+(Site .*|ASF|Banco de Portugal|Todos Contam|Portal do Cliente Banc[aá]rio)$")
BOILERPLATE_LINES = {"Migalhas de pão", "Partilhar", "Imprimir", "Voltar ao topo"}

CHALLENGE_MARKERS = (
    "Just a moment...",
    "Attention Required! | Cloudflare",
    "A verificar se a ligação é segura",
    "Checking if the site connection is secure",
)


class BlockedError(Exception):
    """The site answered with an anti-bot challenge; we stop instead of bypassing it."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PoliteSession:
    """HTTP session that honours robots.txt and spaces out requests."""

    def __init__(self, min_delay: float = 1.0, max_delay: float = 2.0):
        self.http = requests.Session()
        self.http.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "pt-PT,pt;q=0.9"})
        self.min_delay, self.max_delay = min_delay, max_delay
        self._last_request = 0.0
        self._robots: dict[str, robotparser.RobotFileParser] = {}

    def _robots_for(self, url: str) -> robotparser.RobotFileParser:
        p = urlparse(url)
        root = f"{p.scheme}://{p.netloc}"
        if root not in self._robots:
            rp = robotparser.RobotFileParser()
            try:
                r = self.http.get(root + "/robots.txt", timeout=20)
                if r.status_code in (401, 403):
                    rp.disallow_all = True
                elif r.status_code >= 400:
                    rp.allow_all = True
                else:
                    rp.parse(r.text.splitlines())
            except requests.RequestException:
                rp.disallow_all = True
            rp.modified()
            self._robots[root] = rp
        return self._robots[root]

    def allowed(self, url: str) -> bool:
        return self._robots_for(url).can_fetch(USER_AGENT, url)

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
        """Return the 200 response, or None if robots.txt forbids it or it fails; raise BlockedError on a challenge."""
        if not self.allowed(url):
            print(f"  [robots.txt] disallowed: {url}")
            return None
        self._wait(url)
        try:
            r = self.http.get(url, timeout=30)
        except requests.RequestException as e:
            print(f"  [error] {url}: {e}")
            return None
        if r.status_code in (403, 429, 503) and any(m in r.text for m in CHALLENGE_MARKERS):
            raise BlockedError(f"{urlparse(url).netloc} returned an anti-bot challenge (HTTP {r.status_code}).")
        if r.status_code != 200:
            print(f"  [HTTP {r.status_code}] {url}")
            return None
        return r


def cache_path(url: str) -> Path:
    return HTML_CACHE_DIR / (hashlib.sha1(url.encode("utf-8")).hexdigest() + ".html")


BLOCK_TAGS = {"h1", "h2", "h3", "h4", "h5", "p", "li", "tr", "dt", "dd", "div", "section", "article", "br", "table", "ul", "ol"}


def _text(el) -> str:
    return " ".join("".join(el.itertext()).split())


def main_text(html: str) -> tuple[str, str]:
    """Fallback extractor: block-aware text of the content area, parsed with html5lib like a browser."""
    doc = html5lib.parse(html, treebuilder="lxml", namespaceHTMLElements=False).getroot()
    title = (doc.findtext(".//title") or "").strip()
    main = (doc.xpath("//main") or doc.xpath('//*[@role="main"]') or [None])[0]
    if main is None or len(_text(main).split()) < MIN_WORDS:
        main = doc.find(".//body")
        if main is None:
            return title, ""
    junk = " or ".join(f"contains(@class,'{c}')" for c in ("menu", "navigation", "footer", "breadcrumb", "cookie"))
    for bad in main.xpath(f".//script|.//style|.//nav|.//header|.//footer|.//form|.//button|.//*[{junk}]"):
        if bad.getparent() is not None:
            bad.getparent().remove(bad)
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
    """Main text and title of an HTML page, or None if it has no useful content."""
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
    """All <a href> links of the page, absolute and without #fragment."""
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
    """Rough topic from the URL and title; the first matching keyword group wins."""
    hay = _normalize(unquote(url).replace("-", " ") + " " + title) + " "
    for topic, words in TOPIC_KEYWORDS:
        if any(w in hay for w in words):
            return topic
    return "outro"


class JsonlWriter:
    """Append records to data/raw/<source>.jsonl, skipping URLs already saved."""

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
