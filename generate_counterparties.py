import argparse

import numpy as np

from db_connection import get_connection

NAME_PREFIXES = [
    "Mercado",
    "Farmacia",
    "Loja",
    "Restaurante",
    "Padaria",
    "Posto",
    "Supermercado",
    "Livraria",
    "Oficina",
    "Clinica",
    "Academia",
    "Cafe",
    "Petshop",
    "Papelaria",
    "Otica",
]
NAME_CORES = [
    "Central",
    "Estrela",
    "Boa Vista",
    "Sao Jorge",
    "Ipanema",
    "Norte",
    "Sul",
    "Progresso",
    "Uniao",
    "Bom Preco",
    "Popular",
    "Aurora",
    "Horizonte",
    "Vitoria",
    "Primavera",
]
NAME_SUFFIXES = ["Ltda", "ME", "EIRELI", ""]
NAME_LOCATIONS = [
    "Centro",
    "Jardins",
    "Moema",
    "Pinheiros",
    "Santana",
    "Tatuape",
    "Lapa",
    "Bela Vista",
    "Liberdade",
    "Consolacao",
]

MAX_UNIQUE_NAMES = (
    len(NAME_PREFIXES) * len(NAME_CORES) * len(NAME_SUFFIXES) * len(NAME_LOCATIONS)
)


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def generate_rows(count: int, rng: np.random.Generator):
    if count > MAX_UNIQUE_NAMES:
        raise ValueError(
            f"count cannot exceed the {MAX_UNIQUE_NAMES} available unique names"
        )

    combinations = rng.choice(MAX_UNIQUE_NAMES, size=count, replace=False)
    shape = (
        len(NAME_PREFIXES),
        len(NAME_CORES),
        len(NAME_SUFFIXES),
        len(NAME_LOCATIONS),
    )

    for combination in combinations:
        prefix_idx, core_idx, suffix_idx, location_idx = np.unravel_index(
            int(combination), shape
        )
        parts = [NAME_PREFIXES[prefix_idx], NAME_CORES[core_idx]]
        suffix = NAME_SUFFIXES[suffix_idx]
        if suffix:
            parts.append(suffix)
        parts.append(f"- {NAME_LOCATIONS[location_idx]}")
        yield (" ".join(parts),)


def main():
    parser = argparse.ArgumentParser(description="Popula a tabela counterparties.")
    parser.add_argument("--count", type=positive_int, default=5_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)

    with get_connection() as conn:
        with (
            conn.cursor() as cur,
            cur.copy("COPY counterparties (name) FROM STDIN") as copy,
        ):
            for row in generate_rows(args.count, rng):
                copy.write_row(row)
        conn.commit()

    print(f"counterparties: {args.count} linhas inseridas")


if __name__ == "__main__":
    main()
