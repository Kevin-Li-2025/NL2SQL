from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nl2sql_l20.io import read_json


@dataclass(frozen=True)
class Column:
    table: str
    name: str
    dtype: str = "text"
    primary_key: bool = False


@dataclass(frozen=True)
class ForeignKey:
    source_table: str
    source_column: str
    target_table: str
    target_column: str


@dataclass(frozen=True)
class DatabaseSchema:
    db_id: str
    tables: list[str]
    columns: list[Column]
    foreign_keys: list[ForeignKey]


def _safe_type(dtype: Any) -> str:
    if not dtype:
        return "text"
    return str(dtype).lower().replace("number", "numeric")


def serialize_schema(schema: DatabaseSchema, linked: dict[str, list[str]] | None = None) -> str:
    linked = linked or {}
    lines: list[str] = []

    relevant_tables = set(linked.get("tables", []))
    relevant_columns = set(linked.get("columns", []))
    if relevant_tables or relevant_columns:
        lines.append("-- Relevant schema hints")
        if relevant_tables:
            lines.append("-- tables: " + ", ".join(sorted(relevant_tables)))
        if relevant_columns:
            lines.append("-- columns: " + ", ".join(sorted(relevant_columns)))
        lines.append("")

    for table in schema.tables:
        table_columns = [column for column in schema.columns if column.table == table]
        lines.append(f"CREATE TABLE {table} (")
        column_lines = []
        for column in table_columns:
            suffix = " PRIMARY KEY" if column.primary_key else ""
            column_lines.append(f"  {column.name} {column.dtype}{suffix}")
        lines.append(",\n".join(column_lines))
        lines.append(");")
        lines.append("")

    if schema.foreign_keys:
        lines.append("-- Foreign keys")
        for fk in schema.foreign_keys:
            lines.append(
                f"-- {fk.source_table}.{fk.source_column} -> "
                f"{fk.target_table}.{fk.target_column}"
            )

    return "\n".join(lines).strip()


def serialize_m_schema(
    schema: DatabaseSchema,
    linked: dict[str, list[str]] | None = None,
    value_hints: dict[str, list[str]] | None = None,
    max_examples_per_column: int = 3,
) -> str:
    linked = linked or {}
    value_hints = value_hints or {}
    linked_tables = set(linked.get("tables", []))
    linked_columns = set(linked.get("columns", []))

    lines = [f"<DB_ID>{schema.db_id}</DB_ID>"]
    for table in schema.tables:
        table_mark = " relevant=true" if table in linked_tables else ""
        lines.append(f"<TABLE name=\"{table}\"{table_mark}>")
        table_columns = [column for column in schema.columns if column.table == table]
        for column in table_columns:
            full_name = f"{column.table}.{column.name}"
            flags = []
            if column.primary_key:
                flags.append("primary_key")
            if full_name in linked_columns:
                flags.append("question_linked")
            examples = value_hints.get(full_name, [])[:max_examples_per_column]
            parts = [
                f"name={column.name}",
                f"type={column.dtype}",
            ]
            if flags:
                parts.append("flags=" + "|".join(flags))
            if examples:
                parts.append("examples=" + " | ".join(examples))
            lines.append("  <COLUMN " + "; ".join(parts) + " />")
        outgoing = [fk for fk in schema.foreign_keys if fk.source_table == table]
        for fk in outgoing:
            lines.append(
                "  <FOREIGN_KEY "
                f"{fk.source_column} -> {fk.target_table}.{fk.target_column} />"
            )
        lines.append("</TABLE>")

    return "\n".join(lines)


def load_spider_schemas(tables_json_path: str | Path) -> dict[str, DatabaseSchema]:
    rows = read_json(tables_json_path)
    schemas: dict[str, DatabaseSchema] = {}

    for row in rows:
        db_id = row["db_id"]
        table_names = row.get("table_names_original") or row.get("table_names")
        raw_columns = row.get("column_names_original") or row.get("column_names")
        column_types = row.get("column_types") or []
        primary_keys = set(row.get("primary_keys") or [])

        columns: list[Column] = []
        column_lookup: dict[int, tuple[str, str]] = {}
        for index, (table_index, column_name) in enumerate(raw_columns):
            if table_index < 0:
                continue
            table_name = table_names[table_index]
            dtype = _safe_type(column_types[index] if index < len(column_types) else "text")
            column = Column(
                table=table_name,
                name=column_name,
                dtype=dtype,
                primary_key=index in primary_keys,
            )
            columns.append(column)
            column_lookup[index] = (table_name, column_name)

        foreign_keys: list[ForeignKey] = []
        for source_index, target_index in row.get("foreign_keys") or []:
            if source_index in column_lookup and target_index in column_lookup:
                source_table, source_column = column_lookup[source_index]
                target_table, target_column = column_lookup[target_index]
                foreign_keys.append(
                    ForeignKey(
                        source_table=source_table,
                        source_column=source_column,
                        target_table=target_table,
                        target_column=target_column,
                    )
                )

        schemas[db_id] = DatabaseSchema(
            db_id=db_id,
            tables=list(table_names),
            columns=columns,
            foreign_keys=foreign_keys,
        )

    return schemas


def load_sqlite_schema(db_path: str | Path, db_id: str | None = None) -> DatabaseSchema:
    db_path = Path(db_path)
    uri = f"file:{db_path}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        cursor = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = [row[0] for row in cursor.fetchall()]
        columns: list[Column] = []
        foreign_keys: list[ForeignKey] = []

        for table in tables:
            table_info = connection.execute(f"PRAGMA table_info({quote_sqlite_identifier(table)})")
            for _, name, dtype, _, _, primary_key in table_info.fetchall():
                columns.append(
                    Column(
                        table=table,
                        name=name,
                        dtype=_safe_type(dtype),
                        primary_key=bool(primary_key),
                    )
                )

            fk_info = connection.execute(f"PRAGMA foreign_key_list({quote_sqlite_identifier(table)})")
            for _, _, target_table, source_column, target_column, *_ in fk_info.fetchall():
                foreign_keys.append(
                    ForeignKey(
                        source_table=table,
                        source_column=source_column,
                        target_table=target_table,
                        target_column=target_column,
                    )
                )
    finally:
        connection.close()

    return DatabaseSchema(
        db_id=db_id or db_path.stem,
        tables=tables,
        columns=columns,
        foreign_keys=foreign_keys,
    )


def quote_sqlite_identifier(identifier: str) -> str:
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


def find_sqlite_database(root: str | Path, db_id: str) -> Path | None:
    root = Path(root)
    candidates = [
        root / db_id / f"{db_id}.sqlite",
        root / db_id / f"{db_id}.db",
        root / f"{db_id}.sqlite",
        root / f"{db_id}.db",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    for suffix in ("*.sqlite", "*.db"):
        for candidate in root.rglob(suffix):
            if candidate.stem == db_id or candidate.parent.name == db_id:
                return candidate
    return None
