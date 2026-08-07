# Fintech Ledger

Projeto de portfólio em PostgreSQL para demonstrar indexação e tuning de queries em volumes grandes de dados (50M+ transações), aplicando os tópicos de [Use The Index, Luke!](https://use-the-index-luke.com/).

A ideia é simular um extrato bancário / carteira digital e, a partir de queries reais desse domínio, documentar estudos de caso: query lenta → plano de execução ruim → índice criado → plano bom → ganho medido.

## Estudos de caso

- [01 - Extrato: índice concatenado](docs/01-extrato-indice-concatenado.md)
