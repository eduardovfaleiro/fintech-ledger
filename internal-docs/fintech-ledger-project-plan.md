# Fintech Ledger — Plano do Projeto (8 dias)

**Objetivo:** projeto de portfólio em PostgreSQL que demonstre, para recrutadores, capacidade de lidar com volumes grandes de dados de forma eficiente e escalável — aplicando os tópicos de [Use The Index, Luke!](https://use-the-index-luke.com/) (ver `sql-indexing-and-tuning-topics.md`).

**Perfil:** desenvolvedor (não DBA) mirando projetos maiores / multinacionais. O diferencial a provar é: gerir banco, fazer consultas eficientes e escaláveis com muitos dados.

---

## Por que este tema

O brainstorming considerou três conceitos:

1. **Ledger financeiro de grupo empresarial (consolidação de subsidiárias)** — cenário perfeito para o livro, mas exige entender de contabilidade/consolidação.
2. **Plataforma de M&A / deal flow** — tema atraente, mas volume natural de dados pequeno (deals são milhares, não milhões) e domínio complexo.
3. **Market data / carteira de investimentos** — volume real, mas puxa para time-series (TimescaleDB), fora do escopo do livro.

**Decisão: "Fintech ledger" (extrato bancário / carteira digital).** Motivos:

- Domínio que qualquer pessoa entende em 5 minutos (todo mundo tem app de banco) — o tema **não é gargalo**.
- Continua sendo "finanças", alinhado ao objetivo.
- A tabela de transações tem volume natural de milhões de linhas, append-only, sempre consultada por conta + período — exatamente o cenário que o livro resolve.

**Princípio de escopo:** o domínio é simplificado ao mínimo crível; a energia vai para dados, índices e documentação. O que dá peso ao projeto não é o schema, é o **volume** (50M+ transações) com distribuição desigual (1% das contas concentram ~60% do volume, como na vida real).

---

## Schema (3 tabelas, e só)

```
accounts        (id, customer_name, opened_at, status)
counterparties  (id, name)                       -- lojas/pessoas que recebem/pagam
transactions    (id, account_id, counterparty_id,
                 amount, direction, category,
                 created_at, status)             -- status: settled | pending | flagged
```

Sem câmbio, sem partida dobrada, sem auth, sem multi-tenant.

---

## Mapeamento feature → tópico do livro

| Feature (todo mundo entende) | Tópico do livro |
|---|---|
| Extrato: conta + período | Índice concatenado, equality antes de range |
| Saldo da conta (`SUM`) | Index-only scan / covering index |
| Scroll infinito do extrato | Seek pagination vs. offset (com benchmark da degradação) |
| Fila antifraude (`status = 'flagged'`) | **Partial index** — caso de manual do PostgreSQL |
| Busca de transação por nome da loja | `upper()` + índice de expressão, LIKE |
| "Top 10 maiores gastos do mês" | Top-N com pipelined order by |
| Gastos por categoria no mês | GroupAggregate vs. HashAggregate |
| Extrato com nome da contraparte | Join, N+1 do ORM e o fix |
| Import de 50M de linhas | Custo de índice em DML (insert com 1 vs. 5 índices) |

---

## O que convence o recrutador

Recrutador não lê schema. O portfólio de verdade é:

1. **Gerador de dados realista** — 50M+ transações, distribuição desigual. Sem isso, nada é demonstrável.
2. **`docs/` com estudos de caso antes/depois** — cada um com: query → plano ruim → índice criado → plano bom → números (*"extrato: 14,2s → 38ms"*). O código é coadjuvante.
3. **Benchmark de escalabilidade** — a mesma query em 1M / 10M / 50M de linhas, com gráfico.
4. **README que conta a história em 30 segundos** — "ledger que consulta X milhões de transações com p95 < Yms".

Todos os estudos de caso documentados com `EXPLAIN (ANALYZE, BUFFERS)`.

---

## Plano dia a dia (vertical)

**Regra:** cada dia fecha um estudo de caso completo. Se parar no dia 4, já existe portfólio. O que cresce com os dias é a quantidade de provas, não o esqueleto.

| Dia | Entrega | Detalhe |
|---|---|---|
| **D1** | Fundação | Docker compose (Postgres), schema, gerador de dados (10M em lote, parametrizável até 50M+), README com a promessa. Único dia sem estudo de caso. |
| **D2** | Caso 1 — Extrato | Query central (`account_id + created_at BETWEEN`). Seq Scan de segundos → índice `(account_id, created_at)` → ms. **A partir daqui o projeto já é mostrável.** |
| **D3** | Caso 2 — Saldo | `SUM(amount)` com covering index → Index Only Scan. Bônus: top-10 gastos (Limit pipelined). |
| **D4** | Caso 3 — Paginação | Offset degradando na página 10.000 vs. keyset estável. Gráfico. O caso que mais impressiona quem já sofreu com isso. |
| **D5** | Casos 4 e 5 — Fila antifraude + busca | Partial index (`WHERE status = 'flagged'`) + índice de expressão (`upper(name)`) com LIKE. Dois casos curtos no mesmo dia. |
| **D6** | Caso 6 — Joins/N+1 | Extrato com nome da loja: loop de queries (ORM naïve) vs. join único; nested loop vs. hash join no plano. |
| **D7** | Benchmark de escala | Query do extrato em 1M / 10M / 50M, tabela + gráfico. Prova o "volumes absurdos". |
| **D8** | Polimento | README final com tabela-resumo de todos os números, screenshots dos planos, revisão. |

---

## Cortes explícitos (não entram)

- **API/frontend** — o `docs/` com planos e números prova mais que uma API fina. Se sobrar tempo no D8: um endpoint de extrato com keyset pagination, no máximo.
- Multi-moeda, autenticação, transferência entre contas (consistência transacional é outro assunto).
- Particionamento — não é tema do livro e abre buraco de tempo.

**Se atrasar:** D6 e D7 são os sacrificáveis. D2–D5 cobrem os tópicos de maior impacto.

---

## Referências

- Mapa completo dos tópicos: `sql-indexing-and-tuning-topics.md` (mesmo diretório)
- Livro/site: https://use-the-index-luke.com/
- Seção PostgreSQL do Apêndice A (planos de execução): https://use-the-index-luke.com/sql/explain-plan/postgresql
