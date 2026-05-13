from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path

from nl2sql_l20.schema import DatabaseSchema, quote_sqlite_identifier
from nl2sql_l20.schema_linking import tokenize


def _is_searchable_type(dtype: str) -> bool:
    dtype = dtype.lower()
    return any(marker in dtype for marker in ("text", "char", "date", "time", "numeric", "int"))


def _format_value(value: object, max_length: int) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    return text[:max_length]


def collect_value_hints(
    db_path: str | Path,
    schema: DatabaseSchema,
    question: str,
    evidence: str = "",
    max_hints: int = 32,
    max_per_column: int = 3,
    max_value_length: int = 80,
) -> dict[str, list[str]]:
    db_path = Path(db_path)
    if not db_path.exists() or max_hints <= 0:
        return {}

    query_tokens = tokenize(f"{question} {evidence}")
    if not query_tokens:
        return {}

    hints: dict[str, list[str]] = defaultdict(list)
    uri = f"file:{db_path}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        for column in schema.columns:
            if len(hints) >= max_hints:
                break
            if not _is_searchable_type(column.dtype):
                continue

            full_name = f"{column.table}.{column.name}"
            table_sql = quote_sqlite_identifier(column.table)
            column_sql = quote_sqlite_identifier(column.name)
            for token in sorted(query_tokens, key=len, reverse=True):
                if len(token) < 3:
                    continue
                try:
                    rows = connection.execute(
                        f"SELECT DISTINCT {column_sql} FROM {table_sql} "
                        f"WHERE {column_sql} IS NOT NULL "
                        f"AND CAST({column_sql} AS TEXT) LIKE ? LIMIT 20",
                        (f"%{token}%",),
                    ).fetchall()
                except sqlite3.Error:
                    break

                for (value,) in rows:
                    text = _format_value(value, max_value_length)
                    if text and text not in hints[full_name]:
                        hints[full_name].append(text)
                    if len(hints[full_name]) >= max_per_column:
                        break
                if len(hints[full_name]) >= max_per_column:
                    break
    finally:
        connection.close()

    return dict(hints)
