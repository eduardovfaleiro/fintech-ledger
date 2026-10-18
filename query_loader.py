from pathlib import Path

QUERY_DIRECTORY = Path(__file__).resolve().parent / "db" / "queries"


def load_query(name: str) -> str:
    """Load a versioned SQL query by its filename, without accepting paths."""
    path = Path(name)
    if path.name != name or path.suffix != ".sql":
        raise ValueError("query name must be a .sql filename")

    return (QUERY_DIRECTORY / name).read_text(encoding="utf-8")
