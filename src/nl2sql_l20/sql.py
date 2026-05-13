from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path
from typing import Any


SQL_START_RE = re.compile(r"\b(with|select|insert|update|delete|create)\b", re.IGNORECASE)
FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def extract_sql(text: str) -> str:
    text = text.strip()
    fenced = FENCE_RE.search(text)
    if fenced:
        text = fenced.group(1).strip()

    marker_match = re.search(r"\bSQL\s*:\s*", text, flags=re.IGNORECASE)
    if marker_match:
        text = text[marker_match.end() :].strip()

    start = SQL_START_RE.search(text)
    if start:
        text = text[start.start() :].strip()

    text = text.replace("<|im_end|>", "").replace("</s>", "").strip()
    text = re.split(r"\n\s*(?:Explanation|Reasoning|Answer)\s*:", text, flags=re.IGNORECASE)[0]

    semicolon = text.find(";")
    if semicolon != -1:
        text = text[: semicolon + 1]

    return text.strip()


def normalize_sql(sql: str) -> str:
    sql = extract_sql(sql)
    sql = re.sub(r"--.*?$", " ", sql, flags=re.MULTILINE)
    sql = sql.strip().rstrip(";").lower()
    sql = re.sub(r"\s+", " ", sql)
    sql = re.sub(r"\s*([(),=<>+\-*/])\s*", r"\1", sql)
    return sql.strip()


def has_order_by(sql: str) -> bool:
    return bool(re.search(r"\border\s+by\b", sql, flags=re.IGNORECASE))


def execute_sqlite(
    sql: str,
    db_path: str | Path,
    max_steps: int = 1_000_000,
    max_seconds: float = 8.0,
) -> tuple[bool, Any]:
    db_path = Path(db_path)
    if not db_path.exists():
        return False, f"database not found: {db_path}"

    counter = {"steps": 0}
    deadline = time.monotonic() + max_seconds if max_seconds > 0 else None

    def progress() -> int:
        counter["steps"] += 1
        if counter["steps"] > max_steps:
            return 1
        if deadline is not None and time.monotonic() > deadline:
            return 1
        return 0

    uri = f"file:{db_path}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.set_progress_handler(progress, 1000)
    try:
        cursor = connection.execute(sql)
        rows = cursor.fetchall()
        return True, rows
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        if message == "interrupted":
            message = f"interrupted after {counter['steps']} progress checks"
        return False, message
    finally:
        connection.close()


def normalize_result_rows(rows: list[tuple[Any, ...]], ordered: bool) -> list[tuple[str, ...]]:
    normalized = [tuple("" if value is None else str(value) for value in row) for row in rows]
    if ordered:
        return normalized
    return sorted(normalized)


def sqlite_execution_match(
    predicted_sql: str,
    gold_sql: str,
    db_path: str | Path,
) -> tuple[bool, str]:
    pred_ok, pred_result = execute_sqlite(predicted_sql, db_path)
    if not pred_ok:
        return False, f"prediction_error: {pred_result}"

    gold_ok, gold_result = execute_sqlite(gold_sql, db_path)
    if not gold_ok:
        return False, f"gold_error: {gold_result}"

    ordered = has_order_by(gold_sql)
    pred_rows = normalize_result_rows(pred_result, ordered=ordered)
    gold_rows = normalize_result_rows(gold_result, ordered=ordered)
    return pred_rows == gold_rows, ""
