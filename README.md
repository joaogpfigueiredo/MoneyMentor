# MEALHEIRO

Chatbot de literacia financeira em português europeu, assente num Knowledge Graph (RDF) construído a
partir de fontes oficiais portuguesas. Cita as fontes e abstém-se quando a confiança é baixa.
Projeto de Knowledge and Language 2026/27 (MEI, Universidade de Coimbra), de João Figueiredo e Tiago Alves.

**Guia (como correr, como apresentar, perguntas prováveis): [docs/GUIA.md](docs/GUIA.md).
Manual de estudo (a teoria de cada peça e como está aplicada): [docs/MANUAL.md](docs/MANUAL.md).**

## Instalação

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt # ou só o passo 1: pip install requests trafilatura
```

## Estrutura

```
scraping/      1. recolha das páginas oficiais          -> data/raw/<fonte>.jsonl
kg/            3. ontologia fl:, extração LLM, SHACL, Fuseki
retrieval/     4. pedaços + BGE-M3 + FAISS; entity linking + SPARQL
generation/    4. resposta com Ollama, com citações
uncertainty/   5. semantic entropy + sinais do KG + regressão logística
baselines/     2. (a) só o LLM; (b) RAG só com texto
eval/          6. questions.jsonl, métricas, ablações
app/           7. interface Streamlit
data/          dados (raw/ vai para o git; html_cache/ e manual_html/ não)
docs/          enunciado, revisão da literatura e proposta
```

## Passo 1: recolha do corpus

Cada página dá uma linha JSON em `data/raw/<fonte>.jsonl`:

```json
{"url": "...", "title": "...", "text": "...", "source": "asf", "topic": "seguros", "retrieved_at": "2026-11-09T12:25:45+00:00"}
```

### Crawler automático (sites que o permitem)

```bash
python -m scraping.crawl --source asf --max-pages 300
python -m scraping.stats
```

Respeita o `robots.txt`, espera 1 a 2 s entre pedidos, identifica-se como `MealheiroBot` e guarda o HTML
em `data/html_cache/`, de modo que voltar a correr não repete pedidos.

### Importação manual (Todos Contam e Portal do Cliente Bancário)

Estes dois sites estão atrás de proteção anti-bot (Cloudflare e a verificação do Banco de Portugal) e
devolvem `403` a qualquer cliente automático, apesar de o `robots.txt` permitir as páginas. **Não
contornamos estas proteções.** Em alternativa:

1. Abrir a página no browser e guardar com **Ctrl+S → "Página Web, apenas HTML"** em
   `data/manual_html/todoscontam/` ou `data/manual_html/bportugal/`.
2. Correr:
   ```bash
   python -m scraping.import_saved_html --source todoscontam
   python -m scraping.import_saved_html --source bportugal
   ```

Em alternativa, as páginas podem ser recolhidas num browser real para um único JSON `{url: html}` e divididas com
`python -m scraping.split_browser_bundle <ficheiro.json> --source bportugal`.

O script recupera o URL original da página (`<link rel="canonical">`, `og:url` ou o comentário
`saved from url`), extrai o texto com o trafilatura e escreve o mesmo formato JSONL.

## Passo 2: índice de texto e baselines

```bash
ollama pull bge-m3
python -m retrieval.text_index build                    # 292 pedaços de ~300 palavras -> data/index/
python -m retrieval.text_index search "O que é a TANB?"
python -m baselines.run --system a                      # (a) só o LLM        -> eval/results/a_llm_only.jsonl
python -m baselines.run --system b                      # (b) RAG só com texto -> eval/results/b_text_rag.jsonl
```

Os dois usam o mesmo LLM (`qwen3:8b`, temperatura 0, via `generation/llm.py`) e abstêm-se por instrução no
prompt, com uma frase fixa ("Não posso responder com segurança."). O (b) recebe as 5 passagens mais
parecidas (BGE-M3 no Ollama + FAISS) e cita-as com `[n]`.

## Perguntas de teste

`eval/questions.jsonl`: 75 perguntas de teste (25 conceptuais, 12 numéricas, 10 multi-salto,
14 sem resposta no corpus, 14 pedidos de conselho pessoal). As que têm resposta trazem `gold_answer`,
`source_url` e `evidence` (citação literal da página, verificada automaticamente).

## Passo 3: Knowledge Graph

| Ficheiro | O que é |
|---|---|
| `kg/ontology.ttl` | ontologia `fl:`: 6 classes + `Topic`, 6 relações, os 3 supervisores |
| `kg/topics.ttl` | os 6 temas e 17 subtemas do Referencial de Educação Financeira (2013), em SKOS |
| `kg/shapes.ttl` | regras SHACL: tipos certos, supervisor válido, tema existente, todo o facto com fonte |
| `kg/schema.py` | esquema Pydantic que o LLM tem de seguir (a ontologia vista do lado do LLM) |
| `kg/extract.py` | LLM (Ollama) lê cada página em pedaços de ~400 palavras e devolve JSON restrito ao `schema.py` → `data/kg/extractions/` |
| `kg/build_kg.py` | extrações JSON → RDF (com `rdf:Statement` + `prov:wasDerivedFrom`) → SHACL → `data/kg/kg.ttl` |
| `kg/sparql.py` | consultas SPARQL (factos a 1 salto com fonte), no rdflib ou no Fuseki |
| `kg/load_fuseki.py` | carrega tudo no Fuseki |
| `kg/examples/` | `asf_manual.jsonl` (factos anotados à mão de 2 páginas da ASF) e `erros_de_proposito.jsonl` (demonstração do SHACL) |

```bash
ollama pull qwen3:8b
python -m kg.extract --source asf --limit 3     # extração com LLM (retoma onde parou)
python -m kg.build_kg                           # usa data/kg/extractions/*.jsonl

python -m kg.build_kg --input kg/examples/asf_manual.jsonl --output data/kg/exemplo.ttl
python -m kg.build_kg --input kg/examples/erros_de_proposito.jsonl --output data/kg/erros.ttl   # SHACL a apanhar erros
python -m kg.build_kg --no-shacl ...                                                              # ablação sem SHACL
python -m kg.sparql "seguro multirriscos" --kg data/kg/exemplo.ttl

docker compose up -d            # Fuseki em http://localhost:3030 (admin / mealheiro)
python -m kg.load_fuseki --kg data/kg/exemplo.ttl
python -m kg.sparql "seguro de incêndio" --endpoint http://localhost:3030/mealheiro/sparql
```

Proveniência: cada facto é guardado como triplo normal **e** descrito por um nó `rdf:Statement`
(reificação RDF) com `prov:wasDerivedFrom <URL>`. Assim o SPARQL devolve o facto e a página que o
suporta, e é daí que vêm as citações.
