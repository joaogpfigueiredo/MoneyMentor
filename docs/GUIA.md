# MEALHEIRO: guia completo (Checkpoint 1)

Este guia serve para três coisas: **perceber** como o projeto funciona, **correr** cada parte e
**mostrar** ao professor no checkpoint, sabendo responder às perguntas. Está escrito para ser lido de
uma ponta à outra uma vez e depois consultado.

---

## 1. O projeto em 1 minuto

O MEALHEIRO é um chatbot de literacia financeira em português europeu. Responde a perguntas sobre
juros, crédito, depósitos, seguros e direitos do consumidor **só com base em fontes oficiais
portuguesas** (Banco de Portugal, Todos Contam, ASF, CMVM), **cita a fonte** e **abstém-se** quando
não tem confiança suficiente ou quando lhe pedem um conselho pessoal.

A ideia central (o que o distingue de um RAG normal) é ter um **Knowledge Graph (KG)** em RDF com
factos extraídos dessas fontes. O KG serve para duas coisas:

1. dar ao LLM factos estruturados e com fonte para responder;
2. dar **sinais de confiança**: se a pergunta fala de entidades que existem no KG e se essas entidades
   estão ligadas entre si. Estes sinais, juntamente com a *semantic entropy*, entram numa regressão
   logística que decide se o bot responde ou se se abstém.

É aqui que as duas componentes que o enunciado exige **interagem**: o conhecimento (KG) alimenta a
decisão sobre a incerteza da componente de linguagem (LLM).

O bot só tem duas saídas: **(1) responder com citação** ou **(2) abster-se e indicar a fonte oficial**.

---

## 2. Mapa do sistema

```
OFFLINE (corre uma vez)
  páginas oficiais ──► scraping/ ──► data/raw/*.jsonl  (texto limpo + URL)
                                         │
                ┌────────────────────────┴───────────────────────┐
                ▼                                                ▼
   kg/extract.py (LLM → JSON)                        retrieval/text_index.py
   kg/build_kg.py (JSON → RDF)                       pedaços de ~300 palavras
   SHACL remove factos inválidos                     embeddings BGE-M3 + FAISS
                ▼                                                ▼
        data/kg/kg.ttl                                    data/index/

ONLINE (a cada pergunta)                       [Checkpoint 2]
  pergunta ─► filtro de conselho pessoal ─► entidades do KG ─► SPARQL (factos a 1 salto)
                                         └► 5 passagens de texto
           ─► LLM responde só com isso, com citações
           ─► sinais de confiança ─► regressão logística ─► responde | abstém-se
```

### O que está feito para o Checkpoint 1

O que a proposta promete para o Checkpoint 1: *"the collected texts, the first version of the ontology
and of the KG, the two baselines (a) and (b) working, and the first 75 test questions"*.

| Entregável | Estado | Onde |
|---|---|---|
| Corpus | ✅ 91 páginas, ~72 mil palavras (ASF 17, BdP 33, Todos Contam 41) | `data/raw/` |
| Ontologia v1 | ✅ 7 classes, 6 relações, temas SKOS, regras SHACL | `kg/*.ttl` |
| KG v1 | ✅ 891 entidades, 3462 factos com fonte, das 3 fontes (ASF, BdP, Todos Contam) | `data/kg/kg.ttl` |
| Baseline (a), só o LLM | ✅ | `baselines/llm_only.py` |
| Baseline (b), RAG com texto | ✅ | `baselines/text_rag.py` |
| 75 perguntas de teste | ✅ (falta revisão humana) | `eval/questions.jsonl` |

---

## 3. Preparar o computador (antes da demonstração)

```bash
.venv\Scripts\activate                 # ativa o ambiente Python (Windows)
ollama list                            # confirma que existem qwen3:8b e bge-m3
```

Se faltar algum modelo: `ollama pull qwen3:8b` e `ollama pull bge-m3`. O Ollama tem de estar aberto
(ícone na barra de tarefas). Tudo corre **localmente**: não há chamadas a APIs pagas.

Para ver texto com acentos no terminal do Windows convém fazer antes `set PYTHONIOENCODING=utf-8`.

---

## 4. Cada parte, explicada

### 4.1 Recolha do corpus (`scraping/`)

**O que faz:** descarrega as páginas oficiais, tira o texto principal (sem menus nem rodapés) e grava
uma linha JSON por página em `data/raw/<fonte>.jsonl`, com `url, title, text, source, topic, retrieved_at`.

**Como:**
- **ASF**: crawler automático (`python -m scraping.crawl --source asf`). Respeita o `robots.txt`, espera
  1–2 s entre pedidos, identifica-se como `MealheiroBot` e guarda o HTML em cache.
- **Banco de Portugal e Todos Contam**: estes sites têm proteção anti-bot (devolvem 403 a programas).
  **Não contornámos a proteção.** As páginas foram recolhidas num browser normal (Chrome), ao ritmo
  de uma página a cada 1,5–2,5 s, gravadas num ficheiro e depois importadas
  (`scraping/split_browser_bundle.py` → `scraping/import_saved_html.py`). É o equivalente a guardar
  as páginas à mão com Ctrl+S.
- **Extração do texto**: `trafilatura` (biblioteca que deteta o conteúdo principal). Quando falha
  (o HTML do BdP tem o texto fora do `<main>`; o Todos Contam tem texto solto dentro de `<div>`), usa-se
  um plano B simples (`main_text` em `scraping/common.py`): lê o HTML como um browser (html5lib),
  remove menus/rodapé e parte o texto em linhas a cada bloco.

**Mostrar:** `python -m scraping.stats` (páginas e palavras por fonte e tema) e abrir uma linha de
`data/raw/bportugal.jsonl`.

### 4.2 A ontologia (`kg/ontology.ttl`, `kg/topics.ttl`)

A ontologia é o **"esquema" do KG**: diz que tipos de coisas existem e que ligações são permitidas.
Prefixo `fl:` = `https://w3id.org/mealheiro/fl#`.

**Classes (tipos de nós):**

| Classe | O que é | Exemplos no KG |
|---|---|---|
| `fl:Product` | algo que o consumidor contrata | seguro de habitação, depósito a prazo, crédito habitação |
| `fl:Concept` | ideia financeira que não é produto | inflação, spread, capital seguro, franquia temporal |
| `fl:Cost` | dinheiro que o consumidor paga | prémio de seguro, franquia, comissão de transferência |
| `fl:Risk` | algo que pode correr mal ao consumidor | risco de incêndio, risco financeiro |
| `fl:Right` | direito legal do consumidor | direito de livre resolução, reclamação, direito ao esquecimento |
| `fl:Regulator` | supervisor | só 3 nós fixos: Banco de Portugal, CMVM, ASF |
| `fl:Topic` | tema do Referencial de Educação Financeira | "Seguros", "Custos do crédito" (é um `skos:Concept`) |

Todas (exceto Topic) são subclasses de `fl:Entity` e são **disjuntas** (`owl:AllDisjointClasses`):
uma coisa não pode ser ao mesmo tempo Product e Cost.

**Relações (tipos de ligações):**

| Relação | De → Para | Significado | Exemplo |
|---|---|---|---|
| `fl:hasCost` | Product → Cost | o produto tem este custo | seguro de habitação → prémio de seguro |
| `fl:hasRisk` | Product → Risk | o produto tem este risco | fundos de pensões → risco financeiro |
| `fl:regulatedBy` | Product → Regulator | é supervisionado por | fundos de pensões fechados → ASF |
| `fl:relatedTo` | Entity ↔ Entity | o texto liga as duas (simétrica) | apólice de seguro ↔ contrato de seguro |
| `fl:hasTopic` | Entity → Topic | tema do Referencial | seguro de habitação → Seguros |
| `fl:definition` | Entity → texto | definição tirada da fonte (atributo, não ligação) | "Seguro que cobre…" |

Os **temas** (`kg/topics.ttl`) vêm do Quadro II do *Referencial de Educação Financeira* (2013):
6 temas e 17 subtemas, em SKOS (`skos:broader` liga subtema → tema). Usar SKOS é o padrão W3C
para taxonomias/tesauros.

### 4.3 Nós e ligações do KG (a pergunta mais provável!)

**Nós** (as "bolinhas" do grafo):
- **891 entidades** extraídas: 552 Concept, 147 Product, 81 Cost, 70 Right, 41 Risk.
- **3 supervisores** fixos (BdP, CMVM, ASF), definidos na ontologia.
- **23 temas** SKOS (6 temas + 17 subtemas).
- Nós técnicos `rdf:Statement` (3462), um por facto, só para guardar a fonte (ver abaixo).
  Não são "conhecimento", são metadados.

**Ligações** (as "setas"): 1806 no total:
`hasTopic` 846, `relatedTo` 801, `hasCost` 85, `regulatedBy` 48, `hasRisk` 26.

Entidades mais ligadas: fundos de pensões (39), depósito a prazo (28), crédito à habitação (28),
cartão de crédito (26), abertura de conta (25).

**Atributos** (texto preso a um nó, não são setas): 891 nomes (`rdfs:label`), 1393 definições
(`fl:definition`), sinónimos (`skos:altLabel`).

**Exemplo concreto**: o nó `kg:seguro-de-habitacao`:

```turtle
kg:seguro-de-habitacao  a fl:Product ;
    rdfs:label    "seguro de habitação"@pt ;
    skos:altLabel "seguro habitação"@pt ;
    fl:hasCost    kg:premio-de-seguro , kg:franquia-de-seguro ;
    fl:hasRisk    kg:risco-de-incendio ;
    fl:hasTopic   fl:t-seguros ;
    fl:relatedTo  kg:capital-seguro , kg:direito-a-devolucao-do-premio ;
    prov:wasDerivedFrom <https://www.consumidor.asf.com.pt/seguros/seguro-de-habitação> .
```

**Proveniência (de onde vem cada facto):** cada facto, por exemplo `seguro de habitação hasCost prémio de seguro`,
é guardado **duas vezes**: como triplo normal (para consultar facilmente) e descrito por um nó
`rdf:Statement` (**reificação RDF**) que diz qual é a página de origem:

```turtle
kg:fact/3f2a…  a rdf:Statement ;
    rdf:subject   kg:seguro-de-habitacao ;
    rdf:predicate fl:hasCost ;
    rdf:object    kg:premio-de-seguro ;
    prov:wasDerivedFrom <https://www.consumidor.asf.com.pt/…> .
```

É daqui que vêm as **citações** do chatbot. `prov:` é o vocabulário W3C PROV-O.

**Como se decide que dois nomes são o mesmo nó (resolução de entidades)?** O IRI é o nome em
minúsculas, sem acentos e com cada palavra no singular: "Fundos de Pensões" e "fundo de pensões"
dão ambos `kg:fundo-de-pensao`. É simples e explicável. A limitação: sinónimos diferentes
("PPR" e "plano poupança reforma") só se juntam se o LLM os der como `aliases`.

**Mostrar:**
```bash
python -m kg.stats                                   # todos os números acima
python -m kg.visualize "seguro multirriscos habitação"   # abre o desenho do grafo no browser
python -m kg.visualize "fundos de pensões"           # o nó mais ligado (39 ligações)
python -m kg.sparql "seguro de habitação"            # factos a 1 salto, cada um com a fonte
```

### 4.4 Extração de factos com o LLM (`kg/extract.py`, `kg/schema.py`)

**O que faz:** para cada página, divide o texto em pedaços de ~400 palavras e pede ao LLM
(`qwen3:8b`, local, no Ollama) que devolva JSON com entidades e relações.

**Porque é fiável o suficiente:**
1. **O prompt descreve a ontologia** (tipos, relações, temas) e tem 8 regras, por exemplo: "extrai só o que
   está escrito", "usa regulatedBy só se o texto o disser".
2. **Um exemplo anotado à mão** (few-shot) mostra o formato.
3. **Structured outputs**: passamos ao Ollama o JSON Schema gerado pelo Pydantic (`kg/schema.py`).
   O modelo **não consegue** gerar um tipo fora da ontologia, porque as classes e relações são `Literal`.
4. **Temperatura 0**: dá sempre o mesmo resultado (reprodutível).
5. Se o JSON for inválido, tenta outra vez e mostra o erro ao modelo.

**Escolha do modelo:** comparámos qwen3:4b e qwen3:8b na mesma página (`data/kg/compare/`).
O 4B é 3× mais rápido (58 s vs 190 s por pedaço numa GPU de 4 GB), mas gera nomes no plural,
duplicados e menos relações. Como a extração corre uma vez e offline, ficou o 8B.

**Exemplo de alucinação (bom para o relatório):** com o prompt v1, o 8B extraiu
`plano de saúde regulatedBy ASF`, mas o texto da ASF diz exatamente o contrário: o plano de saúde
**não** é supervisionado pela ASF. A regra 4 do prompt v2 corrigiu isto. É por isto que validamos
e vamos auditar uma amostra dos factos.

### 4.5 Validação em dois níveis: Pydantic e SHACL (`kg/shapes.ttl`, `kg/build_kg.py`)

1. **Pydantic** verifica a *forma* do JSON do LLM (campos, tipos permitidos). Erro → pede-se de novo.
   Também deita fora relações cujas pontas não existem e entidades que são supervisores.
2. **SHACL** (W3C) verifica *regras sobre o grafo já construído*:
   - cada entidade tem exatamente um `rdfs:label` em português;
   - definição com ≥ 20 caracteres;
   - o tema existe nos temas SKOS;
   - `hasCost` aponta para um `Cost`, `hasRisk` para um `Risk`;
   - o supervisor é BdP, CMVM ou ASF;
   - **só um Product** pode ter `hasCost`/`hasRisk`/`regulatedBy`;
   - **cada facto tem `prov:wasDerivedFrom` com um URL**.

Os factos que falham são **removidos** e ficam listados em `data/kg/kg_shacl_report.txt`.
No KG v1: 3567 factos → **105 removidos** (88 violações) → 3462. Erros reais apanhados:
`crédito habitação hasRisk justa causa`, `seguro de acidentes de trabalho hasCost prestações em
dinheiro` (é um benefício, não um custo), `indemnização hasCost …` (não é um produto),
`contrato de crédito hasCost TAEG` (a TAEG ficou como Concept: é um indicador, não um custo).

**Porquê os dois níveis?** O Pydantic só vê um pedaço de cada vez. O SHACL vê o grafo todo, por
exemplo uma entidade que um pedaço diz ser Concept e outro usa como Product.
A ablação `--no-shacl` mede o efeito disto na avaliação.

**Mostrar (demonstração do SHACL com erros de propósito):**
```bash
python -m kg.build_kg --input kg/examples/erros_de_proposito.jsonl --output data/kg/erros.ttl
```
O Pydantic rejeita o tipo inventado "Bank", uma relação sem ponta é descartada e o SHACL apanha 3
violações (Concept com hasCost, hasRisk a apontar para um Cost, definição curta demais).

**Construir o KG:** `python -m kg.build_kg` (lê `data/kg/extractions/*.jsonl` e escreve `data/kg/kg.ttl`).

### 4.6 SPARQL e Fuseki (`kg/sparql.py`, `kg/load_fuseki.py`)

`python -m kg.sparql "entidade"` encontra a entidade pelo nome e corre a consulta SPARQL "factos a 1
salto": todos os `rdf:Statement` em que a entidade é sujeito ou objeto, com a fonte. É exatamente o
que o chatbot vai pedir ao KG no Checkpoint 2.

Por omissão corre em memória com o `rdflib` (não precisa de nada instalado). Com Docker, o mesmo
KG pode ser servido pelo **Apache Jena Fuseki**, um servidor SPARQL com interface web:
```bash
docker compose up -d                       # http://localhost:3030 (admin / mealheiro)
python -m kg.load_fuseki --kg data/kg/kg.ttl
python -m kg.sparql "seguro de habitação" --endpoint http://localhost:3030/mealheiro/sparql
```
(O Fuseki ainda não foi testado nesta máquina porque o Docker Desktop não estava a arrancar. Para a
demonstração usa-se o rdflib.)

### 4.7 Índice de texto (`retrieval/text_index.py`)

Divide cada página em pedaços de ~300 palavras (parágrafos inteiros) e transforma cada pedaço num
vetor de 1024 números com o **BGE-M3** (modelo de embeddings multilingue, a correr no Ollama).
Pedaços com significado parecido ficam com vetores próximos. O **FAISS** encontra os 5 vetores mais
próximos do vetor da pergunta (semelhança do cosseno). Total: **292 pedaços**.

```bash
python -m retrieval.text_index build
python -m retrieval.text_index search "Quanto imposto pago sobre os juros de um depósito?"
```

### 4.8 Baselines (`baselines/`)

Os três sistemas a comparar usam **o mesmo LLM** (`qwen3:8b`, temperatura 0) e o mesmo pedido de
resposta curta. A única diferença é o contexto que o LLM recebe:

| Sistema | Contexto | Ficheiro |
|---|---|---|
| (a) só LLM | nenhum, só o que o modelo "sabe" | `baselines/llm_only.py` |
| (b) RAG com texto | 5 passagens recuperadas, citadas com [n] (réplica de Eleuterio et al., SLATE 2025) | `baselines/text_rag.py` |
| (c) o nosso | factos do KG + passagens + sinais de confiança | Checkpoint 2 |

Nos baselines, a abstenção é **só por instrução no prompt**: o modelo deve responder exatamente
"Não posso responder com segurança." se não souber ou se for um pedido de conselho. Esta é uma das
três condições de abstenção a comparar (prompt vs semantic entropy vs sinais combinados).

```bash
python -m baselines.run --system a        # -> eval/results/a_llm_only.jsonl
python -m baselines.run --system b        # -> eval/results/b_text_rag.jsonl
```
Cada linha do resultado tem a pergunta, a resposta, se se absteve, as passagens usadas e o tempo.
No fim, o script mostra a taxa de abstenção nas perguntas com e sem resposta e, no (b), o
**recall@5** (em quantas perguntas a página certa estava nas 5 passagens).

### 4.9 Perguntas de teste (`eval/questions.jsonl`)

75 perguntas em PT-PT, todas no split `test`:

| Tipo | N.º | Exemplo |
|---|---|---|
| conceptual | 25 | "O que quer dizer a TANB de um depósito ser uma taxa bruta?" |
| numeric | 12 | "Quanto rendem 2500 € num depósito a 180 dias com TANB de 4,3%, antes de impostos?" |
| multihop | 10 | "Quem supervisiona os depósitos a prazo e quem supervisiona os fundos de investimento?" |
| unanswerable | 14 | "Qual é o valor da Euribor a 6 meses esta semana?" (não está nas fontes) |
| advice | 14 | "Devo pôr 10 000 € num depósito a prazo ou em fundos?" (conselho pessoal) |

Campos: `id, question, type, gold_answer, source_url, answerable, split` e ainda `evidence`, uma
citação **literal** da página que justifica a resposta. Um script confirmou que todas as citações
existem nas páginas. As perguntas com resposta foram redigidas com ajuda de um LLM a partir do
corpus e **têm de ser revistas por nós antes do checkpoint** (ler cada `gold_answer` contra a `evidence`). As sem resposta e as de conselho foram escritas à mão, e confirmámos
que as primeiras não têm resposta no corpus. As restantes ~125 de teste e ~50 de dev/val (para treinar
a regressão logística e escolher o limiar) ficam para o Checkpoint 2.

---

## 5. Guião da demonstração (≈ 10 minutos)

Ter o terminal aberto na pasta do projeto, com o venv ativo e o Ollama a correr.

1. **Problema e ideia** (1 min): §1 deste guia. Frase-chave: *"os sinais do KG decidem quando o
   chatbot não deve responder"*.
2. **Corpus** (1 min): `python -m scraping.stats`. Explicar a recolha no browser sem contornar o anti-bot.
3. **Ontologia** (2 min): abrir `kg/ontology.ttl` e mostrar as tabelas do §4.2. Mencionar SKOS
   (temas do Referencial) e PROV-O (fontes).
4. **KG** (3 min):
   - `python -m kg.stats` → nós e ligações;
   - `python -m kg.visualize "seguro multirriscos habitação"` → desenho no browser;
   - `python -m kg.sparql "seguro de habitação"` → factos com fonte;
   - mostrar o exemplo de alucinação (§4.4) e o relatório do SHACL (`data/kg/kg_shacl_report.txt`).
5. **Baselines** (2 min): `python -m retrieval.text_index search "O que é a TAEG?"` e depois abrir
   `eval/results/b_text_rag.jsonl` numa pergunta boa e numa má (ver §7). Mostrar o resumo do §7.
6. **Perguntas** (1 min): abrir `eval/questions.jsonl` e mostrar um exemplo de cada tipo.
7. **Próximos passos** (30 s): §9.

Dica: **não correr ao vivo** comandos que chamam o LLM (extração, baselines). Demoram 30 s a 3 min
por pedido. Mostrar os resultados já gravados. Os comandos `stats`, `visualize`, `sparql` e
`search` são rápidos (o `search` demora uns segundos a carregar o BGE-M3).

---

## 6. Perguntas prováveis do professor (e respostas)

**Porque um KG e não só RAG?** O texto sozinho não diz se a pergunta está "dentro" do que sabemos.
O KG dá sinais explícitos: as entidades da pergunta existem (`entities_found`)? Estão ligadas
(`facts_connect`)? Isso ajuda a decidir quando **não** responder. Também dá factos com fonte
explícita e verificável (SHACL).

**Quais são os nós e as ligações?** Ver §4.3: 891 entidades em 5 classes, mais 3 supervisores e
23 temas. 1806 ligações em 5 relações. Os `rdf:Statement` são só para a proveniência.

**Porque estas classes?** Cobrem o que um consumidor precisa de saber sobre um produto financeiro:
o que é (Product/Concept), quanto custa (Cost), o que pode correr mal (Risk), que direitos tem
(Right) e quem o protege (Regulator). Foram pensadas para serem poucas e fáceis de extrair por um LLM.

**Porque há tantos `relatedTo` e tão poucos `hasRisk`?** As páginas da ASF descrevem sobretudo
coberturas e direitos, falam pouco de riscos. O `relatedTo` é a relação "genérica" que o LLM usa
quando o texto liga duas coisas sem dizer como. É uma limitação conhecida, e o BdP e o Todos Contam
(que têm secções "Principais riscos") devem equilibrar isto.

**Como garantem que os factos estão certos?** Em três camadas: (1) structured outputs + Pydantic só
deixam passar tipos da ontologia; (2) SHACL remove factos que violam as regras; (3) vamos auditar à
mão uma amostra aleatória (métrica "precisão dos factos do KG"). Temos um exemplo real de
alucinação apanhada (plano de saúde).

**Porque reificação e não named graphs / RDF-star?** É RDF 1.1 padrão, funciona em qualquer
ferramenta (rdflib, Fuseki, SHACL) e é fácil de explicar. RDF-star seria mais compacto, mas o suporte
ainda é desigual.

**O que é o SHACL e porque não OWL reasoning?** O OWL serve para *inferir* (mundo aberto: se falta
algo, não é erro). O SHACL serve para *validar* (mundo fechado: se falta a fonte, é erro). Queremos
rejeitar factos maus, por isso usamos SHACL.

**Porque um LLM local e não o GPT?** Reprodutibilidade, custo zero, privacidade, e o enunciado/proposta
assenta em modelos abertos (Qwen3-8B, EuroLLM, Amália). Temperatura 0 torna os resultados repetíveis.

**Como contornaram o bloqueio do BdP/Todos Contam?** Não contornámos. O robots.txt permite essas
páginas, mas a proteção anti-bot recusa programas. Recolhemos as páginas num browser normal, devagar,
e importámos o HTML. É o mesmo que as guardar à mão.

**Como vão avaliar?** Correção com um LLM-judge validado com Cohen's kappa contra anotação nossa;
fidelidade e precisão das citações (RAGAS); qualidade da confiança com AUROC e ECE; curva
accuracy vs coverage (quanto melhora a exatidão quando o bot pode recusar). Ablações: sem SHACL e
sem os sinais do KG.

**O que é a semantic entropy?** Pede-se ao LLM 5 respostas à mesma pergunta (com temperatura > 0),
agrupam-se as que dizem o mesmo (um modelo NLI verifica se A implica B *e* B implica A) e
calcula-se a entropia dos grupos. Se as 5 respostas dizem coisas diferentes, o modelo está incerto.

**Porque uma regressão logística?** Junta poucos sinais (entropia, entities_found, facts_connect)
numa probabilidade de a resposta estar certa. É simples, interpretável (os coeficientes dizem quanto
pesa cada sinal) e treina-se com as ~50 perguntas de dev/val. Não treinamos redes neuronais.

---

## 7. Resultados dos baselines (Checkpoint 1)

Corridos a 21/11 sobre as 75 perguntas de teste, com `qwen3:8b` e temperatura 0. Os números vêm do
resumo de `baselines/run.py` e de `eval/results/*.jsonl`. **A correção ainda não foi medida** (falta
o LLM-judge); o que já se pode medir é a abstenção e a recuperação.

| | (a) só LLM | (b) RAG com texto |
|---|---|---|
| Absteve-se nas 47 que **têm** resposta (devia ser baixo) | 13% (6) | **0%** |
| Absteve-se nas 14 **sem resposta** no corpus | 36% (5) | **86%** (12) |
| Absteve-se nos 14 **pedidos de conselho** | 100% | 93% (13) |
| Página certa nas 5 passagens (recall@5) | n.a. | **98%** (46/47) |
| Tempo médio por pergunta | 14,5 s | 21,8 s |

**Leitura:** sem documentos, o LLM **inventa** respostas para perguntas que não pode saber. Com as
passagens, quase sempre se abstém quando a informação não está lá, e responde sempre quando está.
O filtro de conselho pessoal funciona bem nos dois. Com 98% de recall@5, a recuperação de texto não
é o ponto fraco: o problema que fica para o sistema (c) é *decidir bem quando responder*.

**Exemplos para mostrar** (pergunta → (a) → (b)):
- q043 *Quem supervisiona os depósitos a prazo e os fundos de investimento?* (a) "ambos pela CMVM" ✗;
  (b) "depósitos pelo Banco de Portugal [1], fundos pela CMVM [3]" ✓.
- q027 *Juros de 2500 € a 180 dias com TANB de 4,3%?* (a) faz a conta e erra (51,75 €) ✗; (b) 53,75 € [1] ✓.
- q033 *Imposto do selo num crédito à habitação a 30 anos?* (a) "0,8%" ✗; (b) "0,6% [1]" ✓.
- q021 *Um plano de saúde é o mesmo que um seguro de saúde?* (a) "Sim" ✗; (b) "Não…" ✓.
- q048 *Euribor a 6 meses esta semana?* (a) inventa "2,65%" ✗; (b) abstém-se ✓.
- q052 *Limite do IRS Jovem?* (a) inventa um valor ✗; (b) abstém-se ✓.

**Erros do (b), bons para motivar o sistema (c):**
- q050 *Comissão de manutenção da CGD?* Responde misturando uma passagem sobre serviços mínimos
  bancários com o nome do banco: parece fundamentado, mas não está. Os sinais do KG (a entidade "CGD"
  não existe no grafo) devem ajudar aqui.
- q074 *Quanto devo poupar para me reformar aos 60?* Dá um conselho vago em vez de se abster.
- q054 *Inflação no mês passado?* Diz que "não está disponível nas passagens", ou seja, abstém-se,
  mas sem a frase fixa, e o detetor (que procura a frase exata) não conta isto como abstenção. É uma
  limitação da deteção por texto e uma das razões para a decisão final vir de uma regressão
  logística e não do próprio LLM.

---

## 8. Números para saber de cor

- Corpus: **91 páginas, ~72 mil palavras** (ASF 17, BdP 33, Todos Contam 41).
- Ontologia: **7 classes, 5 relações entre nós + 1 atributo (definition)**, 23 temas SKOS, 4 shapes SHACL.
- KG v1: **891 entidades, 1806 ligações, 3462 factos com fonte (de 90 páginas), 105 removidos pelo SHACL** (de 3567).
- Extração: qwen3:8b, ~180 s por pedaço de 400 palavras numa RTX 3050 de 4 GB; **225 de 229 pedaços**
  (ASF 62/63, BdP 105/108, Todos Contam 58/58; 4 timeouts). BdP + Todos Contam: ~8 h numa noite.
- Índice: **292 pedaços**, vetores BGE-M3 de dimensão 1024, FAISS.
- Teste: **75 perguntas** (25/12/10/14/14).

---

## 9. Limitações e próximos passos (dizer com honestidade)

- **4 pedaços não foram extraídos** (timeout: BdP "Avaliação da solvabilidade", "Como contratar",
  "Garantia de depósitos"; ASF "Contrato de Seguro"). O texto continua no índice, só faltam os factos.
- **Erros semânticos que passam no SHACL**: p. ex. `depósito a prazo hasCost juros` (os juros são um
  rendimento). O SHACL verifica tipos, não o significado; é por isso que auditamos uma amostra.
- **Muitas definições por entidade** (uma por fonte/pedaço; crédito à habitação tem 8): é bom para
  citar, mas há repetição.
- Falta a CMVM no corpus (os fundos de investimento vêm do Todos Contam).
- Muitos `relatedTo` genéricos (801); poucos `hasRisk` (26).
- Resolução de entidades por nome normalizado: não junta sinónimos não declarados.
- Ainda por fazer (Checkpoint 2): entity linking, recuperação no KG, geração com citações do KG,
  semantic entropy, regressão logística, interface Streamlit, resto das perguntas, LLM-judge e
  métricas, ligações à FIBO/Wikidata e Euribor do BPstat (prometidas na proposta).

---

## 10. Glossário rápido

- **RDF**: modelo de dados da Web Semântica; tudo são **triplos** *sujeito – predicado – objeto*.
- **IRI**: identificador global de um nó (um URL), por exemplo `https://w3id.org/mealheiro/kg/seguro-de-habitacao`.
- **Turtle (.ttl)**: formato de texto para escrever RDF.
- **Ontologia (OWL)**: define classes, relações e restrições (o esquema do KG).
- **SKOS**: vocabulário W3C para taxonomias (temas, `broader`/`narrower`).
- **PROV-O**: vocabulário W3C para proveniência (`prov:wasDerivedFrom` = "derivado de").
- **Reificação**: descrever um triplo com um nó `rdf:Statement` para lhe juntar metadados (a fonte).
- **SHACL**: linguagem W3C para validar grafos RDF contra regras ("shapes").
- **SPARQL**: linguagem de consulta para RDF (o "SQL dos grafos").
- **Fuseki**: servidor SPARQL do Apache Jena.
- **Embedding**: vetor de números que representa o significado de um texto.
- **FAISS**: biblioteca para encontrar rapidamente os vetores mais próximos.
- **RAG**: *Retrieval-Augmented Generation*: recuperar documentos e dá-los ao LLM para responder.
- **Structured outputs**: obrigar o LLM a gerar JSON que segue um esquema.
- **Few-shot**: dar ao LLM um ou mais exemplos resolvidos no prompt.
- **Semantic entropy**: medida de incerteza baseada em quão diferentes são várias respostas do LLM.
- **NLI**: *Natural Language Inference*: decidir se uma frase implica outra (modelo mDeBERTa-XNLI).
- **AUROC / ECE**: qualidade da confiança (separa certas de erradas? a probabilidade bate certo com a realidade?).
- **TANB / TAEG / TAN**: taxa anual nominal bruta (depósitos) / taxa anual de encargos efetiva global
  (custo total do crédito) / taxa anual nominal (crédito).
