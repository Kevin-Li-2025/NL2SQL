from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from nl2sql_l20.io import read_jsonl, write_json
from nl2sql_l20.sql import normalize_sql, sqlite_execution_match


CREATE_TABLE_RE = re.compile(r"\bCREATE\s+TABLE\s+([`\"\[]?)([A-Za-z_][A-Za-z0-9_]*)\1", re.I)
FROM_JOIN_RE = re.compile(
    r"\b(?:FROM|JOIN|UPDATE|INTO)\s+([`\"\[]?)([A-Za-z_][A-Za-z0-9_]*)\1"
    r"(?:\s+(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*))?",
    re.I,
)
QUALIFIED_COLUMN_RE = re.compile(
    r"([`\"\[]?)([A-Za-z_][A-Za-z0-9_]*)\1\s*\.\s*([`\"\[]?)([A-Za-z_][A-Za-z0-9_]*)\3"
)
SQL_RESERVED_WORDS = {
    "on",
    "where",
    "join",
    "left",
    "right",
    "inner",
    "outer",
    "group",
    "order",
    "limit",
    "having",
    "union",
    "intersect",
    "except",
    "select",
}


def safe_divide(numerator: int, denominator: int) -> float:
    return float(numerator / denominator) if denominator else 0.0


def schema_inventory(row: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    table_names: set[str] = set()
    column_names: set[str] = set()
    qualified_columns: set[str] = set()
    current_table = ""

    for line in (row.get("schema_text") or "").splitlines():
        table_match = CREATE_TABLE_RE.search(line)
        if table_match:
            current_table = table_match.group(2).lower()
            table_names.add(current_table)
            continue

        stripped = line.strip().rstrip(",")
        if not current_table or not stripped or stripped.startswith("--") or stripped == ");":
            continue
        column_name = stripped.split()[0].strip('`"[]')
        if not column_name or column_name.upper() in {"PRIMARY", "FOREIGN", "UNIQUE", "CONSTRAINT"}:
            continue
        column_name = column_name.lower()
        column_names.add(column_name)
        qualified_columns.add(f"{current_table}.{column_name}")

    return table_names, column_names, qualified_columns


def schema_violations(sql: str, row: dict[str, Any]) -> dict[str, list[str]]:
    table_names, _, qualified_columns = schema_inventory(row)
    normalized = normalize_sql(sql)
    predicted_tables: set[str] = set()
    aliases: dict[str, str] = {}
    for match in FROM_JOIN_RE.finditer(normalized):
        table = match.group(2).lower()
        alias = (match.group(3) or "").lower()
        predicted_tables.add(table)
        aliases[table] = table
        if alias and alias not in SQL_RESERVED_WORDS:
            aliases[alias] = table

    predicted_qualified_columns = set()
    for match in QUALIFIED_COLUMN_RE.finditer(normalized):
        qualifier = match.group(2).lower()
        column = match.group(4).lower()
        table = aliases.get(qualifier, qualifier)
        predicted_qualified_columns.add(f"{table}.{column}")
    return {
        "tables": sorted(predicted_tables - table_names),
        "qualified_columns": sorted(predicted_qualified_columns - qualified_columns),
    }


def evaluate_rows(
    gold_rows: list[dict[str, Any]],
    prediction_rows: list[dict[str, Any]],
    execute: bool,
) -> dict[str, Any]:
    gold_by_id = {row["id"]: row for row in gold_rows}
    pred_by_id = {row["id"]: row for row in prediction_rows}
    details = []

    normalized_exact = 0
    executable_total = 0
    execution_match = 0
    execution_errors = 0
    predicted_sql_present = 0
    executable_success = 0
    schema_hallucinations = 0

    for row_id, gold in gold_by_id.items():
        pred = pred_by_id.get(row_id, {})
        predicted_sql = pred.get("prediction") or pred.get("sql") or ""
        predicted_sql_present += int(bool(predicted_sql.strip()))
        gold_sql = gold["sql"]
        exact = normalize_sql(predicted_sql) == normalize_sql(gold_sql)
        normalized_exact += int(exact)
        hallucinations = schema_violations(predicted_sql, gold)
        has_schema_hallucination = bool(hallucinations["tables"] or hallucinations["qualified_columns"])
        schema_hallucinations += int(has_schema_hallucination)

        execution_ok = None
        execution_error = ""
        db_path = gold.get("db_path") or ""
        if execute and db_path:
            executable_total += 1
            execution_ok, execution_error = sqlite_execution_match(predicted_sql, gold_sql, db_path)
            execution_match += int(execution_ok)
            execution_errors += int(bool(execution_error))
            executable_success += int(not execution_error)

        details.append(
            {
                "id": row_id,
                "db_id": gold["db_id"],
                "normalized_exact": exact,
                "execution_match": execution_ok,
                "execution_error": execution_error,
                "schema_hallucination": has_schema_hallucination,
                "schema_violations": hallucinations,
                "gold": gold_sql,
                "prediction": predicted_sql,
            }
        )

    total = len(gold_by_id)
    return {
        "total": total,
        "predicted_sql_present_rate": safe_divide(predicted_sql_present, total),
        "normalized_exact": safe_divide(normalized_exact, total),
        "normalized_exact_count": normalized_exact,
        "execution_accuracy": safe_divide(execution_match, executable_total),
        "execution_evaluated": executable_total,
        "executable_rate": safe_divide(executable_success, executable_total),
        "execution_errors": execution_errors,
        "execution_error_rate": safe_divide(execution_errors, executable_total),
        "schema_hallucination_rate": safe_divide(schema_hallucinations, total),
        "schema_hallucination_count": schema_hallucinations,
        "missing_predictions": total - len(set(gold_by_id) & set(pred_by_id)),
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate NL2SQL predictions.")
    parser.add_argument("--gold", required=True, help="Prepared benchmark JSONL file.")
    parser.add_argument("--pred", required=True, help="Prediction JSONL file.")
    parser.add_argument("--out", default=None, help="Optional metrics JSON output path.")
    parser.add_argument("--execute", action="store_true", help="Run SQLite execution comparison.")
    args = parser.parse_args()

    result = evaluate_rows(list(read_jsonl(args.gold)), list(read_jsonl(args.pred)), args.execute)
    summary = {key: value for key, value in result.items() if key != "details"}
    print(summary)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        write_json(args.out, result)


if __name__ == "__main__":
    main()
