# 05 — Busca de estabelecimentos: índice sobre expressão

Agora, vamos para o caso 5. Vamos fazer uma busca case-insensitive pelo nome de um estabelecimento.

**Cenário:** PostgreSQL 18.4, tabela `counterparties` com 5 mil linhas, busca pelo prefixo `Mercado Central` e cache quente.

| Cenário | Tempo | Blocos acessados | Tamanho do índice |
|---|---:|---:|---:|
| Sem índice | 1,175 ms | 64 | — |
| Índice comum em `name` | 1,206 ms | 64 | 88 kB |
| Índice em `upper(name)` | 0,036 ms | 20 | 88 kB |

## A consulta

Imagine uma busca em que o usuário pode escrever `Mercado Central`, `mercado central` ou `MERCADO CENTRAL`. Queremos que todas essas formas encontrem os mesmos estabelecimentos.

Para ignorar a diferença entre letras maiúsculas e minúsculas, podemos aplicar `upper()` tanto na coluna quanto no valor pesquisado. Como estamos buscando por um prefixo, adicionamos `%` somente no final:

```sql
select
    id,
    name
from
    counterparties
where
    upper(name) like upper('Mercado Central') || '%';
```

Essa consulta encontrou 21 estabelecimentos.

## Sem índice nenhum

Sem um índice, o banco precisa aplicar `upper()` no nome de cada estabelecimento e, depois, verificar se o resultado começa com `MERCADO CENTRAL`:

```text
QUERY PLAN
----------------------------------------------------------------------------------------------------------------
Seq Scan on counterparties  (cost=0.00..139.00 rows=25 width=28) (actual time=0.044..1.151 rows=21.00 loops=1)
  Filter: (upper(name) ~~ 'MERCADO CENTRAL%'::text)
  Rows Removed by Filter: 4979
  Buffers: shared hit=64
Planning Time: 0.021 ms
Execution Time: 1.175 ms
```

O `Seq Scan` percorreu as 5 mil linhas, descartou 4.979 e devolveu 21. Neste volume, 1,175 ms ainda é rápido. Entretanto, o custo vai crescer junto com a tabela, porque a busca precisa executar `upper()` linha por linha.

## O índice errado: `name`

Em um primeiro momento, talvez você pense em criar um índice diretamente na coluna `name`:

```sql
create index idx_counterparties_name
    on counterparties (name text_pattern_ops);
```

Repare que já incluímos o `text_pattern_ops` nesse índice. Assim, o problema que vamos isolar não é o uso do `like`, mas a função aplicada na coluna.

Entretanto, esse índice guarda o valor original de `name`, enquanto a consulta procura pelo resultado de `upper(name)`. Para o banco, são duas coisas diferentes.

Executando a consulta novamente:

```text
QUERY PLAN
----------------------------------------------------------------------------------------------------------------
Seq Scan on counterparties  (cost=0.00..139.00 rows=25 width=28) (actual time=0.062..1.200 rows=21.00 loops=1)
  Filter: (upper(name) ~~ 'MERCADO CENTRAL%'::text)
  Rows Removed by Filter: 4979
  Buffers: shared hit=64
Planning Time: 0.019 ms
Execution Time: 1.206 ms
```

Repare que o índice nem aparece no plano. O banco continua utilizando um `Seq Scan`, acessando os mesmos 64 blocos e descartando as mesmas 4.979 linhas.

O tempo de 1,206 ms contra 1,175 ms não significa que o índice deixou a consulta mais lenta. Como ele não foi utilizado, essa pequena diferença é apenas uma variação normal entre as execuções. Ainda assim, o índice ocupa 88 kB e adiciona custo às inserções e alterações de nome sem ajudar essa busca.

## O índice certo: `upper(name)`

Se a consulta busca pelo resultado de uma expressão, podemos indexar o resultado dessa mesma expressão:

```sql
create index idx_counterparties_upper_name
    on counterparties (upper(name) text_pattern_ops);
```

Agora, a B tree não armazena `Mercado Central`, `mercado central` e `MERCADO CENTRAL` de formas diferentes. Ela armazena o resultado de `upper(name)`, exatamente como ele aparece no `where` da consulta.

O `text_pattern_ops` é utilizado para que o índice consiga atender à busca prefixada com `like` mesmo com a collation `en_US.utf8` do banco.

Executando novamente:

```text
QUERY PLAN
-------------------------------------------------------------------------------------------------------------------------------------------
Bitmap Heap Scan on counterparties  (cost=4.54..52.83 rows=25 width=28) (actual time=0.012..0.028 rows=21.00 loops=1)
  Filter: (upper(name) ~~ 'MERCADO CENTRAL%'::text)
  Heap Blocks: exact=18
  Buffers: shared hit=20
  ->  Bitmap Index Scan on idx_counterparties_upper_name  (cost=0.00..4.53 rows=25 width=0) (actual time=0.005..0.005 rows=21.00 loops=1)
        Index Cond: ((upper(name) ~>=~ 'MERCADO CENTRAL'::text) AND (upper(name) ~<~ 'MERCADO CENTRAM'::text))
        Index Searches: 1
        Buffers: shared hit=2
Planning Time: 0.033 ms
Execution Time: 0.036 ms
```

Agora aparece um `Bitmap Index Scan`. O PostgreSQL transforma o prefixo em um range dentro da B tree: começa em `MERCADO CENTRAL` e para antes de `MERCADO CENTRAM`.

Depois de encontrar as 21 entradas no índice, o `Bitmap Heap Scan` acessa os 18 blocos da tabela que contêm esses estabelecimentos. Por isso, o plano ainda mostra o filtro com `like`: o range encontra os candidatos e o filtro confirma o padrão completo.

## Busca por prefixo

Existe um detalhe importante aqui: o índice só consegue delimitar a busca porque o texto começa com uma parte fixa.

```sql
-- consegue utilizar o prefixo como range no índice
where upper(name) like 'MERCADO CENTRAL%';

-- não possui um ponto conhecido para começar a travessia da B tree
where upper(name) like '%MERCADO CENTRAL%';
```

Com `%` no começo, o valor poderia estar em qualquer posição do texto. Nesse caso, uma B tree não resolve a busca. Seria necessário mudar o requisito para busca por prefixo ou utilizar outra estratégia, como um índice de trigramas.

## O que mudou

O problema não era simplesmente a ausência de um índice na coluna `name`. O problema era que a consulta não buscava por `name`, mas sim por `upper(name)`.

Com o índice comum, o PostgreSQL continuou lendo os 64 blocos da tabela e executando a função nas 5 mil linhas. Com o índice sobre a expressão, ele acessou 20 blocos e o tempo caiu de 1,175 ms para 0,036 ms, aproximadamente 33 vezes mais rápido.

Assim, se uma função faz parte do caminho de acesso da consulta, o índice precisa guardar o resultado dessa mesma função. Criar um índice na coluna original e esperar que o banco faça a associação sozinho não funciona.
