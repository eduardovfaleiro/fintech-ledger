import argparse

import numpy as np

from db_connection import get_connection

NAME_PREFIXES = [
    "Mercado", "Farmacia", "Loja", "Restaurante", "Padaria", "Posto",
    "Supermercado", "Livraria", "Oficina", "Clinica", "Academia", "Cafe",
    "Petshop", "Papelaria", "Otica",
]
NAME_CORES = [
    "Central", "Estrela", "Boa Vista", "Sao Jorge", "Ipanema", "Norte",
    "Sul", "Progresso", "Uniao", "Bom Preco", "Popular", "Aurora",
    "Horizonte", "Vitoria", "Primavera",
]
NAME_SUFFIXES = ["Ltda", "ME", "EIRELI", ""]


def generate_rows(count: int, rng: np.random.Generator):
    prefix_idx = rng.integers(0, len(NAME_PREFIXES), size=count)
    core_idx = rng.integers(0, len(NAME_CORES), size=count)
    suffix_idx = rng.integers(0, len(NAME_SUFFIXES), size=count)

    for i in range(count):
        parts = [NAME_PREFIXES[prefix_idx[i]], NAME_CORES[core_idx[i]]]
        suffix = NAME_SUFFIXES[suffix_idx[i]]
        if suffix:
            parts.append(suffix)
        yield (" ".join(parts),)


def main():
    parser = argparse.ArgumentParser(description="Popula a tabela counterparties.")
    parser.add_argument("--count", type=int, default=5_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)

    with get_connection() as conn:
        with conn.cursor() as cur:
            with cur.copy("COPY counterparties (name) FROM STDIN") as copy:
                for row in generate_rows(args.count, rng):
                    copy.write_row(row)
        conn.commit()

    print(f"counterparties: {args.count} linhas inseridas")


if __name__ == "__main__":
    main()
