# SPEC.md · Como construir, etapa por etapa

> Execute **uma etapa por vez**, só quando pedido. As decisões de negócio estão no **PRD.md**; as regras técnicas (R1–R7, M1–M4) e o dicionário estão aqui. O agente SQL (Etapa 4\) e o MCP (Etapa 5\) leem o PRD.md e este arquivo inteiros a cada pergunta.

```
books.toscrape.com ──► bronze.livros ──► prata.livros ──► ouro.livros / ouro.categorias ──► agente SQL ──► MCP
     (Etapa 1)            (cru)            (Etapa 2)              (Etapa 3)                   (Etapa 4)      (Etapa 5)
```

&nbsp;

## Estado (o agente atualiza ao fim de cada etapa)

| etapa | status | decisões tomadas / observações |
| :---- | :---- | :---- |
| 1 · Scraping → bronze | ✅ feito e aprovado | Gravação via MCP do Supabase, sem `.env`: um script Python não acessa o MCP da sessão do agente, então criei `--saida-sql` em `01_scraper_bronze.py`, que gera o SQL para o agente executar. Na 2ª carga (`--paginas 2`), assinatura MD5 idêntica à da 1ª: gravada com `insert ... select` da 1ª, com o `_execucao_id` próprio. `id` com `primary key` (a SPEC só pedia `bigserial`). `descricao` lida de `#product_description + p` (seletor não previsto na SPEC). Depois, com `DATABASE_URL`, `aplicar_sql.py` e a gravação direta do scraper foram testados, e a carga completa de 50 páginas gravou 1.000 linhas. Bronze atual: 1.080 linhas (40 + 40 + 1.000) e 1.000 `upc` distintos. |
| 2 · Prata | ✅ feito e aprovado | Aplicada via MCP do Supabase e reaplicada com `python aplicar_sql.py sql/01_prata.sql`. R1: empate em `_ingestao_em` desempata por `id` mais recente. R7: `btrim` em `upc`, `titulo`, `categoria` e `url`, incluindo tab e quebra de linha. Mojibake em `titulo` **não é tratado**, pois nenhuma regra cobre (9 de 1.000 títulos, ex.: "Shakespeareâ..."). A view expõe 1.000 livros únicos; 219 ficam em `Sem categoria` (152 `Default` e 67 `Add a comment`). Sem exemplo nos dados atuais: estoque sem número (R4) e cargas com dados diferentes para o mesmo `upc` (R1). |
| 3 · Ouro | ✅ feito e aprovado | Aplicada via MCP do Supabase e reaplicada com `python aplicar_sql.py sql/02_ouro.sql`. `ouro.categorias` mantém a linha `Sem categoria`, exigida pelo critério `sum(qtd_titulos)` = total da prata; a exclusão de M4 fica nas consultas de ranking (Etapas 4 e 5). Sem coluna em reais, pois o dicionário não prevê: a conversão de M4 (× 7,20) também fica nas consultas. `preco_medio_gbp`, `rating_medio` e `pct_bem_avaliados` arredondados para 2 casas; `pct_bem_avaliados` na escala 0–100. Views calculadas sobre os 1.000 livros, em 49 categorias. |
| 4 · Agente SQL | ✅ feito (aguarda aprovação) | Critérios rodados com `claude-opus-5-5` e banco reais, sobre os 1.000 livros. Frontend `app_streamlit.py` e biblioteca `streamlit` adicionados a pedido do usuário. Cada pergunta consulta o banco de novo; o histórico leva só perguntas e respostas, para permitir esclarecimentos. `--sem-contexto` lê `public`, `bronze`, `prata` e `ouro`, não os schemas internos do Supabase, para não expor `auth` e similares ao LLM; a bronze só é recusada com o contexto ligado. Guardrails além da SPEC: bloqueio de funções `pg_*`, `set_config`, `dblink`, `query_to_xml` e similares, schemas internos e strings `E''`/`U&`. O bloqueio recusa qualquer SQL com a palavra `bronze`, mesmo em texto. Esta tabela de Estado também entra no contexto do agente: notas desatualizadas aparecem nas respostas, então ela precisa refletir o estado atual da base. |
| 5 · Servidor MCP | ⬜ a fazer |  |

&nbsp;

---

## Fonte de dados: books.toscrape.com

- Site público feito para treinar scraping. 50 páginas × 20 livros \= 1.000 livros.  
- Listagem: `https://books.toscrape.com/catalogue/page-{n}.html` → links em `article.product_pod h3 a`.  
- Detalhe do livro: título em `div.product_main h1`; preço em `div.product_main p.price_color`; avaliação na classe de `p.star-rating` (ex.: `star-rating Three`); tabela `table.table` com `UPC`, `Availability`, `Number of reviews`; categoria no 3º link de `ul.breadcrumb`.  
- **Encoding:** o site não declara charset. Com `requests`, o `£` costuma chegar como `Â£`. Na bronze isso fica como veio; R2 resolve na prata.  
- Campos do `payload` na bronze: `url`, `titulo`, `preco_raw`, `rating_raw`, `estoque_raw`, `upc`, `n_reviews_raw`, `categoria_raw`, `descricao`.

## Regras: bronze → prata

- **R1 · Chave e duplicidade:** chave \= `upc`. Manter só a linha com o `_ingestao_em` mais recente.  
- **R2 · Preço:** extrair só o número de `preco_raw` → `preco_gbp numeric(10,2)`. Moeda \= libra (GBP).  
- **R3 · Avaliação:** `star-rating One..Five` → `rating` 1..5.  
- **R4 · Estoque:** de `In stock (22 available)` extrair `22` → `estoque_qtd int`. Sem número \= 0\.  
- **R5 · Reviews:** `n_reviews_raw` → `n_reviews int`.  
- **R6 · Categoria:** `Default` e `Add a comment` não são categorias → `Sem categoria`.  
- **R7 · Texto:** remover espaços nas pontas.

## Métricas: ouro

- **M1 · Valor em estoque** \= `preco_gbp × estoque_qtd`.  
- **M2 · Bem avaliado** \= `rating >= 4` (decisão do PRD).  
- **M3 · Faixa de preço:** `até £20` (\< 20\) · `£20–40` (20 a \< 40\) · `acima de £40` (≥ 40).  
- **M4 · Moeda das respostas:** GBP. Se pedirem reais, câmbio do PRD (£1 \= R\$ 7,20). Rankings de categoria **excluem** `Sem categoria`, salvo pedido explícito.

## Dicionário de dados

- **prata.livros** (1 linha \= 1 livro): `upc` · `titulo` · `categoria` · `preco_gbp` · `rating` · `estoque_qtd` · `n_reviews` · `url` · `_ingestao_em`  
- **ouro.livros:** prata \+ `valor_estoque_gbp` (M1) · `faixa_preco` (M3) · `bem_avaliado` (M2, bool)  
- **ouro.categorias** (1 linha \= 1 categoria): `categoria` · `qtd_titulos` · `preco_medio_gbp` · `rating_medio` · `estoque_unidades` · `valor_estoque_gbp` · `pct_bem_avaliados`

---

## Etapa 1 · Scraping → bronze

**Entrega:** `requirements.txt`, `.env.exemplo`, `sql/00_bronze.sql`, `01_scraper_bronze.py`, `aplicar_sql.py`

Requisitos

- Tabela `bronze.livros` (`id bigserial`, `fonte_url text`, `payload jsonb`, `_execucao_id text`, `_ingestao_em timestamptz default now()`).  
- Raspar a **página de detalhe** de cada livro (a listagem não tem UPC nem estoque). Campos do `payload`: ver "Fonte de dados".  
- **Bronze é cru:** grava os textos exatamente como vieram. Nenhuma limpeza.  
- **Append-only:** cada execução insere de novo, sem upsert.  
- Parâmetro `--paginas N` (20 livros por página). Até 8 requisições em paralelo, com `User-Agent` próprio.  
- Conexão via MCP do supabase (priorize assim) ou \`DATABASE\_URL\` do \`.env\`. O script cria a tabela se ela não existir.  
- `aplicar_sql.py`: utilitário que **o próprio agente usa** nas etapas seguintes. `python aplicar_sql.py sql/arquivo.sql` executa o arquivo; `python aplicar_sql.py --query "select ..."` imprime o resultado.

Critérios de aceite

- `python 01_scraper_bronze.py --paginas 2` grava 40 linhas.  
- Rodar 2× → `select count(*), count(distinct payload->>'upc') from bronze.livros` \= 80 e 40\.  
- `select payload from bronze.livros limit 3` mostra os textos crus (`£`/`Â£`, `star-rating Three`, `In stock (N available)`).

---

## Etapa 2 · Prata

**Entrega:** `sql/01_prata.sql` (view `prata.livros`), aplicado no banco pelo agente: `python aplicar_sql.py sql/01_prata.sql`

Requisitos

- Aplicar **R1 a R7**, com `-- R<n>` em cada linha que aplica regra.  
- Colunas exatamente como no dicionário.

Critérios de aceite

- `count(*) = count(distinct upc)`.  
- Nenhum `preco_gbp`, `rating` ou `estoque_qtd` nulo.  
- Nenhuma categoria `Default` ou `Add a comment`.

---

## Etapa 3 · Ouro

**Entrega:** `sql/02_ouro.sql` (views `ouro.livros` e `ouro.categorias`), aplicado com `python aplicar_sql.py sql/02_ouro.sql`

Requisitos

- Métricas **M1 a M4**, com `-- M<n>` em cada linha que aplica métrica.  
- `ouro.livros` \= prata \+ `valor_estoque_gbp`, `faixa_preco`, `bem_avaliado`.  
- `ouro.categorias` \= 1 linha por categoria (colunas no dicionário).

Critérios de aceite

- `sum(qtd_titulos)` em `ouro.categorias` \= `count(*)` em `prata.livros`.  
- `faixa_preco` só tem os 3 valores definidos em M3.

---

## Etapa 4 · Agente SQL

**Entrega:** `04_sql_agent.py`, `app_streamlit.py` (frontend para testar o agente, pedido pelo usuário)

Requisitos

- Loop: pergunta → LLM gera **um** SQL em bloco ```` ```sql ```` → executa → LLM responde em português.  
- **Contexto do agente (o coração da etapa):** o system prompt é montado a cada execução com  
  1. instruções do agente (papel, só prata/ouro, um SELECT por vez, perguntar se ambíguo);  
  2. o **`PRD.md` e o `SPEC.md` inteiros**, lidos do disco (os mesmos arquivos que construíram o pipeline);  
  3. o **schema real** de `prata` e `ouro`, lido do `information_schema`.  
- Flag `--sem-contexto`: só a instrução mínima \+ o schema de **todas** as tabelas (para comparar em aula).  
- Guardrails: só `SELECT`/`WITH`, transação `read only`, `statement_timeout` de 10 s, `limit 50`, até 3 tentativas com o erro devolvido ao LLM.  
- Provedor e modelo por `.env`: `LLM_PROVIDER` (openai|anthropic), `LLM_MODEL`.  
- Imprimir o SQL gerado, o resultado e a resposta.

Critérios de aceite

- Acerta as 4 perguntas do PRD com o contexto ligado.  
- Nunca consulta `bronze` com o contexto ligado.

---

## Etapa 5 · Servidor MCP

**Entrega:** `05_mcp_server.py`, `mcp_config.exemplo.json`

Requisitos

- Servidor MCP (biblioteca `mcp`, FastMCP, transporte stdio) com 3 ferramentas: `ler_contexto` (devolve PRD.md \+ SPEC.md), `listar_schema` (prata e ouro via `information_schema`) e `consultar(sql)` (um SELECT, até 50 linhas).  
- Mesmos guardrails do agente: transação `read only`, `statement_timeout` 10 s, só `SELECT`/`WITH`, `bronze` proibida.  
- A descrição de cada ferramenta diz ao modelo **quando** usá-la (ler o contexto antes de escrever SQL; mostrar o SQL ao usuário).  
- `mcp_config.exemplo.json`: exemplo de configuração para Claude Desktop / Claude Code, sem segredo no arquivo.

Critérios de aceite

- `mcp dev 05_mcp_server.py` lista as 3 ferramentas e `consultar("select count(*) from prata.livros")` devolve o número.  
- Em um cliente MCP, a pergunta 1 do PRD gera uma consulta em `ouro.categorias` com câmbio 7,20 e sem `Sem categoria`.  
- `consultar("select * from bronze.livros")` é recusado.