# MEALHEIRO: contexto do projeto

Chatbot de literacia financeira em **português europeu** para a cadeira Knowledge and Language 2026/27
(MEI, Universidade de Coimbra). Autores: João Figueiredo e Tiago Alves.
Responde a perguntas sobre juros, crédito, depósitos, seguros e direitos do consumidor com base num
**Knowledge Graph em RDF** construído a partir de fontes oficiais portuguesas. Cita as fontes e
**abstém-se** quando a confiança é baixa.

Documentos de referência em `docs/`: enunciado (`KL_Project_2026_2027.pdf`), `Literature_Review.pdf`,
`Project_Proposal.pdf`. O enunciado exige uma componente de NLP e uma de conhecimento/incerteza que
**interajam**. Aqui os sinais do KG alimentam a decisão de abstenção.

## Regra principal: simplicidade

- Tudo tem de ser fácil de explicar e defender na apresentação. Código curto e legível, em inglês, sem comentários.
- Não treinamos redes neuronais. Nada de SubgraphRAG nem conformal prediction.
- O bot tem **só duas saídas**: (1) responder com citação; (2) abster-se e indicar a fonte oficial.
- Preferir uma solução simples e explicável a uma mais "inteligente".

## Arquitetura

### Offline (corre uma vez)
1. **Scraping** (`scraping/`): requests + trafilatura. Fontes: Todos Contam, Portal do Cliente
   Bancário (BdP), CMVM e ASF. Respeitar o robots.txt e esperar 1–2 s entre pedidos.
   Saída: `data/raw/<fonte>.jsonl` com `url, title, text, source, topic, retrieved_at`.
   **Nunca contornar proteções anti-bot** (Cloudflare, desafios JS). Se um site bloquear,
   usa-se a importação de HTML guardado à mão no browser (`scraping/import_saved_html.py`).
2. **Ontologia** (`kg/`): Turtle, prefixo `fl:`.
   Classes: Product, Concept, Cost, Risk, Right, Regulator, Topic.
   Relações: hasCost, hasRisk, regulatedBy, definition, relatedTo, hasTopic.
   Temas em SKOS, a partir do Referencial de Educação Financeira. Cada facto leva `prov:wasDerivedFrom` com o URL de origem.
3. **Extração** de factos com um LLM: saída JSON validada por Pydantic e restrita à ontologia, depois convertida para RDF.
4. **Validação** com pySHACL e carregamento no Apache Jena Fuseki (Docker).
5. **Índice de texto** (`retrieval/`): pedaços de cerca de 300 palavras, embeddings BGE-M3, FAISS.
6. Prometido na proposta: ligar produtos à **FIBO** e à **Wikidata**, e taxas (Euribor) do **BPstat**.

### Online (a cada pergunta)
1. Filtro de âmbito: deteta pedidos de conselho pessoal e abstém-se.
2. Entity linking aos `rdfs:label` do KG, por texto e por embeddings.
3. SPARQL dos factos a 1 salto das entidades, mais 3 a 5 passagens de texto.
4. O LLM (Ollama: Qwen3-8B, EuroLLM-9B ou Amália) responde **só** com base nesses factos e passagens, e cita-os.
5. Sinais de confiança (`uncertainty/`): semantic entropy (5 amostras, agrupadas por NLI bidirecional,
   mDeBERTa-XNLI), `entities_found` e `facts_connect`.
6. Uma regressão logística (scikit-learn) dá P(resposta correta). Acima do limiar responde, abaixo abstém-se.
7. Interface em Streamlit (`app/`): chat, fontes e indicador de confiança.

## Avaliação (`eval/`)
- Cerca de 150 perguntas de teste em PT-PT, mais cerca de 50 de dev/val (para treinar a regressão e escolher o limiar).
- `eval/questions.jsonl` com `id, question, type, gold_answer, source_url, answerable, split`.
  `type` ∈ {conceptual, numeric, multihop, unanswerable, advice}; `split` ∈ {dev, val, test}.
- Sistemas a comparar: (a) só o LLM (`baselines/`); (b) RAG só com texto, réplica de Eleuterio et al. (SLATE 2025); (c) o nosso, KG + texto.
- Abstenção: instrução no prompt vs semantic entropy sozinha vs sinais combinados.
- Métricas: correção (LLM-judge, validado com Cohen's kappa), fidelidade e precisão das citações (RAGAS),
  AUROC, ECE, accuracy vs coverage, precisão dos factos do KG (amostra auditada).
- Ablações: sem SHACL; sem os sinais do KG.

## Datas
- **Checkpoint 1, 23/11/2026**: corpus, ontologia e KG v1, baselines (a) e (b), 75 perguntas de teste.
- **Checkpoint 2, 03/12/2026**: sistema completo com confiança, teste completo, primeiros resultados.
- **Relatório final, 12/12/2026** (máximo de 8 páginas, IJCAI). Apresentações a 14, 16 e 17/12.

## Ordem de trabalho
1. Scrapers (feito: ASF automático 17 pág.; BdP 33 pág. e Todos Contam 41 pág. por recolha assistida no browser, 21/11)
2. Baselines (b) e (a) (feito 21/11: retrieval/text_index.py, baselines/run.py; 75 perguntas de teste em eval/questions.jsonl)
3. Ontologia, extração, SHACL e Fuseki (feito 22/11: KG v1 com as 3 fontes; falta testar o Fuseki em Docker)
4. Recuperação no KG e geração com citações ← *a seguir*
5. Módulo de incerteza e calibração
6. Avaliação

## Convenções
- Python ≥ 3.9 (venv em `.venv/`). Cada pasta de topo é um pacote; corre-se com `python -m pasta.modulo`.
- Dados intermédios em `data/`. `data/html_cache/` e `data/manual_html/` não vão para o git.
- Código todo em inglês e **sem comentários** (`#`), incluindo os .ttl, o docker-compose e o requirements (decisão de 22/11).
  Cada script tem só uma docstring curta em inglês (1–2 linhas e o uso), que serve de texto do `--help`.
  As explicações para a apresentação ficam em `docs/GUIA.md` e `docs/MANUAL.md`, não no código.
- Ficam em português só os **dados**: prompts do LLM, frase de abstenção, descrições do esquema Pydantic
  (vão para o LLM), palavras-chave dos temas, marcadores anti-bot e labels/comentários RDF (`@pt`).

## Decisões tomadas
- Namespaces: `fl:` = `https://w3id.org/mealheiro/fl#` (ontologia), `kg:` = `https://w3id.org/mealheiro/kg/` (dados).
- Proveniência por **reificação RDF** (`rdf:Statement` + `prov:wasDerivedFrom`); o triplo também é afirmado diretamente.
- IRIs das entidades = slug do rdfs:label com cada palavra no singular (`entity_iri`), para fundir plurais; em conflito de tipo, fica o 1.º.
- Extração completa da ASF (15/11): 62/63 pedaços (1 timeout; `num_predict`=2048 evita ciclos), `data/kg/kg.ttl` com 912/926 factos após SHACL
  (277 entidades, 248 relatedTo, 25 hasCost, 18 regulatedBy, 2 hasRisk).
- Extração BdP + Todos Contam (22/11, ~8 h, ~180 s/pedaço): BdP 105/108, TC 58/58 (3 timeouts). KG v1 com as 3 fontes:
  891 entidades, 1806 ligações, 3462/3567 factos após SHACL (90 páginas). Erros para o relatório: TAEG como Concept
  (hasCost removido pelo SHACL), "depósito a prazo hasCost juros" (passa no SHACL: é semântico).
- Recolha assistida (21/11): o Chrome do utilizador (extensão Claude in Chrome) fez fetch das páginas com 1,5–2,5 s
  entre pedidos, sem resolver desafios anti-bot (nenhum apareceu); gravou um JSON {url: html} → `scraping.split_browser_bundle`
  → `scraping.import_saved_html`. Texto: trafilatura, ou o plano B `main_text` (html5lib + quebras por bloco) se der >20% mais texto.
- Embeddings BGE-M3 via Ollama (`bge-m3`), não sentence-transformers: evita instalar o PyTorch só para isto.
- As 47 perguntas com resposta foram redigidas por um LLM a partir do corpus, com `evidence` literal verificada; têm de ser revistas à mão.
- Validação em dois níveis: Pydantic (forma do JSON do LLM) → SHACL (grafo). Factos que falham o SHACL são removidos (`--no-shacl` para a ablação).
- Temas: Quadro II do Referencial de Educação Financeira 2013 (6 temas, 17 subtemas no topics.ttl).
- Os PDFs em todoscontam.pt/sites/default/files/ são acessíveis sem bloqueio (ao contrário das páginas HTML).
- Extração (09/11, página "Seguro de Saúde" da ASF, RTX 3050 4 GB):
  qwen3:8b ≈ 190 s/pedaço (61% no CPU) vs qwen3:4b ≈ 58 s/pedaço. O 4B gera labels no plural, duplicados e menos relações,
  por isso a extração do KG usa o **qwen3:8b** (corre uma vez, offline). Comparação em `data/kg/compare/`.
  O prompt v1 levou o 8B a extrair "plano de saúde regulatedBy ASF", quando o texto diz o contrário; a regra 4 do prompt v2 corrigiu isto.
  É um bom exemplo de alucinação para o relatório.
