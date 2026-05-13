from __future__ import annotations

import re

from nl2sql_l20.schema import DatabaseSchema


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def tokenize(text: str) -> set[str]:
    tokens = {token.lower() for token in TOKEN_RE.findall(text)}
    expanded = set(tokens)
    for token in tokens:
        if token.endswith("ies") and len(token) > 4:
            expanded.add(token[:-3] + "y")
        if token.endswith("s") and len(token) > 3:
            expanded.add(token[:-1])
    return expanded


def split_identifier(identifier: str) -> set[str]:
    return tokenize(identifier.replace("_", " "))


def link_schema(question: str, schema: DatabaseSchema, evidence: str = "") -> dict[str, list[str]]:
    question_tokens = tokenize(f"{question} {evidence}")
    table_hits: set[str] = set()
    column_hits: set[str] = set()

    for table in schema.tables:
        table_tokens = split_identifier(table)
        if table_tokens & question_tokens:
            table_hits.add(table)

    for column in schema.columns:
        column_tokens = split_identifier(column.name)
        full_name = f"{column.table}.{column.name}"
        if column_tokens & question_tokens:
            column_hits.add(full_name)
            table_hits.add(column.table)

    for fk in schema.foreign_keys:
        if fk.source_table in table_hits or fk.target_table in table_hits:
            table_hits.add(fk.source_table)
            table_hits.add(fk.target_table)

    return {
        "tables": sorted(table_hits),
        "columns": sorted(column_hits),
    }
