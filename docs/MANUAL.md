# MEALHEIRO: manual de estudo (teoria e prática)

Este manual explica **tudo** o que o projeto usa: a teoria de cada conceito, como essa teoria está
aplicada no nosso código e o que cada ficheiro faz. O [GUIA.md](GUIA.md) diz *como correr e como
apresentar*; este manual diz *porque é que as coisas funcionam*.

Cada capítulo tem três partes:
- **Teoria**: o conceito, independentemente do projeto (o que se pode perguntar num exame);
- **No MEALHEIRO**: como e onde o usamos, com excertos do código;
- **Perguntas para testar**: se souberes responder, percebeste o capítulo.

Os capítulos seguem a ordem da linha de montagem do sistema. Os capítulos 11 e 12 (incerteza e
avaliação) descrevem o que é feito no Checkpoint 2, mas a teoria convém saber já, porque é o
coração da proposta.

---

## Índice

0. [O problema e a ideia](#0-o-problema-e-a-ideia)
1. [Recolha de texto da Web](#1-recolha-de-texto-da-web)
2. [Knowledge Graphs e RDF](#2-knowledge-graphs-e-rdf)
3. [Ontologias: RDFS, OWL e SKOS](#3-ontologias-rdfs-owl-e-skos)
4. [Proveniência: PROV-O e reificação](#4-proveniência-prov-o-e-reificação)
5. [Modelos de linguagem (LLMs)](#5-modelos-de-linguagem-llms)
6. [Extração de informação com LLMs](#6-extração-de-informação-com-llms)
7. [Resolução de entidades](#7-resolução-de-entidades)
8. [Validação com SHACL](#8-validação-com-shacl)
9. [SPARQL e triplestores](#9-sparql-e-triplestores)
10. [Recuperação de informação: embeddings e FAISS](#10-recuperação-de-informação-embeddings-e-faiss)
11. [RAG: geração aumentada por recuperação](#11-rag-geração-aumentada-por-recuperação)
12. [Incerteza e abstenção](#12-incerteza-e-abstenção)
13. [Avaliação](#13-avaliação)
14. [Engenharia: como o código está organizado](#14-engenharia-como-o-código-está-organizado)
15. [Mapa ficheiro a ficheiro](#15-mapa-ficheiro-a-ficheiro)

---

## 0. O problema e a ideia

### O problema
Só **13%** dos adultos portugueses atingem o nível essencial de literacia financeira, e só 25%
acertam ao mesmo tempo nas perguntas de juro simples e composto (Banco de Portugal, inquérito de
2026). Um chatbot podia ajudar, mas um LLM sozinho tem três problemas:

1. **Inventa factos** (*alucinações*). Vimos isto no baseline (a): disse que os depósitos a prazo
   são supervisionados pela CMVM, e inventou o valor da Euribor "desta semana".
2. **Não conhece as regras portuguesas**, ou mistura-as com as de outros países.
3. **Responde a tudo**, mesmo ao que não devia: perguntas fora das fontes ou pedidos de conselho
   pessoal ("devo investir em ações?"), que um serviço público não deve dar.

### A ideia
- **Fundamentar** (*grounding*) as respostas em fontes oficiais portuguesas e **citá-las**.
- Guardar o conhecimento dessas fontes num **Knowledge Graph** com a origem de cada facto.
- Usar o KG não só para responder, mas também para **decidir quando não responder**: se a
  pergunta fala de coisas que não estão no grafo, ou que o grafo não liga, há razões para duvidar.

### Ligação ao enunciado
O enunciado exige uma componente de **linguagem/NLP** e uma componente de **conhecimento ou
incerteza** que **interajam de forma substantiva** (não basta usar duas ferramentas lado a lado).
No MEALHEIRO:
- **NLP**: extração de informação com LLM, recuperação de texto com embeddings, geração de respostas, NLI.
- **Conhecimento**: RDF, OWL, SKOS, SHACL, SPARQL, proveniência.
- **Incerteza**: semantic entropy, regressão logística, calibração.
- **A interação**: os sinais do KG (`entities_found`, `facts_connect`) entram no modelo de
  incerteza, que decide se a resposta do LLM é mostrada. E o próprio KG é construído pelo LLM e
  corrigido pelas regras simbólicas (SHACL). As componentes alimentam-se umas às outras.

### Ligação à literatura (a nossa revisão)
| Trabalho | O que faz | O que aproveitamos | O que fazemos diferente |
|---|---|---|---|
| Eleuterio et al. (SLATE 2025) | chatbot PT de literacia financeira, RAG sobre 222 artigos do Todos Contam, 48 perguntas, sem baseline | o domínio, a ideia de RAG → é o nosso **baseline (b)** | KG, abstenção medida, baselines, conjunto de teste maior |
| Burgin et al., QuARK (RANLP 2025) | LLM extrai triplos *sem esquema* para um KG financeiro; o KG melhora a exatidão | extração com LLM | **com** ontologia, triplos **validados** (SHACL), para consumidores |
| Li et al., SubgraphRAG (ICLR 2025) | recupera subgrafos de um KG grande para dar a um LLM | a ideia de dar factos do grafo ao LLM | não temos um KG grande pré-existente; usamos 1 salto, sem treino |
| Farquhar et al. (Nature 2024) | *semantic entropy* para detetar confabulações | o sinal de incerteza principal | juntamos a entropia com sinais do KG |

A **lacuna** (*gap*) identificada: nenhum destes trabalhos junta um KG com ontologia, recuperação
que usa o grafo e uma decisão calibrada de responder ou abster-se, em português europeu.
As perguntas de investigação: **RQ1** (KG + texto dá respostas mais corretas e fiéis do que só
texto e do que só LLM?) e **RQ2** (a abstenção fica mais bem calibrada juntando sinais do KG à
semantic entropy?).

---

## 1. Recolha de texto da Web

### Teoria

**HTTP.** Um browser (ou um programa) pede uma página com `GET <url>`; o servidor responde com
um **código de estado** e o conteúdo. Códigos importantes: `200` OK; `301/302` redireção;
`403` proibido; `404` não existe; `429` demasiados pedidos; `503` serviço indisponível.

**HTML e DOM.** Uma página é HTML: uma árvore de elementos (`<html>`, `<body>`, `<div>`, `<p>`,
`<a href>`…). O browser constrói a árvore (o **DOM**) a partir do texto HTML com um **parser**.
O HTML real está muitas vezes mal formado (tags não fechadas). A norma HTML5 define um
**algoritmo de parsing com recuperação de erros** que todos os browsers seguem; parsers antigos
(como o do libxml2, usado pelo `lxml`) recuperam de outra maneira e podem construir uma árvore
diferente.

**Crawling.** Um *crawler* começa em URLs iniciais, descarrega cada página, extrai os links e
põe-nos numa fila (pesquisa em largura, **BFS**). Para não visitar o site inteiro, filtra-se por
prefixo do URL e por padrões a ignorar.

**Boas maneiras (*politeness*).**
- **robots.txt** (*Robots Exclusion Protocol*, RFC 9309): ficheiro na raiz do site que diz que
  caminhos os robôs podem visitar e, às vezes, quanto tempo esperar (`Crawl-delay`). Não é uma
  proteção técnica: é um pedido que um programa bem comportado respeita.
- **Esperar entre pedidos** para não sobrecarregar o servidor.
- **Identificar-se** com um `User-Agent` honesto.
- **Cache**: guardar o que já se descarregou para não repetir pedidos.

**Proteção anti-bot.** Alguns sites (com Cloudflare ou semelhantes) devolvem um desafio em
JavaScript ou um `403` a qualquer cliente que não pareça um browser. Contornar isto (fingir ser um
browser, resolver desafios) é eticamente e legalmente problemático. A alternativa legítima é uma
pessoa abrir as páginas num browser normal.

**Remoção de *boilerplate*.** Uma página tem muito texto que não interessa: menus, rodapés,
cookies, "partilhar no Facebook". Ferramentas como o **trafilatura** usam heurísticas para encontrar
o conteúdo principal: densidade de texto (blocos com muito texto e poucos links são conteúdo;
blocos com muitos links são navegação), tags semânticas (`<article>`, `<main>`), comprimento das
frases, e um algoritmo de recurso (*fallback*) quando estas falham.

### No MEALHEIRO

**Formato de saída** (`data/raw/<fonte>.jsonl`, uma linha JSON por página):
```json
{"url": "...", "title": "Taxas de juro", "text": "...", "source": "bportugal",
 "topic": "juros", "retrieved_at": "2026-11-21T16:45:00+00:00"}
```
JSONL ("JSON Lines") é prático: cada linha é independente, pode-se acrescentar sem reescrever o
ficheiro e ler linha a linha.

**ASF: crawler automático** (`scraping/crawl.py`, `scraping/common.py`, `scraping/sources.py`):
- `PoliteSession` em `common.py`: antes do primeiro pedido a um site lê o `robots.txt` com o
  `urllib.robotparser`; se o `robots.txt` der 401/403, assume "tudo proibido"; respeita o
  `Crawl-delay` e espera sempre um tempo aleatório entre 1 e 2 s. User-Agent:
  `MealheiroBot/0.1 (projeto academico Knowledge and Language, Universidade de Coimbra)`.
- Deteta desafios anti-bot: se a resposta for 403/429/503 **e** tiver marcas de desafio
  (Cloudflare, "Just a moment"…), lança `BlockedError` e o crawler **pára** e explica como fazer a
  importação manual. Nunca tenta contornar.
- `cache_path()` guarda cada HTML em `data/html_cache/<sha1 do URL>.html`.
- `sources.py` define, para cada fonte, os URLs iniciais, os prefixos permitidos e o que ignorar
  (PDFs, páginas em inglês, pesquisa, política de privacidade, etc.).

**BdP e Todos Contam: recolha assistida no browser.** Os dois sites devolvem 403 a programas,
embora o `robots.txt` permita as páginas. O que fizemos:
1. abrir os sites no Chrome do utilizador (não apareceu nenhuma verificação);
2. recusar os cookies não essenciais;
3. a partir da página, pedir as páginas de conteúdo uma a uma, com 1,5–2,5 s de intervalo;
4. gravar tudo num único ficheiro JSON `{url: html}`;
5. `scraping/split_browser_bundle.py` escreve um `.html` por página, com o comentário
   `<!-- saved from url=... -->` que o Ctrl+S do browser também põe;
6. `scraping/import_saved_html.py` descobre o URL original (`<link rel="canonical">`, `og:url` ou
   esse comentário), extrai o texto e escreve o JSONL.

**Extração do texto** (`extract_page` em `common.py`):
1. Primeiro o `trafilatura` (com `favor_precision=True`, para preferir deixar de fora a incluir lixo).
2. Depois o plano B `main_text`, e fica o que der **mais 20% de texto**. O plano B existe por
   causa de dois problemas reais:
   - **BdP**: o HTML tem tags mal fechadas. O `lxml` reconstruía a árvore de forma diferente do
     browser e o texto ficava "dentro" do menu. Solução: ler com o **html5lib**, que implementa o
     algoritmo de parsing do HTML5 (o mesmo dos browsers). Além disso, o texto do BdP está **fora**
     do `<main>`, por isso, se o `<main>` tiver pouco texto, usa-se o `<body>` sem `nav`, `header`,
     `footer` e elementos com classes "menu", "navigation", "footer", "breadcrumb", "cookie".
   - **Todos Contam**: partes importantes (por exemplo as secções de riscos) são texto solto dentro
     de `<div>` e entre `<br>`, sem `<p>`. O plano B mete uma quebra de linha à volta de cada bloco
     (`div`, `p`, `br`, títulos, listas, tabelas) e depois junta o texto todo; assim nada se perde.
     Na página "Depósitos a prazo", passou de 113 para 649 palavras.
3. Remove linhas de navegação conhecidas (`BOILERPLATE_LINES`) e o sufixo do site no título.
4. Páginas com menos de 80 palavras (`MIN_WORDS`) são descartadas (são índices ou menus).

**Tema da página** (`guess_topic`): palavras-chave no URL e no título (crédito, depósitos,
seguros…). É só uma etiqueta grosseira para estatísticas; os temas "a sério" vêm do KG (SKOS).

**Resultado:** 91 páginas, ~72 mil palavras (ASF 17 / 21 140, BdP 33 / 35 903,
Todos Contam 41 / 14 780). `python -m scraping.stats` mostra isto.

### Perguntas para testar
- O `robots.txt` impede tecnicamente um programa de aceder? (Não; é uma convenção.)
- Porque é que o `lxml` e o browser podiam ver árvores diferentes para o mesmo HTML?
- Porque é que não usámos um browser automático "disfarçado" para o BdP?
- O que faz o `favor_precision` e qual é o compromisso (precisão vs cobertura)?

---

## 2. Knowledge Graphs e RDF

### Teoria

**Knowledge Graph (KG).** Uma forma de representar conhecimento como um **grafo**: **nós**
(entidades, conceitos) ligados por **arestas com nome** (relações). Exemplos conhecidos: Wikidata,
DBpedia, Google Knowledge Graph. A vantagem face a texto: o conhecimento fica **explícito,
estruturado e consultável** (pode-se perguntar "todos os custos do produto X"), e cada facto pode
ter metadados (fonte, data, confiança).

**RDF** (*Resource Description Framework*, W3C) é o modelo de dados normalizado para KGs na Web.
Tudo é um **triplo**:

```
sujeito  ──predicado──►  objeto
seguro de habitação ──hasCost──► prémio de seguro
```

- **Sujeito**: um recurso (um nó), identificado por um **IRI** (um URL que serve de nome global,
  por exemplo `https://w3id.org/mealheiro/kg/seguro-de-habitacao`) ou um nó anónimo (*blank node*).
- **Predicado**: sempre um IRI (a relação; por exemplo `https://w3id.org/mealheiro/fl#hasCost`).
- **Objeto**: um recurso (IRI) **ou** um **literal** (um valor: texto, número, data). Literais de
  texto podem ter **etiqueta de língua**: `"seguro de habitação"@pt`. Outros têm **tipo de dados**:
  `"20"^^xsd:integer`.

Um **grafo RDF** é um conjunto de triplos. Como é um *conjunto*, o mesmo triplo duas vezes conta
uma vez (útil: juntar extrações repetidas não duplica nada).

**Porquê IRIs?** São nomes **globais e únicos**: dois grafos diferentes podem falar do mesmo
recurso usando o mesmo IRI, e assim juntam-se automaticamente. É a base dos *Linked Data*.

**Prefixos.** Para não escrever IRIs enormes, usam-se abreviaturas: com
`@prefix fl: <https://w3id.org/mealheiro/fl#>`, `fl:hasCost` é o IRI completo. Prefixos
habituais: `rdf:`, `rdfs:`, `owl:`, `xsd:`, `skos:`, `prov:`, `sh:`.

**Serializações.** O mesmo grafo pode ser escrito em vários formatos: **Turtle** (`.ttl`, o mais
legível, o que usamos), N-Triples (um triplo por linha), RDF/XML, JSON-LD. Em Turtle:
```turtle
kg:seguro-de-habitacao a fl:Product ;                 # "a" = rdf:type
    rdfs:label "seguro de habitação"@pt ;              # ";" = mesmo sujeito, outro predicado
    fl:hasCost kg:premio-de-seguro , kg:franquia-de-seguro .   # "," = mesmo predicado, outro objeto
```

**Nós, ligações e atributos (a pergunta do professor).** No vocabulário dos grafos:
- **Nós** = sujeitos e objetos que são recursos (IRIs).
- **Ligações/arestas** = triplos cujo objeto é outro recurso (por exemplo `hasCost`).
- **Atributos/propriedades de dados** = triplos cujo objeto é um literal (por exemplo `rdfs:label`, `fl:definition`).
- Há dois **níveis**: o **esquema** (que tipos de nós e de ligações existem, ou seja, a ontologia, capítulo 3) e os
  **dados** (os nós e ligações concretos, ou instâncias).

**Linked Data** (Tim Berners-Lee): usar IRIs HTTP como nomes, devolver informação útil quando
alguém visita o IRI e ligar a outros datasets (por exemplo, `owl:sameAs` para a Wikidata).

### No MEALHEIRO

- **Dois namespaces**: `fl:` = `https://w3id.org/mealheiro/fl#` (o **esquema**: classes,
  relações, supervisores, temas) e `kg:` = `https://w3id.org/mealheiro/kg/` (os **dados**: as
  entidades extraídas). Separar esquema e dados é boa prática. O `w3id.org` é um serviço de IRIs
  permanentes usado por projetos de investigação (o domínio não depende de nós).
- **Biblioteca**: `rdflib` (Python) para criar, ler, escrever e consultar grafos.
- **O KG**: `data/kg/kg.ttl`. Estado atual (KG v1, as 3 fontes, 22/11):

| | Quantidade |
|---|---|
| Triplos no ficheiro | 23651 |
| **Nós (entidades)** | 891: Concept 552, Product 147, Cost 81, Right 70, Risk 41 |
| Nós fixos do esquema | 3 supervisores + 23 temas SKOS |
| **Ligações** | 1806: hasTopic 846, relatedTo 801, hasCost 85, regulatedBy 48, hasRisk 26 |
| **Atributos** | 891 `rdfs:label`, 1393 `fl:definition`, 68 `skos:altLabel` |
| Factos com fonte (`rdf:Statement`) | 3462 (de 90 páginas) |

- `python -m kg.stats` calcula estes números; `python -m kg.visualize "<entidade>"` desenha a
  vizinhança de um nó.

### Perguntas para testar
- Qual é a diferença entre um IRI e um literal? Um predicado pode ser um literal?
- Porque é que juntar o mesmo triplo duas vezes não cria duplicados?
- Num triplo `kg:x fl:definition "…"@pt`, isto é uma ligação ou um atributo?
- Para que servem os prefixos e porque temos dois namespaces?

---

## 3. Ontologias: RDFS, OWL e SKOS

### Teoria

**Ontologia** = especificação explícita de uma conceptualização (Gruber): que **tipos** de coisas
existem num domínio, que **relações** há entre elas e que **restrições** se aplicam. É o esquema do
KG, mas com **semântica formal** (permite inferências).

**RDFS** (RDF Schema) dá o vocabulário básico:
- `rdfs:Class`, `rdf:type` (instância de), `rdfs:subClassOf` (subclasse; transitiva);
- `rdf:Property`, `rdfs:subPropertyOf`;
- `rdfs:domain` e `rdfs:range`: o tipo do sujeito e do objeto de uma propriedade;
- `rdfs:label`, `rdfs:comment`: nome e descrição para humanos.

**Atenção a um ponto subtil (muito perguntado):** em RDFS/OWL, `domain` e `range` **não são
restrições**, são **regras de inferência**. Se `fl:hasCost` tem `rdfs:range fl:Cost` e o grafo
diz `X fl:hasCost Y`, um raciocinador **conclui** que `Y` é um `fl:Cost`; não dá erro se `Y` não
for declarado Cost. Para **verificar** usa-se SHACL (capítulo 8).

**OWL** (Web Ontology Language) acrescenta expressividade, com base em **lógicas de descrição**:
- `owl:Class`, `owl:ObjectProperty` (liga dois recursos), `owl:DatatypeProperty` (liga um recurso a um literal);
- características de propriedades: `owl:SymmetricProperty` (se A→B então B→A),
  `owl:TransitiveProperty`, `owl:FunctionalProperty`, `owl:inverseOf`;
- **disjunção**: `owl:disjointWith`, `owl:AllDisjointClasses` (nada pode pertencer a duas delas);
- restrições (`owl:someValuesFrom`, cardinalidades), equivalências (`owl:equivalentClass`, `owl:sameAs`).

**Dois pressupostos do OWL que convém saber:**
- **Mundo aberto** (*Open World Assumption*): o que não está escrito **não é falso**, é
  desconhecido. Se um produto não tem fonte no grafo, o OWL não se queixa; assume que a fonte
  existe algures.
- **Sem nomes únicos** (*no Unique Name Assumption*): dois IRIs diferentes podem referir a mesma coisa.

Por isso o OWL é ótimo para **inferir** e fraco para **validar dados**. Daí o SHACL.

**SKOS** (Simple Knowledge Organization System, W3C) é para **taxonomias, tesauros e sistemas de
classificação**, ou seja, hierarquias de temas que não são "classes" no sentido lógico:
- `skos:ConceptScheme` (o esquema), `skos:Concept` (um tema);
- `skos:prefLabel` (nome preferido), `skos:altLabel` (sinónimo);
- `skos:broader` / `skos:narrower` (mais geral / mais específico). Não são `subClassOf`:
  "Seguros" ser mais específico do que "Sistema financeiro" não quer dizer que um seguro *é um*
  sistema financeiro;
- `skos:hasTopConcept` / `skos:topConceptOf`, `skos:inScheme`.

**Como se desenha uma ontologia (metodologia).** Começar por **perguntas de competência**
(*competency questions*): que perguntas o KG tem de saber responder? Daí saem as classes e as
relações. Preferir poucas classes bem definidas, reutilizar vocabulários existentes (SKOS, PROV,
FIBO…) e documentar cada termo.

### No MEALHEIRO

**Perguntas de competência** (o que um consumidor quer saber de um produto financeiro):
o que é? quanto custa? o que pode correr mal? que direitos tenho? quem supervisiona? de que tema é?
Cada uma corresponde a uma parte da ontologia:

| Pergunta | Parte da ontologia |
|---|---|
| O que é? | classes `Product`/`Concept` + atributo `fl:definition` |
| Quanto custa? | `fl:hasCost` → `fl:Cost` |
| O que pode correr mal? | `fl:hasRisk` → `fl:Risk` |
| Que direitos tenho? | classe `fl:Right` (+ `relatedTo`) |
| Quem supervisiona? | `fl:regulatedBy` → `fl:Regulator` |
| De que tema é? | `fl:hasTopic` → `fl:Topic` (SKOS) |

**`kg/ontology.ttl`** (o essencial):
```turtle
fl:Entity    a owl:Class .                                   # superclasse de tudo
fl:Product   a owl:Class ; rdfs:subClassOf fl:Entity .
fl:Concept   a owl:Class ; rdfs:subClassOf fl:Entity .
fl:Cost      a owl:Class ; rdfs:subClassOf fl:Entity .
fl:Risk      a owl:Class ; rdfs:subClassOf fl:Entity .
fl:Right     a owl:Class ; rdfs:subClassOf fl:Entity .
fl:Regulator a owl:Class ; rdfs:subClassOf fl:Entity .
fl:Topic     a owl:Class ; rdfs:subClassOf skos:Concept .    # os temas são conceitos SKOS
[] a owl:AllDisjointClasses ; owl:members ( fl:Product fl:Concept fl:Cost fl:Risk fl:Right fl:Regulator ) .

fl:hasCost     a owl:ObjectProperty ; rdfs:domain fl:Product ; rdfs:range fl:Cost .
fl:hasRisk     a owl:ObjectProperty ; rdfs:domain fl:Product ; rdfs:range fl:Risk .
fl:regulatedBy a owl:ObjectProperty ; rdfs:domain fl:Product ; rdfs:range fl:Regulator .
fl:relatedTo   a owl:ObjectProperty, owl:SymmetricProperty ; rdfs:domain fl:Entity ; rdfs:range fl:Entity .
fl:hasTopic    a owl:ObjectProperty ; rdfs:domain fl:Entity ; rdfs:range fl:Topic .
fl:definition  a owl:DatatypeProperty ; rdfs:domain fl:Entity ; rdfs:range rdf:langString .

fl:BancoDePortugal a fl:Regulator .  fl:CMVM a fl:Regulator .  fl:ASF a fl:Regulator .
```
(no ficheiro real cada termo tem também `rdfs:label` e `rdfs:comment` em português.)

Decisões a saber justificar:
- **Porquê só 5 classes de entidade?** Cobrem as perguntas de competência e são fáceis de extrair
  por um LLM de 8B. Mais classes = mais confusão na extração.
- **Porquê disjuntas?** Uma coisa não pode ser ao mesmo tempo produto e custo. Isto deteta erros
  de extração (o mesmo nome classificado com dois tipos). Em `build_kg.py`, quando há conflito de
  tipo, fica o primeiro e regista-se um aviso.
- **Porquê os supervisores são indivíduos fixos e não extraídos?** São só três e sabemos quais
  são. Deixar o LLM criá-los dava variantes ("ASF", "Autoridade de Supervisão…", "Banco Portugal").
- **Porquê `relatedTo` simétrica?** "A está relacionado com B" implica "B está relacionado com A".
- **Porquê `fl:definition` em vez de `skos:definition`?** Para poder exigir língua e comprimento
  mínimo com SHACL e reificar cada definição com a sua fonte; podia ser declarada
  `rdfs:subPropertyOf skos:definition` (melhoria possível).

**`kg/topics.ttl`**: os temas do Quadro II do *Referencial de Educação Financeira* (2013), como
esquema SKOS `fl:ReferencialEF`: 6 temas de topo (`fl:t-orcamento`, `t-sistema`, `t-poupanca`,
`t-credito`, `t-etica`, `t-direitos`) e 17 subtemas ligados por `skos:broader`
(por exemplo `fl:t-seguros skos:broader fl:t-sistema`). Usar um referencial oficial dá uma
classificação reconhecida e não inventada por nós.

**Prometido na proposta, ainda por fazer:** ligar produtos à **FIBO** (*Financial Industry
Business Ontology*, ontologia de referência do setor financeiro) e à **Wikidata** (por exemplo com
`skos:exactMatch` ou `owl:sameAs`), e taxas (Euribor) do **BPstat**. São *Linked Data*.

### Perguntas para testar
- Se `fl:hasCost` tem `range fl:Cost` e escrevo `kg:x fl:hasCost kg:y` sem dizer que `y` é Cost,
  o que conclui um raciocinador OWL? E o que faz o SHACL?
- Porque é que os temas são SKOS e não uma hierarquia de `rdfs:subClassOf`?
- O que é o pressuposto do mundo aberto e porque é um problema para validar dados?
- Que pergunta de competência justifica a classe `Risk`?

---

## 4. Proveniência: PROV-O e reificação

### Teoria

**Proveniência** = de onde veio um dado, quem o produziu e como. Num sistema que cita fontes é
essencial: sem proveniência não há citações.

**PROV-O** (W3C) é a ontologia normalizada para proveniência. Tem três classes centrais:
`prov:Entity` (uma coisa: um documento, um dado), `prov:Activity` (um processo: uma extração) e
`prov:Agent` (quem é responsável: uma pessoa, um programa). Relações como
`prov:wasDerivedFrom` (derivado de), `prov:wasGeneratedBy`, `prov:wasAttributedTo`.

**O problema: como dizer algo *sobre* um triplo?** Um triplo não tem identificador próprio, por
isso não se pode escrever "o triplo *X hasCost Y* vem da página P" diretamente. Há várias soluções:

| Técnica | Como | Prós | Contras |
|---|---|---|---|
| **Reificação RDF** | um nó `rdf:Statement` com `rdf:subject`, `rdf:predicate`, `rdf:object` | RDF 1.1 padrão, funciona em todas as ferramentas | 4 triplos extra por facto; verboso |
| **Named graphs** | cada fonte num grafo separado (quads) | compacto, natural em SPARQL (`GRAPH`) | o grafo inteiro partilha metadados; mais difícil validar com SHACL |
| **RDF-star / RDF 1.2** | `<< X hasCost Y >> prov:wasDerivedFrom P` | elegante | suporte ainda desigual nas ferramentas |
| **Propriedade singular** | um predicado único por facto | sem extensões | ilegível |

Nota: a reificação **não afirma** o triplo; só o descreve. Por isso, para poder consultar o facto
normalmente, é preciso escrever **também** o triplo direto.

### No MEALHEIRO

Escolhemos **reificação RDF + o triplo direto**, por ser padrão, compatível com rdflib, pySHACL e
Fuseki, e fácil de explicar. Em `kg/build_kg.py`:

```python
def add_fact(g, s, p, o, source):
    g.add((s, p, o))                                   # 1. o facto em si (para consultar)
    h = hashlib.sha1(f"{s}|{p}|{o}|{source}".encode()).hexdigest()[:16]
    st = KG[f"fact/{h}"]                               # 2. um nó com IRI determinístico
    g.add((st, RDF.type, RDF.Statement))
    g.add((st, RDF.subject, s)); g.add((st, RDF.predicate, p)); g.add((st, RDF.object, o))
    g.add((st, PROV.wasDerivedFrom, source))           # 3. a fonte
```
- O IRI do `Statement` é um **hash** de (sujeito, predicado, objeto, fonte). Correr o build duas
  vezes dá os mesmos IRIs (determinístico) e não duplica nada.
- **O mesmo facto vindo de duas páginas** dá dois `Statement`s (hashes diferentes): o facto fica
  com duas fontes, o que é informação útil (mais suporte).
- Também cada **entidade** tem `prov:wasDerivedFrom` para as páginas onde aparece.
- O SHACL exige que cada `Statement` tenha uma fonte que é um URL (`StatementShape`, capítulo 8).
- A consulta SPARQL do capítulo 9 percorre os `Statement`s: é daí que vêm as citações do chatbot.

Usamos só `prov:wasDerivedFrom`; não modelamos a atividade de extração (modelo, data, prompt) em
PROV. Seria uma melhoria natural (`prov:wasGeneratedBy` uma `prov:Activity` com o modelo usado).

### Perguntas para testar
- Porque é que, com reificação, também temos de escrever o triplo direto?
- Porque é que o IRI do `Statement` é um hash e não um número sequencial?
- Que vantagem teria o RDF-star? Porque não o usámos?

---

## 5. Modelos de linguagem (LLMs)

### Teoria

**O que é um LLM.** Uma rede neuronal (arquitetura **Transformer**) treinada para prever o
**próximo token** de um texto. Um **token** é um pedaço de palavra (em português, ~1,3–1,6 tokens
por palavra). Para gerar texto, o modelo calcula uma distribuição de probabilidade sobre o
vocabulário, escolhe um token, junta-o ao texto e repete (**geração autorregressiva**).

**Componentes do Transformer** (o essencial): *embeddings* dos tokens; camadas de **auto-atenção**
(cada token "olha" para os anteriores e decide quais são relevantes); camadas *feed-forward*;
à saída, *logits* (pontuações) para cada token do vocabulário, transformados em probabilidades pela
função **softmax**.

**Treino em fases.** (1) *Pré-treino* em muitíssimo texto (aprende língua e factos);
(2) *instruction tuning* / *fine-tuning* supervisionado (aprende a seguir instruções);
(3) alinhamento com preferências humanas (RLHF ou semelhante). Não treinamos nada: usamos um
modelo já treinado.

**Janela de contexto.** O número máximo de tokens que o modelo vê de uma vez (prompt + resposta).
Na prática, mais contexto custa mais memória: o **KV cache** (as chaves e valores da atenção de cada
token) cresce linearmente com o contexto. Modelos também usam pior a informação no **meio** de
contextos longos (*lost in the middle*).

**Descodificação (como se escolhe o token).**
- **Temperatura** *T*: divide os logits antes do softmax. *T* → 0 equivale a escolher sempre o token
  mais provável (**greedy**, determinístico); *T* alta dá distribuições mais planas (mais variedade).
- **Amostragem** top-k / top-p (*nucleus*): só se amostra entre os tokens mais prováveis.
- Para a **extração** e as **respostas** queremos reprodutibilidade: **T = 0**. Para a
  **semantic entropy** queremos várias respostas diferentes: **T > 0**.

**Prompts.** O *system prompt* dá o papel e as regras; as mensagens *user*/*assistant* formam a
conversa. **Few-shot** (aprendizagem em contexto): pôr no prompt exemplos resolvidos; o modelo
imita o formato e o nível de detalhe sem ser treinado.

**Alucinação.** O modelo gera texto fluente e plausível mas falso. *Intrínseca*: contradiz a fonte
que recebeu; *extrínseca*: acrescenta coisas que não estão na fonte. Causa de fundo: o modelo
otimiza plausibilidade, não verdade. *Confabulação* (Farquhar et al.) é o subtipo de respostas
arbitrárias que mudam de amostra para amostra; é isso que a semantic entropy deteta.

**Quantização.** Os pesos de um modelo de 8 mil milhões de parâmetros em 16 bits ocupam ~16 GB. Os
modelos do Ollama vêm **quantizados** (tipicamente ~4 bits por peso, formato GGUF), ficando com
~5 GB, com perda de qualidade pequena.

**Execução local.** O **Ollama** corre modelos no próprio PC (usa o motor llama.cpp) e expõe uma API
HTTP local (`http://localhost:11434`). Se o modelo não cabe na memória da GPU, parte das camadas
corre no CPU (*offload*), o que o torna muito mais lento.

### No MEALHEIRO

- **Modelo**: `qwen3:8b` (Qwen3, 8 mil milhões de parâmetros, Alibaba, pesos abertos, multilingue),
  ficheiro de 5,2 GB. Também testámos `qwen3:4b` (2,5 GB).
- **Hardware**: RTX 3050 Laptop com **4 GB** de VRAM. O 8B não cabe: ~61% corre no CPU. Daí os
  ~190–500 s por pedaço na extração e ~15–22 s por resposta curta.
- **`think: False`**: o Qwen3 tem um modo de "raciocínio" (gera um texto de pensamento escondido antes da
  resposta). Desligámo-lo: com a GPU que temos ficava muito mais lento e, com saída JSON
  restringida, não ajuda.
- **`num_ctx`**: 4096 tokens (prompt da extração ~1500 + resposta). Menos contexto = menos memória
  na GPU. **`num_predict`**: 2048 na extração. Corta respostas em ciclo: um pedaço da ASF ficou
  mais de 10 minutos a gerar até darmos este limite.
- **`temperature: 0`** em tudo o que já está feito (extração e baselines).
- Toda a comunicação com o LLM passa por `generation/llm.py` (`chat()`), para que os três sistemas
  usem exatamente as mesmas opções.

### Perguntas para testar
- O que faz a temperatura e porque usamos 0 na extração mas não na semantic entropy?
- Porque é que o modelo de 8B é tão mais lento do que o de 4B na nossa máquina?
- O que é few-shot e porque não é "treino"?
- Que diferença há entre alucinação intrínseca e extrínseca? Dá um exemplo do projeto.

---

## 6. Extração de informação com LLMs

### Teoria

**Extração de informação (IE)**: transformar texto livre em dados estruturados. Subtarefas
clássicas: **reconhecimento de entidades** (NER), **classificação de entidades**, **extração de
relações** (RE). Tradicionalmente faziam-se com modelos treinados em dados anotados (CRF, BERT…).
Com LLMs, faz-se com um prompt (*zero/few-shot*), sem dados de treino.

**Extração sem esquema vs com esquema.** Sem esquema (como no QuARK), o LLM inventa as relações
("tem_comissão", "cobra", "implica_custo"…), o que dá um grafo grande mas inconsistente e difícil de
consultar. Com esquema (o nosso caso), o LLM só pode usar os tipos e relações da ontologia: o grafo
é mais pequeno mas consistente e validável.

**Saídas estruturadas** (*structured outputs*, *constrained decoding*). Em vez de pedir JSON e esperar
que o modelo cumpra, **restringe-se a geração**: o JSON Schema é convertido numa gramática, e em
cada passo os tokens que violariam a gramática recebem probabilidade zero (os seus logits são
mascarados). O modelo **não consegue** gerar um tipo que não esteja no esquema. Isto garante a
**forma**, não a **verdade** (o conteúdo ainda pode estar errado).

**Validação de esquema.** O **Pydantic** (Python) define modelos de dados com tipos; valida JSON
contra eles e gera o JSON Schema correspondente. O tipo `Literal["Product", "Concept", …]` só
aceita aqueles valores.

**Divisão em pedaços (*chunking*).** Textos longos são partidos: cabe na janela de contexto, o
modelo presta mais atenção a cada parte e um erro afeta só um pedaço. Custo: relações entre
pedaços diferentes perdem-se, e a mesma entidade aparece em vários pedaços (resolve-se na fusão,
capítulo 7).

### No MEALHEIRO

**Ficheiros**: `kg/schema.py` (o esquema Pydantic) e `kg/extract.py` (o ciclo de extração).

**O esquema** (`kg/schema.py`) é a ontologia vista pelo LLM:
```python
EntityType   = Literal["Product", "Concept", "Cost", "Risk", "Right"]
RelationType = Literal["hasCost", "hasRisk", "regulatedBy", "relatedTo"]
TopicCode    = Literal["seguros", "custos-credito", ...]        # os 17 subtemas

class Entity(BaseModel):
    label: str                    # nome canónico, minúsculas, singular
    type: EntityType
    definition: Optional[str]     # tirada do texto
    aliases: List[str]            # sinónimos/siglas
    topics: List[TopicCode]

class Relation(BaseModel):
    subject: str; relation: RelationType; object: str

class Extraction(BaseModel):
    entities: List[Entity]; relations: List[Relation]
```
Note-se: o LLM não produz `hasTopic` nem `definition` como relações; produz os campos `topics` e
`definition` de cada entidade, e o `build_kg.py` converte-os em triplos.

**O ciclo** (`kg/extract.py`), para cada página de `data/raw/<fonte>.jsonl`:
1. `chunk_text()`: junta **parágrafos inteiros** até ~400 palavras (não corta frases).
2. `build_messages()`: monta a conversa:
   - *system*: o `SYSTEM_PROMPT` com a definição de cada tipo (e o que **não** é: "prazos,
     reembolsos, períodos e obrigações NÃO são custos"), as relações, os códigos de tema e 8 regras;
   - *user*/*assistant*: **um exemplo resolvido à mão** (texto sobre seguro multirriscos → JSON);
   - *user*: o título da página e o pedaço.
3. `call_llm()`: pede ao Ollama com `format = Extraction.model_json_schema()` (**saída
   restringida**), `temperature 0`, `think False`, `num_ctx 4096`, `num_predict 2048`.
4. `extract_chunk()`: valida com Pydantic; se falhar, **tenta mais uma vez mostrando o erro ao
   modelo**; se falhar de novo ou exceder o tempo, salta o pedaço.
5. Grava `{"url", "chunk", "model", "extraction"}` em `data/kg/extractions/<fonte>.jsonl`.
   **Retoma** onde parou: ao arrancar, lê o que já está feito e salta esses pedaços.

**As 8 regras do prompt** (e porquê):
1. Só o que está escrito, sem conhecimento próprio → contra alucinação extrínseca.
2. Nome em minúsculas, singular → facilita a fusão de entidades.
3. Definição tirada do texto → fidelidade.
4. As pontas das relações têm de ser entidades listadas; `regulatedBy` só se o texto o disser →
   **corrigiu uma alucinação real** (ver abaixo).
5. Não criar entidades para os supervisores nem para empresas → os supervisores são fixos.
6. Temas de crédito só para crédito; no máximo 2 temas → evita temas espalhados ao acaso.
7. Ignorar menus, cookies, notícias.
8. Se não houver nada útil, devolver listas vazias → em vez de inventar.

**Limpeza antes de construir** (`Extraction.drop_dangling()` em `schema.py`):
- remove entidades que são supervisores ("ASF", "Banco de Portugal"…), um erro frequente;
- remove relações cujas pontas não são entidades da mesma extração (exceto o supervisor em
  `regulatedBy`). Não se rejeita a extração inteira por causa de uma relação má.

**A experiência que justificou o modelo** (página "Seguro de Saúde" da ASF, 3 pedaços):

| Modelo / prompt | s/pedaço | Factos | Removidos pelo SHACL | Observações |
|---|---|---|---|---|
| qwen3:8b, prompt v1 | ~260 | 74 | 3 | **alucinou** `plano de saúde regulatedBy ASF` |
| qwen3:4b, prompt v2 | ~58 | 36 | 1 | nomes no plural, duplicados, menos relações, temas errados |
| qwen3:8b, prompt v2 | ~190 | 48 | 3 | o melhor |

A alucinação: o texto diz que o plano de saúde **não** é um seguro e **não** é supervisionado pela
ASF; o modelo extraiu o contrário (uma alucinação **intrínseca**, que contradiz a fonte). A regra 4
corrigiu-a. É um exemplo para o relatório e a razão para auditarmos uma amostra de factos.

**Números.** 225 de 229 pedaços extraídos: ASF 62/63, BdP 105/108, Todos Contam 58/58
(4 timeouts). Média de ~180 s por pedaço; o BdP e o Todos Contam levaram ~8 h numa noite. Os pedaços
do BdP são mais densos (até ~500 s e 20+ entidades). No total, 3567 factos antes do SHACL e 3462
depois. Um erro semântico que passa no SHACL: `depósito a prazo hasCost juros` (os juros são um
rendimento). O SHACL só vê os tipos, não o significado.

### Perguntas para testar
- O que garante a saída restringida e o que **não** garante?
- Porque é que o prompt diz o que **não** é um custo?
- Porque é que partimos o texto em pedaços? Que informação se perde?
- Porque é que a retentativa mostra o erro ao modelo?
- Porque é que escolhemos o 8B se o 4B é três vezes mais rápido?

---

## 7. Resolução de entidades

### Teoria

**Resolução de entidades** (*entity resolution*, *deduplication*): decidir quando duas menções
referem a mesma coisa do mundo ("fundos de pensões" na página A e "fundo de pensões" na página B).
Abordagens, da mais simples à mais sofisticada:
1. igualdade exata de texto;
2. **normalização** (minúsculas, sem acentos, lematização/singular) e depois igualdade;
3. semelhança de texto (distância de edição, Jaccard de n-gramas);
4. semelhança de **embeddings** + agrupamento (*clustering*);
5. modelos treinados ou LLMs a decidir pares.

O compromisso: juntar demais funde coisas diferentes ("seguro de vida" ≠ "seguro de vida
associado ao crédito"); juntar de menos deixa duplicados.

**Entity linking** é parecido mas noutro momento: ligar menções num texto (por exemplo, na pergunta
do utilizador) a nós de um KG existente.

### No MEALHEIRO

Abordagem 2 (normalização), em `kg/build_kg.py`:
```python
def slug(text):          # 'Crédito à Habitação' -> 'credito-a-habitacao'
def singular(word):      # 'pensoes' -> 'pensao', 'anuais' -> 'anual', 'seguros' -> 'seguro'
def entity_iri(label):   # KG['-'.join(singular(w) for w in slug(label).split('-'))]
```
- "Fundos de Pensões Fechados" e "fundo de pensões fechado" → `kg:fundo-de-pensao-fechado`.
- O primeiro nome visto fica como `rdfs:label`; as outras variantes ficam como `skos:altLabel`.
- A regra de singular é grosseira de propósito (ões→ão, ães→ão, ais→al, eis→el, res→r, tirar o
  "s" final em palavras com mais de 3 letras). Serve só para **comparar**, nunca é mostrada.
- **Conflito de tipo**: se a mesma entidade vem como Product num pedaço e Concept noutro, fica o
  primeiro tipo e regista-se um aviso (a disjunção da ontologia não permite os dois).
- A mesma normalização é usada em `kg/sparql.py` para encontrar uma entidade pelo nome, e em
  `kg/visualize.py`.

**Limitações:** sinónimos diferentes ("PPR" e "plano poupança reforma") só se juntam se o LLM os
listar em `aliases`; plurais irregulares podem falhar. No Checkpoint 2, o **entity linking** da
pergunta vai usar texto (esta normalização) **e** embeddings (para "seguro da casa" → "seguro de
habitação").

### Perguntas para testar
- Que erro é pior para nós: juntar demais ou juntar de menos? Porquê?
- Porque é que a regra de singular pode ser grosseira sem problema?
- Qual é a diferença entre resolução de entidades e entity linking?

---

## 8. Validação com SHACL

### Teoria

**SHACL** (*Shapes Constraint Language*, W3C) valida grafos RDF contra **formas** (*shapes*).
Ao contrário do OWL, assume **mundo fechado** para a validação: se uma regra exige uma fonte e ela
não está no grafo, é uma **violação**.

Conceitos:
- **Shape**: `sh:NodeShape` (regras sobre um nó) contendo `sh:property` (regras sobre os valores
  de um caminho/predicado, `sh:path`).
- **Alvo** (*target*): que nós a shape verifica. `sh:targetClass C` (todas as instâncias de C);
  `sh:targetSubjectsOf p` (todos os sujeitos de triplos com predicado p); `sh:targetNode`;
  `sh:targetObjectsOf`.
- **Restrições** (*constraints*) comuns:
  - cardinalidade: `sh:minCount`, `sh:maxCount`;
  - tipo de valor: `sh:datatype`, `sh:class` (o valor tem de ser instância de C), `sh:nodeKind`
    (IRI, literal…), `sh:in` (lista fechada de valores permitidos);
  - texto: `sh:minLength`, `sh:pattern` (expressão regular), `sh:languageIn`, `sh:uniqueLang`.
- **Relatório de validação**: `sh:conforms` (true/false) e um `sh:ValidationResult` por violação,
  com `sh:focusNode` (o nó em causa), `sh:resultPath` (o predicado), `sh:value` (o valor ofensivo),
  `sh:sourceShape` e `sh:resultMessage`.

**OWL vs SHACL, numa frase:** OWL diz o que as coisas **significam** e permite **inferir**; SHACL diz
o que os dados **têm de cumprir** e permite **verificar**. Usam-se juntos.

**pySHACL** é a implementação em Python. Um pormenor importante: o `sh:class C` aceita instâncias
de **subclasses** de C, desde que os triplos `rdfs:subClassOf` estejam no grafo de dados (a norma
SHACL segue `rdf:type/rdfs:subClassOf*`). É por isso que validamos os dados **junto com a
ontologia**: um Product passa no `sh:class fl:Entity` sem ser preciso ativar inferência.

### No MEALHEIRO

**Validação em dois níveis:**
1. **Pydantic** (durante a extração, por pedaço): forma do JSON e valores permitidos. Erro → pede-se
   outra vez ao LLM.
2. **SHACL** (depois de construir o grafo, sobre o grafo todo): regras que envolvem vários factos
   ou que só se veem com o grafo junto. Erro → o facto é **removido** e fica no relatório.

**As 4 shapes** (`kg/shapes.ttl`), cada uma ligada a um erro típico de extração:

| Shape | Alvo | O que exige | Erro que apanha |
|---|---|---|---|
| `EntityShape` | todas as Product, Concept, Cost, Risk, Right | ≥1 `rdfs:label` `@pt`, sem duas na mesma língua; `definition` `@pt` com ≥20 caracteres; `hasTopic` aponta para um `fl:Topic`; `relatedTo` aponta para uma `fl:Entity`; ≥1 `prov:wasDerivedFrom` | entidade sem nome, definição vazia, tema inventado, entidade sem fonte |
| `ProductShape` | todos os Product | `hasCost` → `fl:Cost`; `hasRisk` → `fl:Risk`; `regulatedBy` ∈ {BdP, CMVM, ASF} | custo que não é custo; supervisor inventado |
| `ProductOnlyShape` | **sujeitos** de `hasCost`/`hasRisk`/`regulatedBy` | têm de ser `fl:Product` | um Concept com custos (ex.: "indemnização hasCost …") |
| `StatementShape` | todos os `rdf:Statement` | exatamente 1 sujeito, 1 predicado (da lista da ontologia), 1 objeto; ≥1 `prov:wasDerivedFrom` IRI que começa por `http` | facto sem fonte |

Repara no truque do `ProductOnlyShape`: `sh:targetSubjectsOf` apanha **quem usa** a relação, mesmo
que não seja um Product. Isto é exatamente o que `rdfs:domain` não faz (o domain inferiria que é um
Product, em vez de dar erro).

**O filtro** (`shacl_filter()` em `kg/build_kg.py`), repetido até 5 vezes, porque remover pode criar
violações novas:
1. Valida `dados + ontologia + temas` contra as shapes (a ontologia vai junto por causa do `subClassOf`, ver acima).
2. Para cada violação:
   - veio do `ProductOnlyShape` → remove as relações `hasCost`/`hasRisk`/`regulatedBy` daquele nó (a
     culpa é da relação, não da entidade);
   - o nó é um `Statement` → remove o facto que descreve e o próprio `Statement`;
   - há valor e caminho → remove **só esse triplo** (por exemplo, o `hasCost` que aponta para algo que não é Cost);
   - caso contrário → remove o nó inteiro (por exemplo, uma entidade sem nome).
3. Remove `Statement`s **órfãos** (cujo triplo já não existe).
4. Cuidado de implementação: `graph.remove((s, p, None))` remove **todos** os objetos (None é um
   *wildcard*); por isso nunca se remove um triplo com um `None` por engano.

**Resultado (KG v1, 3 fontes):** 3567 → 3462 factos (105 removidos, 88 violações; só ASF eram 926 → 912), relatório em `data/kg/kg_shacl_report.txt`.
Exemplos reais: `crédito habitação hasRisk justa causa`; `seguro de acidentes de trabalho hasCost
prestações em dinheiro` (é um benefício); `fundos de pensões hasCost unidades de participação`;
`indemnização`, `segurador`, `prémio de seguro` com `hasCost` (não são produtos).

**Demonstração com erros de propósito** (`kg/examples/erros_de_proposito.jsonl`): o Pydantic
rejeita o tipo "Bank"; uma relação sem ponta é descartada; o SHACL apanha 3 violações. A
**ablação** `--no-shacl` constrói o KG sem o filtro, para medir na avaliação quanto o SHACL ajuda.

### Perguntas para testar
- Porque é que precisamos de SHACL se já temos `rdfs:domain`/`rdfs:range` na ontologia?
- O que faz `sh:targetSubjectsOf` e porque é que o `ProductOnlyShape` o usa?
- Porque é que o filtro corre em ciclo?
- Porque é que não deitamos fora a entidade toda quando um `hasCost` está errado?

---

## 9. SPARQL e triplestores

### Teoria

**SPARQL** é a linguagem de consulta para RDF (como SQL para tabelas). A ideia central é o
**padrão de grafo**: escreves triplos com **variáveis** (`?x`) e o motor encontra todas as formas
de as substituir por valores que existam no grafo.
```sparql
PREFIX fl: <https://w3id.org/mealheiro/fl#>
SELECT ?produto ?custo WHERE {
  ?produto a fl:Product ;
           fl:hasCost ?custo .
}
```
Construções importantes: `FILTER` (condições), `OPTIONAL` (parte que pode faltar, como um LEFT
JOIN), `UNION`, `BIND` (criar valores), `COALESCE` (o primeiro valor que existir), `ORDER BY`,
`LIMIT`, caminhos de propriedades (`rdfs:label|skos:altLabel` = um ou outro; `skos:broader+` = um
ou mais saltos). Outros tipos de consulta: `ASK` (sim/não), `CONSTRUCT` (devolve um grafo),
`DESCRIBE`.

**Triplestore**: base de dados para RDF com um **endpoint SPARQL** (HTTP). O **Apache Jena Fuseki**
é um servidor SPARQL com armazenamento persistente (TDB) e interface web. Corre num contentor
**Docker** (um ambiente isolado e reprodutível, descrito em `docker-compose.yml`).

### No MEALHEIRO

`kg/sparql.py` tem duas consultas:

**`LABELS`**: todas as entidades com os seus nomes (para encontrar uma entidade pelo nome):
```sparql
SELECT ?entity ?type ?label WHERE {
  ?entity a ?type ; rdfs:label|skos:altLabel ?label .
  FILTER(STRSTARTS(STR(?type), STR(fl:)))
}
```
`find_entity()` compara o nome pedido com estes nomes usando a normalização do capítulo 7.

**`ONE_HOP`**: todos os factos **a 1 salto** de uma entidade, com a fonte:
```sparql
SELECT ?sLabel ?p ?oLabel ?source WHERE {
  ?st a rdf:Statement ;
      rdf:subject ?s ; rdf:predicate ?p ; rdf:object ?o ;
      prov:wasDerivedFrom ?source .
  FILTER(?s = ?entity || ?o = ?entity)         # a entidade é sujeito OU objeto
  OPTIONAL { ?s rdfs:label ?sl }
  OPTIONAL { ?o rdfs:label|skos:prefLabel ?ol } # o objeto pode ser um tema (prefLabel)
  BIND(COALESCE(?sl, STR(?s)) AS ?sLabel)
  BIND(COALESCE(?ol, ?o) AS ?oLabel)           # definições são literais: usa-se o próprio valor
}
ORDER BY ?p
```
Lê-se assim: "dá-me todos os factos descritos (com fonte) em que a entidade aparece, com os nomes
legíveis de cada ponta". Percorre os `Statement`s porque são eles que têm a fonte; é este o
contexto que o chatbot (c) vai dar ao LLM, e são estas fontes que vão aparecer nas citações.
**1 salto** = só os vizinhos diretos; mais saltos trazem mais ruído (o QuARK mostrou que triplos a
mais prejudicam).

**Dois modos** (`run()`): sem `--endpoint`, carrega `kg.ttl` + ontologia + temas no **rdflib** e
corre a consulta em memória (não precisa de nada instalado; é o que usamos). Com
`--endpoint`, envia a consulta ao **Fuseki** com o `SPARQLWrapper`. `kg/load_fuseki.py` carrega os
ficheiros no Fuseki com um HTTP PUT (Graph Store Protocol). O Fuseki ainda não foi testado nesta
máquina porque o Docker Desktop não estava a arrancar.

### Perguntas para testar
- O que faz o `OPTIONAL` na consulta `ONE_HOP` e o que acontecia sem ele?
- Porque é que a consulta percorre os `rdf:Statement` em vez dos triplos diretos?
- Porque é que só vamos a 1 salto?
- Que vantagem tem o Fuseki face a carregar o ficheiro no rdflib?

---

## 10. Recuperação de informação: embeddings e FAISS

### Teoria

**Recuperação de informação (IR)**: dada uma pergunta, encontrar os documentos mais relevantes.

**Recuperação lexical** (clássica): compara **palavras**. TF-IDF e **BM25** dão mais peso a palavras
raras que aparecem no documento. Problema: "seguro da casa" não encontra "seguro de habitação"
(palavras diferentes, mesmo sentido).

**Recuperação densa** (com embeddings): um modelo transforma cada texto num **vetor** de números
(um *embedding*) de tal forma que textos com significado parecido ficam com vetores próximos. A
pergunta é transformada da mesma maneira e procuram-se os vetores mais próximos.
- Modelos **bi-encoder**: codificam pergunta e documento **separadamente** (dá para pré-calcular
  todos os documentos). São treinados com **aprendizagem contrastiva**: aproximar pares
  (pergunta, passagem relevante) e afastar pares não relevantes.
- **Semelhança do cosseno**: cos(a, b) = (a·b) / (‖a‖‖b‖), de −1 a 1. Se os vetores forem
  **normalizados** (comprimento 1), o cosseno é simplesmente o **produto interno** a·b.

**BGE-M3** (BAAI, 2024): modelo de embeddings **multilingue** (100+ línguas, incluindo português),
textos até 8192 tokens, vetores densos de **1024 dimensões**. O "M3" vem de *multi-lingual,
multi-granularity, multi-functionality*: também produz representações esparsas e multi-vetor
(não usamos; só a densa).

**FAISS** (Facebook AI Similarity Search): biblioteca para encontrar vizinhos mais próximos em
muitos vetores. `IndexFlatIP` faz pesquisa **exata** por produto interno (compara com todos);
índices aproximados (IVF, HNSW) trocam um pouco de exatidão por velocidade quando há milhões de vetores.

**Chunking para recuperação.** Pedaços pequenos são mais precisos mas perdem contexto; grandes têm
mais contexto mas diluem o significado. ~200–500 palavras é comum.

**Métrica: recall@k**: em que fração das perguntas o documento certo aparece entre os *k* primeiros.

### No MEALHEIRO

`retrieval/text_index.py`:
- `chunk_page()`: parágrafos inteiros até ~**300 palavras** → **292 pedaços** de 91 páginas.
- `embed()`: pede os vetores ao **Ollama** (`/api/embed`, modelo `bge-m3`), em lotes de 16, e
  normaliza-os (`faiss.normalize_L2`).
  **Porquê no Ollama e não com `sentence-transformers`?** Evita instalar o PyTorch (~2 GB) só para
  isto e usa o mesmo serviço que o LLM. O modelo é o mesmo BGE-M3 prometido na proposta.
- O texto do embedding é `título + "\n" + pedaço`: ajuda quando o pedaço não repete o tema da
  página (por exemplo, um pedaço do meio de "Taxas de juro").
- `IndexFlatIP` (exato; com ~300 vetores é instantâneo). Gravado em `data/index/text.faiss` +
  `data/index/chunks.jsonl` (o texto e o URL de cada vetor).
- `TextIndex.search(pergunta, k=5)` devolve os 5 pedaços mais parecidos com a pontuação.
- Nos baselines, os embeddings de **todas** as perguntas calculam-se de uma vez antes de gerar
  respostas: assim a GPU não está sempre a trocar entre o BGE-M3 e o qwen3:8b.

**Resultado:** **recall@5 = 98%** (46/47 perguntas com resposta têm a página certa nas 5
passagens). A recuperação de texto não é o ponto fraco.

### Perguntas para testar
- Porque é que "seguro da casa" encontra "seguro de habitação" com embeddings e não com BM25?
- Porque é que normalizamos os vetores antes de usar produto interno?
- Porque é que o FAISS exato chega para nós?
- O que mede o recall@5 e o que **não** mede?

---

## 11. RAG: geração aumentada por recuperação

### Teoria

**RAG** (*Retrieval-Augmented Generation*, Lewis et al., 2020): antes de responder, **recuperar**
documentos relevantes e dá-los ao LLM no prompt, pedindo que responda com base neles. Vantagens:
conhecimento atualizável sem retreinar, respostas **fundamentadas**, possibilidade de **citar**.

**Modos de falha:**
1. **Falha de recuperação**: a passagem certa não vem.
2. **Passagens distratoras**: vem algo parecido mas irrelevante, e o modelo usa-o.
3. **Geração infiel**: a passagem certa está lá, mas o modelo acrescenta ou contradiz.
4. **Falta de abstenção**: a resposta não está nas passagens, mas o modelo responde à mesma.

**GraphRAG / KG-RAG**: em vez de (ou além de) texto, dar ao LLM **factos de um grafo**. Vantagens:
factos curtos e precisos, ligações explícitas, sinais estruturais (se as entidades existem e se
estão ligadas). Exemplos: QuARK (triplos + texto), SubgraphRAG (subgrafos pontuados).

### No MEALHEIRO

**Três sistemas, o mesmo LLM** (`qwen3:8b`, temperatura 0, até 3 frases): a única diferença é o
contexto. Assim, a diferença nos resultados deve-se ao contexto e não ao modelo.

| Sistema | Contexto | Ficheiro | Estado |
|---|---|---|---|
| (a) só LLM | nenhum | `baselines/llm_only.py` | ✅ |
| (b) RAG com texto | 5 passagens numeradas [1]…[5] com título e URL | `baselines/text_rag.py` | ✅ |
| (c) KG + texto | factos a 1 salto do KG (com fonte) + passagens + sinais de confiança | Checkpoint 2 | ⏳ |

**O prompt do (b)**: responder em PT-PT, no máximo 3 frases, **só** com a informação das passagens;
citar com `[n]`; se as passagens não tiverem a resposta ou se for um pedido de conselho pessoal,
responder **exatamente** "Não posso responder com segurança." A frase fixa torna a abstenção
detetável automaticamente (`is_abstention()` em `generation/llm.py`).

**`baselines/run.py`** corre um sistema sobre `eval/questions.jsonl` e grava
`eval/results/<sistema>.jsonl` (pergunta, resposta, se se absteve, passagens, tempo); retoma onde
parou e no fim mostra o resumo.

**Resultados (75 perguntas):**

| | (a) | (b) |
|---|---|---|
| Absteve-se nas 47 que **têm** resposta (↓ melhor) | 13% | **0%** |
| Absteve-se nas 14 **sem resposta** (↑ melhor) | 36% | **86%** |
| Absteve-se nos 14 **conselhos** (↑ melhor) | 100% | 93% |
| recall@5 | – | 98% |

Os modos de falha observados no (b) são exatamente os da teoria:
- **passagem distratora + falta de abstenção**: "comissão de manutenção da CGD": responde com uma
  passagem sobre serviços mínimos bancários e o nome do banco. Parece fundamentado, mas não está;
- **conselho mal detetado**: "quanto devo poupar para me reformar aos 60" dá um conselho vago;
- **abstenção por outras palavras**: "não está disponível nas passagens", que o detetor por frase
  exata não conta.

É aqui que entra o (c): os sinais do KG (a "CGD" não existe no grafo) e a semantic entropy devem
apanhar estes casos.

### Perguntas para testar
- Porque é que os três sistemas usam o mesmo LLM e a mesma temperatura?
- Dá um exemplo nosso de cada modo de falha do RAG.
- Porque é que a frase de abstenção é fixa? Que problema isso cria?
- O que é que o KG acrescenta ao RAG, concretamente?

---

## 12. Incerteza e abstenção

*(Checkpoint 2: aqui fica a teoria e o plano; o código ainda não existe.)*

### Teoria

**Previsão seletiva** (*selective prediction*): um sistema que pode dizer "não sei". Há um
compromisso entre **cobertura** (fração de perguntas a que responde) e **risco** (fração de erros nas
que responde). A **curva accuracy–coverage** mostra a exatidão para cada nível de cobertura:
responder só quando a confiança é alta deve dar menos respostas, mas mais certas.

**Porque não basta perguntar ao modelo.** Os LLMs são mal calibrados: dizem coisas erradas com o
mesmo tom confiante. A abstenção "por instrução no prompt" (o que fazem os baselines) depende de o
modelo saber que não sabe, o que muitas vezes não acontece (vimos o (a) inventar a Euribor).

**Semantic entropy** (Kuhn et al., 2023; Farquhar et al., Nature 2024):
1. Gerar **N respostas** à mesma pergunta com temperatura > 0 (nós: N = 5).
2. **Agrupar** as respostas que dizem **o mesmo** (mesmo que com palavras diferentes). Duas respostas
   A e B ficam no mesmo grupo se **A implica B e B implica A** (*implicação bidirecional*), decidido
   por um modelo de **NLI**.
3. Calcular a **entropia** da distribuição pelos grupos. Com a frequência de cada grupo
   p(c) = (n.º de respostas no grupo c) / N:

   **SE = − Σ_c p(c) · log p(c)**

   - 5 respostas iguais → 1 grupo → SE = 0 (o modelo está seguro).
   - 5 respostas todas diferentes → 5 grupos → SE = log 5 ≈ 1,61 (o modelo está a "confabular").

   A ideia: a incerteza que importa é sobre o **significado**, não sobre as palavras. "28%" e
   "uma taxa de 28 por cento" são a mesma resposta.

**NLI** (*Natural Language Inference*): dado um par (premissa, hipótese), classificar como
**implicação** (*entailment*), **neutro** ou **contradição**. Usamos o **mDeBERTa-v3** treinado em
**XNLI** (NLI multilingue, inclui português). É um modelo já treinado: só o usamos, não o treinamos.

**Sinais do KG** (a nossa contribuição):
- **`entities_found`**: quantas (ou que fração) das entidades mencionadas na pergunta foram
  encontradas no KG. Se a pergunta fala da "CGD" ou de "criptomoedas" e nada disso existe no
  grafo, a pergunta está provavelmente fora das fontes.
- **`facts_connect`**: se os factos recuperados **ligam** as entidades da pergunta entre si (há um
  caminho no grafo). Para uma pergunta multi-salto, ter as duas entidades mas desligadas é sinal de
  risco.

**Regressão logística**: combina os sinais x = (SE, entities_found, facts_connect) numa
probabilidade:

**P(resposta correta | x) = σ(w₀ + w₁·SE + w₂·entities_found + w₃·facts_connect)**, com σ(z) = 1/(1+e^(−z))

- Treina-se minimizando a **log-loss** (entropia cruzada) em respostas de **dev** rotuladas como
  certas ou erradas.
- É **interpretável**: o sinal e o tamanho de cada wᵢ dizem quanto cada sinal pesa (espera-se w₁ < 0,
  porque mais entropia dá menos probabilidade de estar certa).
- Não é uma rede neuronal; são 4 números.

**Limiar (*threshold*)**: responde-se se P ≥ τ; abaixo, abstém-se. O τ escolhe-se em **validação**
(por exemplo, o que maximiza a exatidão para uma cobertura mínima), nunca no teste.

**Métricas de confiança:**
- **AUROC**: probabilidade de uma resposta certa escolhida ao acaso ter **mais** confiança do que
  uma errada escolhida ao acaso. 0,5 = ao acaso; 1 = separa perfeitamente.
- **Calibração / ECE** (*Expected Calibration Error*): divide as previsões em intervalos de confiança
  (por exemplo 0–0,1, 0,1–0,2…) e compara, em cada intervalo, a confiança média com a exatidão real:
  **ECE = Σ_b (|B_b|/n) · |acc(B_b) − conf(B_b)|**. Se o modelo diz 80% e acerta 80% das vezes,
  está calibrado. Visualiza-se com um **diagrama de fiabilidade**.

### No MEALHEIRO (plano para o Checkpoint 2)

Pasta `uncertainty/`: (1) gerar 5 respostas com T > 0; (2) agrupá-las com o mDeBERTa-XNLI
(implicação nos dois sentidos); (3) calcular a SE; (4) calcular `entities_found` e `facts_connect`
a partir do entity linking e do SPARQL; (5) treinar a regressão logística (scikit-learn) nas
respostas de dev; (6) escolher τ em val; (7) avaliar no teste. Comparação das três condições de
abstenção: **instrução no prompt** (o que os baselines já fazem) vs **semantic entropy sozinha** vs
**sinais combinados**. Ablação: **sem os sinais do KG**.

### Perguntas para testar
- Calcula a SE para 5 respostas em que 3 dizem "28%" e 2 dizem "25%". (−0,6·ln 0,6 − 0,4·ln 0,4 ≈ 0,67)
- Porque é que a implicação tem de ser bidirecional? (A "a taxa é 28%" implica B "há uma taxa",
  mas B não implica A; não são a mesma resposta.)
- Porque é que se escolhe o limiar em validação e não no teste?
- O que quer dizer AUROC = 0,5? E ECE = 0?
- Que sinal do KG apanharia a pergunta sobre a CGD?

---

## 13. Avaliação

### Teoria

**Conjuntos separados**: **dev/treino** (ajustar o modelo; aqui a regressão), **validação**
(escolher hiperparâmetros como o limiar), **teste** (medir no fim, uma vez). Usar o teste para
afinar dá resultados otimistas (*overfitting* ao teste).

**Baselines e ablações.** Um **baseline** é uma alternativa mais simples para comparar (sem ele, um
número sozinho não diz nada). Uma **ablação** remove uma parte do sistema para medir a sua
contribuição.

**LLM como juiz** (*LLM-as-a-judge*): usar um LLM para decidir se uma resposta está correta face à
resposta de referência. Mais barato do que anotar à mão, mas tem de ser **validado** contra
anotação humana numa amostra.

**Cohen's kappa**: concordância entre dois anotadores (o juiz e nós) descontando a que aconteceria
por acaso: **κ = (p_o − p_e) / (1 − p_e)**, em que p_o é a concordância observada e p_e a esperada ao
acaso. κ ≈ 0: concordância ao acaso; > 0,6 boa; > 0,8 muito boa.

**RAGAS** (Es et al., 2024): métricas para RAG, calculadas com um LLM: **faithfulness** (as
afirmações da resposta são suportadas pelo contexto?), **context precision/recall**, **answer
relevancy**. Precisão das citações: as passagens citadas `[n]` suportam a frase onde estão?

### No MEALHEIRO

**`eval/questions.jsonl`**: 75 perguntas de teste (o resto até ~150 de teste e ~50 de dev/val no
Checkpoint 2). Campos: `id, question, type, gold_answer, source_url, answerable, split` e
`evidence` (citação literal da página que prova a resposta).

| Tipo | N.º | Para medir |
|---|---|---|
| conceptual | 25 | explicação de conceitos |
| numeric | 12 | números e contas (taxas, limites, prazos) |
| multihop | 10 | juntar dois factos (onde o KG deve ajudar mais) |
| unanswerable | 14 | abster-se quando a informação não está nas fontes |
| advice | 14 | abster-se em pedidos de conselho pessoal |

Como foram feitas: as 47 com resposta foram redigidas com ajuda de um LLM a partir do corpus,
cada uma com a citação literal; um script confirmou que cada citação existe na página citada.
As 28 sem resposta/conselho foram escritas à mão; confirmámos no corpus que a informação pedida não
existe. **Têm de ser revistas por nós.**

**Plano de métricas** (proposta):
- **Correção**: LLM-judge, validado com Cohen's kappa contra rótulos nossos numa amostra.
- **Fidelidade e precisão das citações**: RAGAS.
- **Qualidade da confiança**: AUROC, ECE, curva accuracy–coverage.
- **Precisão dos factos do KG**: amostra aleatória de factos auditada à mão contra a página.
- **Ablações**: sem SHACL (`--no-shacl`); sem os sinais do KG.

### Perguntas para testar
- Porque é que o (b) ter 0% de abstenção nas perguntas com resposta não prova que acertou?
- Para que serve o campo `evidence`?
- Porque é que um LLM-judge precisa de ser validado? Como?
- Que ablação mostra se o SHACL vale a pena?

---

## 14. Engenharia: como o código está organizado

- **Python ≥ 3.9**, ambiente virtual em `.venv/` (isola as bibliotecas do projeto).
- Cada pasta de topo é um **pacote** (tem `__init__.py`) e corre-se com `python -m pasta.modulo`
  a partir da raiz (os imports entre pastas funcionam assim).
- **Dados intermédios em ficheiros**, em formatos simples (JSONL, Turtle), por fases:
  `data/raw/` → `data/kg/extractions/` → `data/kg/kg.ttl`; `data/index/`; `eval/results/`.
  Cada fase pode ser refeita sem as anteriores.
- **Retomar onde parou**: o crawler, a extração e os baselines leem o que já fizeram e saltam.
  Essencial com uma extração que demora horas.
- **Determinismo**: temperatura 0, IRIs por hash e por nome normalizado, ordem fixa. Correr de novo
  dá o mesmo resultado.
- **Serviços locais**: Ollama (LLM e embeddings) em `localhost:11434`; Fuseki (opcional) em
  `localhost:3030` via Docker.
- **Bibliotecas principais**: `requests`, `trafilatura`, `html5lib`, `lxml` (recolha); `rdflib`,
  `pyshacl`, `SPARQLWrapper` (KG); `pydantic` (esquema); `numpy`, `faiss-cpu` (índice);
  a seguir `transformers` (mDeBERTa), `scikit-learn` (regressão), `ragas`, `streamlit`.
- Convenções: código em inglês e sem comentários; cada script tem uma docstring curta em inglês
  (o texto do `--help`). Os prompts do LLM e os dados ficam em português. As explicações estão
  neste manual e no guia. Os excertos de código neste manual são versões simplificadas e anotadas.

---

## 15. Mapa ficheiro a ficheiro

| Ficheiro | O que faz | Funções principais |
|---|---|---|
| `scraping/common.py` | sessão educada, cache, extração de texto, escrita do JSONL | `PoliteSession`, `extract_page`, `main_text`, `guess_topic`, `JsonlWriter` |
| `scraping/sources.py` | configuração de cada fonte | `Source`, `SOURCES` |
| `scraping/crawl.py` | crawler BFS (ASF) | `main` |
| `scraping/split_browser_bundle.py` | JSON do browser → um `.html` por página | `main` |
| `scraping/import_saved_html.py` | `.html` guardados → JSONL | `original_url`, `main` |
| `scraping/stats.py` | páginas e palavras por fonte e tema | `main` |
| `kg/ontology.ttl` | classes, relações, supervisores | – |
| `kg/topics.ttl` | temas do Referencial em SKOS | – |
| `kg/shapes.ttl` | as 4 shapes SHACL | – |
| `kg/schema.py` | esquema Pydantic da extração | `Entity`, `Relation`, `Extraction.drop_dangling` |
| `kg/extract.py` | extração com o LLM | `chunk_text`, `build_messages`, `call_llm`, `extract_chunk` |
| `kg/build_kg.py` | JSON → RDF + proveniência + SHACL | `entity_iri`, `add_fact`, `add_extraction`, `shacl_filter` |
| `kg/sparql.py` | consultas `LABELS` e `ONE_HOP` | `run`, `find_entity` |
| `kg/load_fuseki.py` | carregar no Fuseki | `main` |
| `kg/stats.py` | nós, ligações, entidades mais ligadas | `main` |
| `kg/visualize.py` | desenho HTML da vizinhança de um nó | `main` |
| `kg/examples/` | factos anotados à mão; erros de propósito | – |
| `retrieval/text_index.py` | pedaços, BGE-M3, FAISS | `chunk_page`, `embed`, `build`, `TextIndex` |
| `generation/llm.py` | chamada ao LLM partilhada; deteção de abstenção | `chat`, `is_abstention` |
| `baselines/llm_only.py` | baseline (a) | `answer` |
| `baselines/text_rag.py` | baseline (b) | `build_prompt`, `answer` |
| `baselines/run.py` | corre um baseline e resume | `main`, `summary` |
| `eval/questions.jsonl` | 75 perguntas de teste | – |
| `eval/results/*.jsonl` | respostas dos baselines | – |
| `docker-compose.yml` | serviço Fuseki | – |

---

## Para estudar: as 10 ideias que tens de saber explicar sem ler

1. Um KG em RDF são triplos sujeito–predicado–objeto; os nós são as entidades, as ligações são as
   relações entre nós, os literais são atributos.
2. A ontologia diz os tipos de nós (5 classes + supervisores + temas) e de ligações (hasCost,
   hasRisk, regulatedBy, relatedTo, hasTopic), a partir de perguntas de competência.
3. OWL serve para inferir (mundo aberto); SHACL para validar (mundo fechado). `domain`/`range`
   inferem, não verificam.
4. Cada facto guarda a fonte por reificação (`rdf:Statement` + `prov:wasDerivedFrom`); é daí que vêm
   as citações.
5. O LLM extrai factos com saída restringida pelo esquema Pydantic (garante a forma, não a verdade)
   e o SHACL remove o que viola as regras; o exemplo do plano de saúde mostra porquê.
6. Duas menções são a mesma entidade se o nome normalizado (minúsculas, sem acentos, singular) for igual.
7. A consulta `ONE_HOP` devolve os factos a 1 salto de uma entidade, com a fonte.
8. Os embeddings põem textos com o mesmo significado perto uns dos outros; o FAISS encontra os 5 mais
   próximos da pergunta; recall@5 = 98%.
9. Sem documentos o LLM inventa; com passagens (RAG) quase sempre se abstém quando deve, mas ainda
   falha com passagens distratoras: é isso que o KG e a incerteza vão resolver.
10. Semantic entropy + `entities_found` + `facts_connect` → regressão logística → P(correta) →
    responde se ≥ limiar (escolhido em validação), senão abstém-se; avalia-se com AUROC, ECE e
    accuracy–coverage.
