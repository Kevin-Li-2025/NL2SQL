from __future__ import annotations

from typing import Any


DIRECT_SYSTEM = (
    "You are an expert text-to-SQL model. Generate one valid SQLite SQL query for the "
    "given question and database schema. Return only the SQL query."
)

SCHEMA_AWARE_SYSTEM = (
    "You are an expert text-to-SQL model. Use the relevant schema hints, full schema, "
    "foreign keys, and evidence to generate one valid SQLite SQL query. Prefer columns "
    "and tables that appear in the relevant schema hints, but fall back to the full schema "
    "when needed. Return only the SQL query."
)

RICH_CONTEXT_SYSTEM = (
    "You are an expert text-to-SQL model. Use the semi-structured schema, foreign keys, "
    "question-linked columns, evidence, and matched database values to generate one valid "
    "SQLite SQL query. Do not invent tables or columns. Return only the SQL query."
)

DECOMPOSE_SYSTEM = (
    "You are an expert text-to-SQL model. Internally decompose the question into SQL "
    "subgoals, identify joins, filters, aggregation, and ordering, then return only the "
    "final SQLite SQL query."
)

QUERY_PLAN_SYSTEM = (
    "You are an expert text-to-SQL model. Think like a database engine: identify the "
    "tables to scan, joins, predicates, grouping, ordering, and projection. Return only "
    "the final SQLite SQL query."
)

SKELETON_SYSTEM = (
    "You are an expert text-to-SQL model. Internally draft the SQL skeleton first, then "
    "fill schema items using only the provided schema. Return only the final SQLite SQL query."
)

EXECUTION_FIRST_SYSTEM = (
    "You are an expert text-to-SQL model optimizing for SQLite execution accuracy. Use only "
    "provided tables and columns, prefer the simplest query that answers the question, include "
    "GROUP BY for non-aggregated selected columns, and ground filters in matched values when "
    "available. Return only the final SQLite SQL query."
)

ARCHITECTURES = (
    "direct",
    "schema_aware",
    "rich_context",
    "decompose",
    "query_plan",
    "skeleton",
    "execution_first",
)


def _rich_user_content(row: dict[str, Any]) -> str:
    evidence = row.get("evidence") or "None"
    value_hints = row.get("value_hints") or {}
    value_lines = []
    for column, values in sorted(value_hints.items()):
        if values:
            value_lines.append(f"- {column}: " + " | ".join(values))
    if not value_lines:
        value_lines.append("None")

    return "\n\n".join(
        [
            f"Database: {row['db_id']}",
            f"Dialect: {row.get('dialect', 'sqlite')}",
            "Evidence:",
            evidence,
            "Matched database values:",
            "\n".join(value_lines),
            "M-Schema:",
            row.get("m_schema_text") or row.get("linked_schema_text") or row["schema_text"],
            "Question:",
            row["question"],
        ]
    )


def build_messages(row: dict[str, Any], architecture: str) -> list[dict[str, str]]:
    if architecture == "direct":
        return [
            {"role": "system", "content": DIRECT_SYSTEM},
            {
                "role": "user",
                "content": "\n\n".join(
                    [
                        f"Database: {row['db_id']}",
                        f"Dialect: {row.get('dialect', 'sqlite')}",
                        "Schema:",
                        row["schema_text"],
                        "Question:",
                        row["question"],
                    ]
                ),
            },
        ]

    if architecture == "schema_aware":
        evidence = row.get("evidence") or "None"
        return [
            {"role": "system", "content": SCHEMA_AWARE_SYSTEM},
            {
                "role": "user",
                "content": "\n\n".join(
                    [
                        f"Database: {row['db_id']}",
                        f"Dialect: {row.get('dialect', 'sqlite')}",
                        "Evidence:",
                        evidence,
                        "Schema with relevance hints:",
                        row.get("linked_schema_text") or row["schema_text"],
                        "Question:",
                        row["question"],
                    ]
                ),
            },
        ]

    if architecture == "rich_context":
        return [
            {"role": "system", "content": RICH_CONTEXT_SYSTEM},
            {"role": "user", "content": _rich_user_content(row)},
        ]

    if architecture == "decompose":
        return [
            {"role": "system", "content": DECOMPOSE_SYSTEM},
            {"role": "user", "content": _rich_user_content(row)},
        ]

    if architecture == "query_plan":
        return [
            {"role": "system", "content": QUERY_PLAN_SYSTEM},
            {"role": "user", "content": _rich_user_content(row)},
        ]

    if architecture == "skeleton":
        return [
            {"role": "system", "content": SKELETON_SYSTEM},
            {"role": "user", "content": _rich_user_content(row)},
        ]

    if architecture == "execution_first":
        return [
            {"role": "system", "content": EXECUTION_FIRST_SYSTEM},
            {"role": "user", "content": _rich_user_content(row)},
        ]

    raise ValueError(f"Unknown architecture: {architecture}")


def apply_chat_template(tokenizer: Any, messages: list[dict[str, str]], add_generation_prompt: bool) -> str:
    if getattr(tokenizer, "chat_template", None):
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=add_generation_prompt,
        )

    rendered = []
    for message in messages:
        role = message["role"].upper()
        rendered.append(f"{role}:\n{message['content']}")
    if add_generation_prompt:
        rendered.append("ASSISTANT:\n")
    return "\n\n".join(rendered)
