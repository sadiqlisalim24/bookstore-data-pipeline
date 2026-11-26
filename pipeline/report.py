"""sql/queries qovluğundakı sorğuları işə salıb nəticəni Markdown cədvəli kimi çap edir."""
from pipeline.config import SQL_DIR


def to_markdown(columns: list[str], rows: list[tuple]) -> str:
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join("" if v is None else str(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def run_queries(conn) -> str:
    parts = []
    with conn.cursor() as cur:
        for path in sorted((SQL_DIR / "queries").glob("*.sql")):
            cur.execute(path.read_text(encoding="utf-8"))
            columns = [d[0] for d in cur.description]
            parts.append(f"### {path.name}\n\n{to_markdown(columns, cur.fetchall())}\n")
    return "\n".join(parts)
