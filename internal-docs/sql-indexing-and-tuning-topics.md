# SQL Indexing and Tuning — Mapa de Tópicos

**Fonte:** [Use The Index, Luke!](https://use-the-index-luke.com/) — versão web do livro *SQL Performance Explained*, de Markus Winand.
**Cobertura:** Db2 (LUW), MySQL/MariaDB, Oracle, PostgreSQL, SQL Server, SQLite, Gupta SQLBase.
**Varredura:** 01/08/2026 — todos os capítulos, subcapítulos, apêndices e verbetes do glossário.

**Para que serve este documento:** é um índice de contexto. Cada item traz o nome oficial do tópico, uma frase do que ele trata e o link direto. Serve para localizar rapidamente qual seção do material responde a um problema de performance específico, e para saber o que precisa ser aplicado em um projeto.

> **Banco-alvo deste material: PostgreSQL.** Itens que não se aplicam ao PostgreSQL estão marcados com ⚠️. O Apêndice A traz a seção do PostgreSQL detalhada e os demais bancos apenas referenciados. Há um bloco de notas específicas de PostgreSQL antes do resumo final.

---

## Prefácio

### [Preface — Developers Need to Index](https://use-the-index-luke.com/sql/preface)
A tese do livro: indexação é responsabilidade do desenvolvedor, não do DBA, porque só quem escreveu a query conhece os dados e o caminho de acesso.

---

## 1. [Anatomy of an SQL Index](https://use-the-index-luke.com/sql/anatomy)
A estrutura física de um índice — redundância pura, com espaço em disco próprio, que só existe para dar ordem aos dados.

- **[The Index Leaf Nodes](https://use-the-index-luke.com/sql/anatomy/the-leaf-nodes)** — os leaf nodes formam uma lista duplamente encadeada, que mantém a ordem lógica sem exigir ordem física em disco.
- **[The Search Tree (B-Tree)](https://use-the-index-luke.com/sql/anatomy/the-tree)** — a árvore balanceada sobre os leaf nodes é o que torna a busca rápida (profundidade cresce só a cada ~100x mais linhas).
- **[Slow Indexes, Part I](https://use-the-index-luke.com/sql/anatomy/slow-indexes)** — por que uma busca indexada pode ser lenta: além da travessia da árvore, há a varredura da cadeia de leaf nodes e o acesso à tabela.

---

## 2. [The Where Clause](https://use-the-index-luke.com/sql/where-clause)
Como cada operador do WHERE afeta o uso do índice — o capítulo mais importante, porque um WHERE mal escrito é o primeiro ingrediente de uma query lenta.

### 2.1 [The Equality Operator](https://use-the-index-luke.com/sql/where-clause/the-equals-operator)
O operador `=` e as armadilhas de índice em condições combinadas.

- **[Primary Keys](https://use-the-index-luke.com/sql/where-clause/the-equals-operator/primary-keys)** — busca por chave primária usa INDEX UNIQUE SCAN (só travessia da árvore); ensina a verificar isso no plano de execução.
- **[Concatenated Indexes](https://use-the-index-luke.com/sql/where-clause/the-equals-operator/concatenated-keys)** — em índices multi-coluna a **ordem das colunas** determina para quais queries o índice serve; uma coluna não-líder não permite acesso eficiente.
- **[Slow Indexes, Part II](https://use-the-index-luke.com/sql/where-clause/the-equals-operator/slow-indexes-part-ii)** — como o otimizador escolhe entre índices disponíveis e os efeitos colaterais de alterar um índice existente.

### 2.2 [Functions](https://use-the-index-luke.com/sql/where-clause/functions)
Funções aplicadas sobre a coluna tornam o índice inutilizável — a saída é o índice baseado em função / coluna computada.

- **[Case-Insensitive Search](https://use-the-index-luke.com/sql/where-clause/functions/case-insensitive-search)** — `UPPER(coluna) = ...` só usa índice se existir um índice sobre `UPPER(coluna)` (ou uma collation case-insensitive).
- **[User-Defined Functions](https://use-the-index-luke.com/sql/where-clause/functions/user-defined-functions)** — só funções determinísticas podem ser indexadas; nada que dependa de data/hora atual.
- **[Over-Indexing](https://use-the-index-luke.com/sql/where-clause/functions/over-indexing)** — evite índices redundantes: padronize o mesmo caminho de acesso na aplicação para que um índice sirva a várias queries.

### 2.3 [Bind Parameters](https://use-the-index-luke.com/sql/where-clause/bind-parameters)
Usar placeholders (`?`, `:nome`) em vez de literais previne SQL injection e permite reaproveitar o plano de execução em cache.

### 2.4 [Searching for Ranges](https://use-the-index-luke.com/sql/where-clause/searching-for-ranges)
Operadores de desigualdade também usam índice, mas restringem fortemente a escolha da ordem das colunas.

- **[Greater, Less and BETWEEN](https://use-the-index-luke.com/sql/where-clause/searching-for-ranges/greater-less-between-tuning-sql-access-filter-predicates)** — regra de ouro: manter a faixa varrida do índice a menor possível, colocando as colunas de igualdade antes das de range.
- **[Indexing LIKE Filters](https://use-the-index-luke.com/sql/where-clause/searching-for-ranges/like-performance-tuning)** — só o trecho antes do primeiro coringa vira condição de acesso; `LIKE '%x%'` não é busca full-text.
- **[Index Merge](https://use-the-index-luke.com/sql/where-clause/searching-for-ranges/index-merge-performance)** — um índice concatenado quase sempre vence vários índices de coluna única; combinar índices só compensa em ranges independentes.

### 2.5 [Partial Indexes](https://use-the-index-luke.com/sql/where-clause/partial-and-filtered-indexes)
**★ Recurso nativo do PostgreSQL.** Índices parciais indexam apenas as linhas que interessam, via cláusula `WHERE` na definição do índice — ideal para filas de trabalho (`WHERE processed = 'N'`) e flags de status.

### 2.6 ⚠️ [NULL in the Oracle Database](https://use-the-index-luke.com/sql/where-clause/null)
**Capítulo inteiro é específico do Oracle — não se aplica ao PostgreSQL**, que indexa NULLs normalmente e tem índices parciais de verdade; leia apenas como curiosidade.

- **[Indexing NULL](https://use-the-index-luke.com/sql/where-clause/null/index)** — ⚠️ o Oracle não indexa a linha quando **todas** as colunas do índice são NULL, logo todo índice é implicitamente parcial.
- **[NOT NULL Constraints](https://use-the-index-luke.com/sql/where-clause/null/not-null-constraint)** — ⚠️ no Oracle, indexar `IS NULL` exige alguma coluna com constraint NOT NULL no índice.
- **[Emulating Partial Indexes](https://use-the-index-luke.com/sql/where-clause/null/partial-index)** — ⚠️ gambiarra para simular índice parcial no Oracle; no PostgreSQL use `CREATE INDEX ... WHERE ...` (seção 2.5).

### 2.7 [Obfuscated Conditions](https://use-the-index-luke.com/sql/where-clause/obfuscation)
Catálogo de anti-padrões que impedem o uso do índice sem que pareça óbvio.

- **[Dates](https://use-the-index-luke.com/sql/where-clause/obfuscation/dates)** — `TRUNC(data)` e conversões sobre a coluna de data quebram o índice; aplique a função no termo de busca, não na coluna.
- **[Numeric Strings](https://use-the-index-luke.com/sql/where-clause/obfuscation/numeric-strings)** — comparar coluna texto com número gera cast implícito na coluna e mata o índice; converta o parâmetro.
- **[Combining Columns](https://use-the-index-luke.com/sql/where-clause/obfuscation/concatenation)** — combinar colunas (data + hora, concatenações) impede o uso do índice concatenado; reescreva com condições redundantes ou use um tipo único.
- **[Smart Logic](https://use-the-index-luke.com/sql/where-clause/obfuscation/smart-logic)** — o padrão `WHERE (:p IS NULL OR coluna = :p)` para queries "genéricas" é o jeito mais fácil de tornar SQL lento; use SQL dinâmico de verdade.
- **[Math](https://use-the-index-luke.com/sql/where-clause/obfuscation/math)** — bancos não resolvem equações: deixe a coluna sozinha de um lado da comparação e as constantes do outro.

---

## 3. [Performance and Scalability](https://use-the-index-luke.com/sql/testing-scalability)
Escalabilidade vista como o impacto de mudanças no ambiente (volume, carga, hardware) sobre o tempo de resposta.

- **[Data Volume](https://use-the-index-luke.com/sql/testing-scalability/data-volume)** — indexação descuidada não aparece em base pequena, mas degrada de forma não-linear conforme o volume cresce.
- **[System Load](https://use-the-index-luke.com/sql/testing-scalability/system-load)** — filter predicates escondidos no plano custam pouco em teste isolado e muito sob carga de produção.
- **[Response Time and Throughput](https://use-the-index-luke.com/sql/testing-scalability/response-time-throughput-scaling-horizontal)** — mais hardware aumenta vazão, não reduz o tempo de resposta de uma query; escala horizontal não conserta query lenta.

---

## 4. [The Join Operation](https://use-the-index-luke.com/sql/join)
Joins processam sempre duas tabelas por vez, e o índice certo depende de qual dos três algoritmos o banco escolher.

- **[Nested Loops](https://use-the-index-luke.com/sql/join/nested-loops-join-n1-problem)** — laço aninhado com lookup por índice a cada linha; é a origem do problema N+1 dos ORMs, e indexa-se o lado interno pelas colunas do join.
- **[Hash Join](https://use-the-index-luke.com/sql/join/hash-join-partial-objects)** — monta uma hash table de um dos lados; aqui **não** se indexam as colunas do join, e sim os predicados WHERE independentes (e seleciona-se menos colunas).
- **[Sort-Merge Join](https://use-the-index-luke.com/sql/join/sort-merge-join)** — junta duas listas ordenadas como um zíper, é simétrico (bom para full outer join), mas raro por exigir ordenação dos dois lados.

---

## 5. [Clustering Data](https://use-the-index-luke.com/sql/clustering)
O "segundo poder" do índice: armazenar junto o que é lido junto, para reduzir o número de operações de I/O.

- **[Index Filter Predicates Used Intentionally](https://use-the-index-luke.com/sql/clustering/index-filter-predicates)** — adicionar ao índice colunas que não servem como access predicate, de propósito, para evitar acessos à tabela.
- **[Index-Only Scan](https://use-the-index-luke.com/sql/clustering/index-only-scan-covering-index)** — o método de tuning mais poderoso: se o índice contém todas as colunas da query (inclusive as do SELECT), a tabela nunca é lida.
- ⚠️ **[Index-Organized Tables and Clustered Indexes](https://use-the-index-luke.com/sql/clustering/index-organized-clustered-index)** — a tabela armazenada dentro do B-Tree (Oracle IOT / SQL Server / MySQL InnoDB); **o PostgreSQL não tem isso** — só heap tables, com o comando `CLUSTER` fazendo uma reordenação pontual e não mantida.

---

## 6. [Sorting and Grouping](https://use-the-index-luke.com/sql/sorting-grouping)
Ordenar é caro e bloqueia o pipeline; um índice já guarda os dados pré-ordenados e pode eliminar a operação de sort.

- **[Indexing Order By](https://use-the-index-luke.com/sql/sorting-grouping/indexed-order-by)** — o mesmo índice que atende o WHERE precisa cobrir também o ORDER BY para que o sort desapareça do plano.
- **[ASC, DESC and NULLS FIRST/LAST](https://use-the-index-luke.com/sql/sorting-grouping/order-by-asc-desc-nulls-last)** — índices são lidos nos dois sentidos, mas misturar ASC e DESC (ou posição de NULLs divergente) exige criar o índice com os modificadores certos.
- **[Indexing Group By](https://use-the-index-luke.com/sql/sorting-grouping/indexed-group-by)** — o algoritmo sort/group pode aproveitar um índice e virar pipelined; o algoritmo hash não.

---

## 7. [Partial Results](https://use-the-index-luke.com/sql/partial-results)
Buscar só as primeiras linhas — o pipelined order by tem custo de partida baixíssimo e permite abortar cedo.

- **[Querying Top-N Rows](https://use-the-index-luke.com/sql/partial-results/top-n-queries)** — avise o banco que você não vai buscar todas as linhas (`FETCH FIRST`/`LIMIT`), senão o otimizador escolhe o plano errado.
- **[Paging Through Results](https://use-the-index-luke.com/sql/partial-results/fetch-next-page)** — o método *offset* é simples mas degrada com o número da página; o método *seek* (busca a partir da última linha da página anterior) é estável.
- **[Window Functions for Pagination](https://use-the-index-luke.com/sql/partial-results/window-functions)** — `ROW_NUMBER() OVER (...)` é a forma padronizada, mas só alguns bancos conseguem executá-la de forma pipelined.

---

## 8. [Modifying Data (Insert, Delete, Update)](https://use-the-index-luke.com/sql/dml)
O outro lado da moeda: índices são redundância que precisa ser mantida, então DML paga o preço da indexação.

- **[Insert](https://use-the-index-luke.com/sql/dml/insert)** — o número de índices na tabela é o fator dominante do custo do INSERT, que é a única operação que não se beneficia de índice algum.
- **[Delete](https://use-the-index-luke.com/sql/dml/delete)** — o DELETE usa índice para o seu WHERE (localizar é rápido), mas paga a remoção da entrada em cada índice.
- **[Update](https://use-the-index-luke.com/sql/dml/update)** — custo equivale a delete + insert, porém só nos índices que contêm as colunas efetivamente alteradas.

---

## Apêndice A — [Execution Plans](https://use-the-index-luke.com/sql/explain-plan)
Como obter e ler o plano de execução, que é o primeiro lugar a olhar diante de um comando lento. Cada banco tem três seções: **Getting** (como obter o plano), **Operations** (dicionário das operações) e **Access vs. filter predicates** (como distinguir os dois — a informação mais importante e a mais escondida).

### ★ [PostgreSQL](https://use-the-index-luke.com/sql/explain-plan/postgresql) — seção principal para este projeto

**[Getting an Execution Plan](https://use-the-index-luke.com/sql/explain-plan/postgresql/getting-an-execution-plan)** — como obter o plano:

- `EXPLAIN <query>` para SQL sem parâmetros; com bind parameters (`$1`) é preciso `PREPARE stmt(int) AS ...` e depois `EXPLAIN EXECUTE stmt(1)`, fechando com `DEALLOCATE stmt`.
- As opções mais úteis são `ANALYZE`, `BUFFERS` e `SETTINGS`: `EXPLAIN (ANALYZE, BUFFERS, SETTINGS) ...`.
- ⚠️ `EXPLAIN ANALYZE` **executa** o comando de verdade, inclusive INSERT/UPDATE/DELETE — envolva em `BEGIN ... ROLLBACK`.
- O custo vem em dois números (startup e total); o row count aparece tanto no estimado quanto no *actual*, o que permite achar rapidamente estimativas de cardinalidade erradas.
- Desde o 9.2 o plano é criado na execução, considerando os valores reais dos binds; o 16 introduziu a opção `generic_plan` para ver o plano genérico.

**[Operations](https://use-the-index-luke.com/sql/explain-plan/postgresql/operations)** — dicionário do plano:

| Operação | O que é |
|---|---|
| `Seq Scan` | lê a tabela inteira (equivale a TABLE ACCESS FULL). |
| `Index Scan` | travessia do B-Tree + varredura dos leaf nodes + acesso à tabela, tudo em uma operação. |
| `Index Only Scan` | não acessa a tabela porque o índice tem todas as colunas (exceto visibilidade MVCC). |
| `Bitmap Index Scan` / `Bitmap Heap Scan` / `Recheck Cond` | pega todos os ponteiros do índice de uma vez, ordena em um bitmap e visita a tabela em ordem física. |
| `Nested Loop` | consulta a segunda tabela para cada linha da primeira. |
| `Hash Join` / `Hash` | carrega um lado em hash table e sonda com o outro. |
| `Merge Join` | combina duas listas já ordenadas. |
| `Sort` / `Sort Key` | ordenação explícita, materializa tudo em memória (não é pipelined). |
| `GroupAggregate` | agrega conjunto já ordenado — é pipelined, o que se quer. |
| `HashAggregate` | agrupa via hash table, materializa e não devolve ordem alguma. |
| `Limit` | aborta as operações abaixo ao atingir N linhas — só é eficiente se o que está abaixo for pipelined. |
| `WindowAgg` | window function; do PG 15 em diante, `Run Condition` indica terminação Top-N. |

**[Access vs. Filter Predicates](https://use-the-index-luke.com/sql/explain-plan/postgresql/filter-predicates)** — o ponto mais importante e mais traiçoeiro no PostgreSQL:

- São **três** tipos de predicado: *access predicate* (início/fim da varredura), *index filter predicate* (aplicado durante a varredura, não a estreita) e *table level filter predicate* (coluna fora do índice, exige ler a linha da heap).
- ⚠️ O PostgreSQL mostra access predicate e index filter predicate **ambos como `Index Cond`** — não dá para distinguir pelo plano; é preciso comparar o `Index Cond` com a definição do índice.
- `Filter` no PostgreSQL é **sempre** filtro em nível de tabela, mesmo quando aparece dentro de um `Index Scan` (o acesso à tabela está embutido nessa operação).
- Index filter predicates dão falsa sensação de segurança: o índice "está sendo usado", mas a performance despenca conforme volume e carga crescem.

### Demais bancos (referência)

- **[Db2 (LUW)](https://use-the-index-luke.com/sql/explain-plan/db2)** — IXSCAN, FETCH, TBSCAN; distingue START/STOP de SARG.
- **[MySQL](https://use-the-index-luke.com/sql/explain-plan/mysql)** — coluna `type` (eq_ref, ref, range, index, ALL); o EXPLAIN dá falsa sensação de segurança.
- **[Oracle](https://use-the-index-luke.com/sql/explain-plan/oracle)** — INDEX UNIQUE/RANGE/FULL SCAN, TABLE ACCESS BY INDEX ROWID; separa `access` de `filter` (é o único que mostra isso com clareza).
- **[SQL Server](https://use-the-index-luke.com/sql/explain-plan/sql-server)** — Seek usa a árvore, Scan lê tudo; Key Lookup.
- **[SQLite](https://use-the-index-luke.com/sql/explain-plan/sqlite)** — SCAN/SEARCH TABLE, USING COVERING INDEX; só nested loops.
- **[Gupta SQLBase](https://use-the-index-luke.com/sql/explain-plan/sqlbase)** — plano pouco informativo.

---

## Apêndice B — [Myth Directory](https://use-the-index-luke.com/sql/myth-directory)
Mitos comuns de performance, desmontados um a um.

- **[Indexes Can Degenerate](https://use-the-index-luke.com/sql/myth-directory/indexes-can-degenerate)** — falso: a árvore é sempre balanceada, e rebuild periódico de índice rende de 0% a 2% num INDEX UNIQUE SCAN.
- **[Most Selective First](https://use-the-index-luke.com/sql/myth-directory/most-selective-first)** — falso: a ordem das colunas deve maximizar o número de queries atendidas, não a seletividade.
- **[Oracle Cannot Index NULL](https://use-the-index-luke.com/sql/myth-directory/null-cannot-be-indexed)** — falso: basta acrescentar ao índice uma coluna ou constante que nunca seja NULL.
- **[Dynamic SQL is Slow](https://use-the-index-luke.com/sql/myth-directory/dynamic-sql-is-slow)** — falso: SQL dinâmico com bind parameters é rápido; o que é lento é montar SQL por concatenação de literais.
- **Select \* is Bad** — listado no índice do apêndice, mas sem página publicada no site.

---

## Apêndice C — [Example Schema](https://use-the-index-luke.com/sql/example-schema)
Scripts de `CREATE`/`INSERT` (tabelas EMPLOYEES, SALES, SCALE_DATA) para reproduzir todos os exemplos do livro, por banco e por capítulo.

---

## Apêndice D — [Glossary](https://use-the-index-luke.com/sql/glossary)
Onze verbetes de terminologia de banco de dados.

- **[Execution Plan / Explain Plan / Query Plan](https://use-the-index-luke.com/sql/glossary/execution-plan-explain-plan)** — representação executável de um comando SQL, gerada pelo otimizador.
- **[Clustered Index / Non-Clustered Index](https://use-the-index-luke.com/sql/glossary/clustered-index)** — tabela armazenada na própria estrutura B-Tree (clustered), versus índice que aponta para outra estrutura (non-clustered).
- **[Index Clustering Factor](https://use-the-index-luke.com/sql/glossary/index-clustering-factor)** — métrica da correlação entre a ordem das linhas no índice e na tabela.
- **[Covering Index](https://use-the-index-luke.com/sql/glossary/covering-index)** — nome dado a um índice quando ele é usado em um index-only scan.
- **[Heap-Table](https://use-the-index-luke.com/sql/glossary/heap-table)** — tabela que guarda as linhas sem ordem alguma.
- **[Index Filter Predicates](https://use-the-index-luke.com/sql/glossary/index-filter-predicates)** — *access predicates* definem início e fim da varredura; *filter predicates* só descartam linhas durante a varredura, sem reduzi-la.
- **[Index-Only Scan](https://use-the-index-luke.com/sql/glossary/index-only-scan)** — varredura de índice sem acesso posterior à tabela.
- **[Index-Organized Table](https://use-the-index-luke.com/sql/glossary/index-organized-table)** — termo Oracle para tabela em B-Tree pela chave primária (`ORGANIZATION INDEX`).
- **[Optimizer / Query Planner](https://use-the-index-luke.com/sql/glossary/query-optimizer-query-planner)** — traduz SQL em plano de execução, por regras (RBO) ou por custo (CBO, o padrão atual).
- **[Parsing / Query Planning / Compiling](https://use-the-index-luke.com/sql/glossary/parsing-query-planning-compiling)** — *hard parse* constrói o plano do zero (caro); *soft parse* reaproveita um plano em cache (barato).
- **[Secondary Index](https://use-the-index-luke.com/sql/glossary/secondary-index)** — índice sobre um clustered index / IOT, ou seja, um índice sobre um índice.

---

## Notas específicas de PostgreSQL (extraídas ao longo do livro)

- **Índices sobre expressão** são suportados desde a 7.4 — é a solução para funções no WHERE (`CREATE INDEX ON t (upper(col))`), e a query precisa usar exatamente a mesma expressão.
- **Índices parciais** são nativos (`CREATE INDEX ... WHERE cond`) — o PostgreSQL é o banco de referência do livro nesse tópico.
- **Index-Only Scan** existe desde a 9.2, com a ressalva do MVCC: o PostgreSQL ainda pode precisar consultar a *visibility map*, então índice "coberto" nem sempre elimina 100% do acesso.
- **Sem clustered index / IOT**: toda tabela é heap; `CLUSTER` reordena uma vez e não mantém a ordem.
- **Bitmap Index/Heap Scan** é uma característica do PostgreSQL sem equivalente direto nos outros bancos do livro — surge quando muitos ponteiros são lidos de uma vez.
- **Type mismatch**: comparar coluna texto com número gera **erro** no PostgreSQL (em vez de cast implícito silencioso, como em outros bancos) — o problema aparece mais cedo.
- **Bind parameters** usam a sintaxe `$1`, `$2`; para dar `EXPLAIN` neles é preciso `PREPARE`/`EXECUTE`.
- **Paginação com window function** (`ROW_NUMBER()`) só executa de forma pipelined a partir do **PG 15**; antes disso, prefira `LIMIT`/`FETCH FIRST` com o método *seek*.
- **`GroupAggregate` vs. `HashAggregate`**: o primeiro indica que o índice eliminou a ordenação (pipelined) — é o alvo ao indexar `GROUP BY`.
- **Ferramenta de leitura de plano**: `EXPLAIN (ANALYZE, BUFFERS, SETTINGS)` dentro de `BEGIN ... ROLLBACK`, comparando *estimated* vs. *actual rows* para achar erro de cardinalidade.

---

## Regras práticas do livro (resumo transversal)

1. Índice não é responsabilidade do DBA — quem escreve a query define o caminho de acesso.
2. Nunca aplique função ou cálculo **sobre a coluna** no WHERE; transforme o parâmetro.
3. Em índice concatenado, a ordem das colunas manda: igualdades primeiro, range por último.
4. Mantenha a faixa varrida do índice a menor possível — cuidado com filter predicates.
5. Use bind parameters (segurança + reuso de plano).
6. Um índice concatenado costuma valer mais que vários índices de coluna única.
7. Indexe o dado original; padronize o caminho de acesso para reaproveitar índices.
8. Todo índice a mais encarece INSERT/UPDATE/DELETE — não indexe por indexar.
9. O plano de execução é a fonte da verdade; procure especificamente pelos predicates.
10. Teste com volume e carga realistas — problema de indexação só aparece na escala.
11. *(PostgreSQL)* `Index Cond` não distingue access de filter predicate — sempre confira contra a definição do índice.
