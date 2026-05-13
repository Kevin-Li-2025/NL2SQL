from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from nl2sql_l20.evaluate import schema_violations
from nl2sql_l20.io import read_jsonl, write_jsonl
from nl2sql_l20.pipeline import (
    annotate_execution,
    architecture_priority,
    candidate_counts,
    question_operator_score,
    value_hint_overlap,
)
from nl2sql_l20.sql import normalize_sql, sqlite_execution_match


def _one_line_sql(sql: str, max_chars: int) -> str:
    rendered = re.sub(r"\s+", " ", (sql or "").strip())
    if len(rendered) <= max_chars:
        return rendered
    return rendered[: max_chars - 3].rstrip() + "..."


def _short_text(text: str, max_chars: int = 180) -> str:
    rendered = re.sub(r"\s+", " ", (text or "").strip())
    if len(rendered) <= max_chars:
        return rendered
    return rendered[: max_chars - 3].rstrip() + "..."


def value_hint_text(row: dict[str, Any]) -> str:
    hints = row.get("value_hints") or {}
    lines = []
    for column, values in sorted(hints.items()):
        compact_values = [str(value) for value in (values or [])[:8]]
        if compact_values:
            lines.append(f"- {column}: " + " | ".join(compact_values))
    return "\n".join(lines) if lines else "None"


def prediction_candidates(prediction_row: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = prediction_row.get("candidates") or []
    if candidates:
        return [dict(candidate) for candidate in candidates]

    prediction = prediction_row.get("prediction") or prediction_row.get("sql") or ""
    if not prediction:
        return []
    return [
        {
            "architecture": prediction_row.get("selected_architecture") or "single_path",
            "sample_index": prediction_row.get("selected_sample_index", 0),
            "prediction": prediction,
            "normalized_prediction": normalize_sql(prediction),
            "raw_generation": prediction_row.get("raw_generation", ""),
        }
    ]


def _rank_tuple(candidate: dict[str, Any]) -> tuple[int, int, int, int, int, int, int, int, int]:
    executable_score = int(candidate.get("executable") is True)
    schema_clean_score = int(candidate.get("schema_violation_count", 1) == 0)
    non_degenerate_score = int(candidate.get("result_degenerate") is False)
    return (
        executable_score,
        schema_clean_score,
        -int(candidate.get("schema_violation_count") or 0),
        int(candidate.get("result_vote_count") or 0),
        int(candidate.get("sql_vote_count") or 0),
        int(candidate.get("operator_score") or 0),
        int(candidate.get("value_hint_overlap") or 0),
        non_degenerate_score,
        architecture_priority(candidate),
    )


def prepare_candidate_infos(
    row: dict[str, Any],
    prediction_row: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates = prediction_candidates(prediction_row)
    prepared = []
    for index, candidate in enumerate(candidates):
        candidate.setdefault("candidate_index", index)
        candidate.setdefault("sample_index", 0)
        candidate.setdefault("normalized_prediction", normalize_sql(candidate.get("prediction", "")))
        if "executable" not in candidate or "result_signature" not in candidate:
            candidate = annotate_execution(candidate, row.get("db_path", ""))

        violations = schema_violations(candidate.get("prediction", ""), row)
        candidate["schema_violations"] = violations
        candidate["schema_violation_count"] = len(violations["tables"]) + len(
            violations["qualified_columns"]
        )
        candidate["value_hint_overlap"] = value_hint_overlap(candidate, row)
        candidate["operator_score"] = question_operator_score(candidate, row)
        prepared.append(candidate)

    result_counts, sql_counts = candidate_counts(prepared)
    for candidate in prepared:
        candidate["result_vote_count"] = result_counts.get(candidate.get("result_signature", ""), 0)
        candidate["sql_vote_count"] = sql_counts.get(candidate.get("normalized_prediction", ""), 0)
        candidate["rank_score"] = list(_rank_tuple(candidate))
    return prepared


def sorted_candidate_infos(
    row: dict[str, Any],
    prediction_row: dict[str, Any],
    max_candidates: int,
) -> list[dict[str, Any]]:
    prepared = prepare_candidate_infos(row, prediction_row)
    prepared.sort(
        key=lambda candidate: (_rank_tuple(candidate), -int(candidate.get("candidate_index") or 0)),
        reverse=True,
    )
    return prepared[:max_candidates] if max_candidates > 0 else prepared


def format_candidate_context(candidates: list[dict[str, Any]], max_sql_chars: int = 900) -> str:
    lines = []
    for display_index, candidate in enumerate(candidates):
        executable = "yes" if candidate.get("executable") is True else "no"
        degenerate = "yes" if candidate.get("result_degenerate") is True else "no"
        row_count = candidate.get("result_row_count")
        row_count_text = "unknown" if row_count is None else str(row_count)
        architecture = candidate.get("architecture") or "unknown"
        sample_index = candidate.get("sample_index", 0)
        lines.append(
            " ".join(
                [
                    f"[{display_index}]",
                    f"source_index={candidate.get('candidate_index', display_index)}",
                    f"arch={architecture}",
                    f"sample={sample_index}",
                    f"exec={executable}",
                    f"rows={row_count_text}",
                    f"degenerate={degenerate}",
                    f"result_votes={candidate.get('result_vote_count', 0)}",
                    f"sql_votes={candidate.get('sql_vote_count', 0)}",
                    f"schema_violations={candidate.get('schema_violation_count', 0)}",
                    f"value_hits={candidate.get('value_hint_overlap', 0)}",
                    f"operator_hits={candidate.get('operator_score', 0)}",
                ]
            )
        )
        if candidate.get("execution_error"):
            lines.append(f"    error: {_short_text(str(candidate['execution_error']))}")
        lines.append(f"    sql: {_one_line_sql(candidate.get('prediction', ''), max_sql_chars)}")
    return "\n".join(lines)


def label_candidates_against_gold(
    row: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, int]:
    exact_count = 0
    execution_match_count = 0
    db_path = row.get("db_path") or ""
    for candidate in candidates:
        exact = normalize_sql(candidate.get("prediction", "")) == normalize_sql(row["sql"])
        candidate["normalized_exact"] = exact
        exact_count += int(exact)
        if db_path:
            match, error = sqlite_execution_match(candidate.get("prediction", ""), row["sql"], db_path)
            candidate["execution_matches_gold"] = match
            candidate["gold_execution_error"] = error
            execution_match_count += int(match)
    return {
        "candidate_normalized_exact_count": exact_count,
        "candidate_execution_match_count": execution_match_count,
    }


def build_repair_row(
    gold_row: dict[str, Any],
    prediction_row: dict[str, Any],
    max_candidates: int = 16,
    require_executable: bool = False,
    label_candidates: bool = False,
) -> dict[str, Any] | None:
    candidates = sorted_candidate_infos(gold_row, prediction_row, max_candidates=max_candidates)
    if not candidates:
        return None
    if require_executable and not any(candidate.get("executable") is True for candidate in candidates):
        return None

    label_summary = (
        label_candidates_against_gold(gold_row, candidates) if label_candidates else {}
    )
    output = dict(gold_row)
    output["candidate_context"] = format_candidate_context(candidates)
    output["value_hint_text"] = value_hint_text(gold_row)
    output["candidate_count"] = len(candidates)
    output["candidate_source_selection_strategy"] = prediction_row.get("selection_strategy", "")
    output["source_prediction"] = prediction_row.get("prediction", "")
    output["source_selected_architecture"] = prediction_row.get("selected_architecture", "")
    output.update(label_summary)
    return output


def build_repair_rows(
    gold_rows: list[dict[str, Any]],
    prediction_rows: list[dict[str, Any]],
    max_candidates: int = 16,
    max_examples: int | None = None,
    require_executable: bool = False,
    label_candidates: bool = False,
) -> list[dict[str, Any]]:
    predictions_by_id = {row["id"]: row for row in prediction_rows}
    repair_rows = []
    for gold_row in gold_rows:
        prediction_row = predictions_by_id.get(gold_row["id"])
        if not prediction_row:
            continue
        repair_row = build_repair_row(
            gold_row,
            prediction_row,
            max_candidates=max_candidates,
            require_executable=require_executable,
            label_candidates=label_candidates,
        )
        if repair_row is None:
            continue
        repair_rows.append(repair_row)
        if max_examples is not None and len(repair_rows) >= max_examples:
            break
    return repair_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build candidate-repair SFT rows.")
    parser.add_argument("--gold", required=True, help="Prepared JSONL with gold SQL.")
    parser.add_argument("--pred", required=True, help="Prediction JSONL with candidate lists.")
    parser.add_argument("--out", required=True, help="Output repair JSONL.")
    parser.add_argument("--max-candidates", type=int, default=16)
    parser.add_argument("--max-examples", type=int, default=None)
    parser.add_argument("--require-executable", action="store_true")
    parser.add_argument("--no-label-candidates", action="store_true")
    args = parser.parse_args()

    repair_rows = build_repair_rows(
        list(read_jsonl(args.gold)),
        list(read_jsonl(args.pred)),
        max_candidates=args.max_candidates,
        max_examples=args.max_examples,
        require_executable=args.require_executable,
        label_candidates=not args.no_label_candidates,
    )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    count = write_jsonl(args.out, repair_rows)
    executable_match_count = sum(
        int((row.get("candidate_execution_match_count") or 0) > 0) for row in repair_rows
    )
    print(
        "Built "
        f"{count} repair rows at {args.out}; "
        f"{executable_match_count} rows contain at least one execution-matching candidate."
    )


if __name__ == "__main__":
    main()
