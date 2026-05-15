from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path
from typing import Any

from tqdm.auto import tqdm

from nl2sql_l20.config import load_config, require
from nl2sql_l20.evaluate import schema_inventory, schema_violations
from nl2sql_l20.io import read_jsonl, write_jsonl
from nl2sql_l20.prompts import ARCHITECTURES, apply_chat_template, build_messages
from nl2sql_l20.sql import execute_sqlite, extract_sql, normalize_result_rows, normalize_sql


DEFAULT_ARCHITECTURES = ("rich_context", "decompose", "query_plan", "skeleton")
SQL_STRING_LITERAL_RE = re.compile(r"'((?:''|[^'])*)'|\"((?:\"\"|[^\"])*)\"")
SQL_NUMBER_LITERAL_RE = re.compile(r"(?<![A-Za-z_])[-+]?\d+(?:\.\d+)?(?![A-Za-z_])")


def _result_signature(rows: list[tuple[Any, ...]]) -> str:
    payload = repr(normalize_result_rows(rows, ordered=False)).encode("utf-8", errors="ignore")
    return hashlib.sha256(payload).hexdigest()[:16]


def generate_candidates(
    model: Any,
    tokenizer: Any,
    row: dict[str, Any],
    architecture: str,
    max_new_tokens: int,
    temperature: float,
    top_p: float,
    sample_count: int,
) -> list[dict[str, Any]]:
    prompt = apply_chat_template(
        tokenizer,
        build_messages(row, architecture),
        add_generation_prompt=True,
    )
    encoded = tokenizer(prompt, return_tensors="pt").to(model.device)
    generate_kwargs = {
        "max_new_tokens": max_new_tokens,
        "do_sample": temperature > 0,
        "top_p": top_p,
        "pad_token_id": tokenizer.pad_token_id,
        "eos_token_id": tokenizer.eos_token_id,
    }
    if temperature > 0:
        generate_kwargs["temperature"] = temperature
        generate_kwargs["num_return_sequences"] = sample_count

    import torch

    with torch.no_grad():
        output_ids = model.generate(**encoded, **generate_kwargs)

    candidates = []
    for sample_index, output in enumerate(output_ids[:sample_count]):
        generated = output[encoded["input_ids"].shape[1] :]
        raw_generation = tokenizer.decode(generated, skip_special_tokens=True).strip()
        prediction = extract_sql(raw_generation)
        candidates.append(
            {
                "architecture": architecture,
                "sample_index": sample_index,
                "prediction": prediction,
                "normalized_prediction": normalize_sql(prediction),
                "raw_generation": raw_generation,
            }
        )
    return candidates


def result_is_degenerate(rows: list[tuple[Any, ...]]) -> bool:
    if not rows:
        return True
    flattened = [value for row in rows for value in row]
    if not flattened:
        return True

    def is_zero_like(value: Any) -> bool:
        if value is None:
            return True
        text = str(value).strip().lower()
        if text in {"", "0", "0.0", "false", "none", "null"}:
            return True
        try:
            return float(text) == 0.0
        except ValueError:
            return False

    return all(is_zero_like(value) for value in flattened)


def annotate_execution(candidate: dict[str, Any], db_path: str) -> dict[str, Any]:
    if not db_path:
        candidate.update(
            {
                "executable": None,
                "execution_error": "",
                "result_signature": "",
                "result_row_count": None,
                "result_degenerate": None,
            }
        )
        return candidate

    ok, result = execute_sqlite(candidate["prediction"], db_path)
    if not ok:
        candidate.update(
            {
                "executable": False,
                "execution_error": str(result),
                "result_signature": "",
                "result_row_count": None,
                "result_degenerate": None,
            }
        )
        return candidate

    candidate.update(
        {
            "executable": True,
            "execution_error": "",
            "result_signature": _result_signature(result),
            "result_row_count": len(result),
            "result_degenerate": result_is_degenerate(result),
        }
    )
    return candidate


def candidate_counts(candidates: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, int]]:
    result_counts: dict[str, int] = {}
    sql_counts: dict[str, int] = {}
    for candidate in candidates:
        if candidate.get("result_signature"):
            result_counts[candidate["result_signature"]] = (
                result_counts.get(candidate["result_signature"], 0) + 1
            )
        if candidate.get("normalized_prediction"):
            sql_counts[candidate["normalized_prediction"]] = (
                sql_counts.get(candidate["normalized_prediction"], 0) + 1
            )
    return result_counts, sql_counts


def architecture_priority(candidate: dict[str, Any]) -> int:
    priorities = {
        "rich_context": 4,
        "decompose": 3,
        "query_plan": 2,
        "skeleton": 1,
        "execution_first": 5,
        "evidence_first": 5,
        "value_grounded": 5,
        "join_path": 4,
        "schema_aware": 0,
        "direct": 0,
    }
    return priorities.get(candidate.get("architecture", ""), 0)


def select_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    result_counts, sql_counts = candidate_counts(candidates)

    def score(candidate: dict[str, Any]) -> tuple[int, int, int, int]:
        executable_score = 1 if candidate.get("executable") is True else 0
        result_score = result_counts.get(candidate.get("result_signature", ""), 0)
        sql_score = sql_counts.get(candidate.get("normalized_prediction", ""), 0)
        priority_score = architecture_priority(candidate)
        return executable_score, result_score, sql_score, priority_score

    return max(candidates, key=score)


def select_candidate_value_aware(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    result_counts, sql_counts = candidate_counts(candidates)
    viable = [
        candidate
        for candidate in candidates
        if candidate.get("executable") is True
        and candidate.get("result_signature")
        and not candidate.get("result_degenerate")
    ]
    if not viable:
        return select_candidate(candidates)

    def score(candidate: dict[str, Any]) -> tuple[int, int, int, int, int]:
        result_score = result_counts.get(candidate.get("result_signature", ""), 0)
        sql_score = sql_counts.get(candidate.get("normalized_prediction", ""), 0)
        priority_score = architecture_priority(candidate)
        row_count = int(candidate.get("result_row_count") or 0)
        has_nonempty_sql = 1 if candidate.get("normalized_prediction") else 0
        return result_score, sql_score, priority_score, has_nonempty_sql, row_count

    return max(viable, key=score)


def schema_violation_count(candidate: dict[str, Any], row: dict[str, Any]) -> int:
    violations = schema_violations(candidate.get("prediction", ""), row)
    return len(violations["tables"]) + len(violations["qualified_columns"])


def value_hint_overlap(candidate: dict[str, Any], row: dict[str, Any]) -> int:
    prediction = (candidate.get("prediction") or "").lower()
    hints = row.get("value_hints") or {}
    matches = 0
    for values in hints.values():
        for value in values or []:
            text = str(value).strip().lower()
            if len(text) >= 2 and text in prediction:
                matches += 1
    return matches


def grounding_text(row: dict[str, Any]) -> str:
    parts = [str(row.get("question") or ""), str(row.get("evidence") or "")]
    hints = row.get("value_hints") or {}
    for values in hints.values():
        parts.extend(str(value) for value in values or [])
    return " ".join(parts).lower()


def sql_string_literals(sql: str) -> list[str]:
    literals = []
    for single, double in SQL_STRING_LITERAL_RE.findall(sql):
        literal = single if single else double
        literal = literal.replace("''", "'").replace('""', '"').strip().lower()
        if len(literal) >= 2:
            literals.append(literal)
    return literals


def sql_number_literals(sql: str) -> list[str]:
    numbers = []
    for match in SQL_NUMBER_LITERAL_RE.findall(sql):
        normalized = match.lstrip("+")
        try:
            value = float(normalized)
        except ValueError:
            continue
        if value in {0.0, 1.0}:
            continue
        numbers.append(normalized.lower())
    return numbers


def grounded_literal_stats(candidate: dict[str, Any], row: dict[str, Any]) -> tuple[int, int]:
    sql = candidate.get("prediction") or ""
    ground = grounding_text(row)
    grounded = 0
    ungrounded = 0
    for literal in sql_string_literals(sql):
        if literal in ground:
            grounded += 1
        else:
            ungrounded += 1
    for number in sql_number_literals(sql):
        if number in ground:
            grounded += 1
        else:
            ungrounded += 1
    return grounded, ungrounded


def word_present(text: str, token: str) -> bool:
    return bool(re.search(rf"\b{re.escape(token.lower())}\b", text.lower()))


def linked_schema_score(candidate: dict[str, Any], row: dict[str, Any]) -> tuple[int, int]:
    sql = candidate.get("normalized_prediction") or normalize_sql(candidate.get("prediction", ""))
    links = row.get("schema_links") or {}
    linked_tables = [str(table).lower() for table in links.get("tables") or []]
    linked_columns = [
        str(column).split(".")[-1].lower()
        for column in links.get("columns") or []
        if str(column).strip()
    ]
    table_score = sum(int(word_present(sql, table)) for table in linked_tables)
    column_score = sum(int(word_present(sql, column)) for column in linked_columns)
    return table_score, column_score


def unlinked_table_count(candidate: dict[str, Any], row: dict[str, Any]) -> int:
    links = row.get("schema_links") or {}
    linked_tables = {str(table).lower() for table in links.get("tables") or []}
    if not linked_tables:
        return 0
    table_names, _, _ = schema_inventory(row)
    sql = candidate.get("normalized_prediction") or normalize_sql(candidate.get("prediction", ""))
    used_tables = {table for table in table_names if word_present(sql, table)}
    return len(used_tables - linked_tables)


def bird_operator_score(candidate: dict[str, Any], row: dict[str, Any]) -> int:
    text = f"{row.get('question') or ''} {row.get('evidence') or ''}".lower()
    sql = (candidate.get("normalized_prediction") or "").lower()
    score = question_operator_score(candidate, row)

    if any(term in text for term in ("ratio", "percentage", "percent", "proportion", "rate")):
        score += int("/" in sql or "cast(" in sql or "*100" in sql or "* 100" in sql)
    if any(term in text for term in ("not ", "without", "except", "no ")) and not any(
        term in text for term in ("not null",)
    ):
        score += int(
            " not " in f" {sql} "
            or "!=" in sql
            or "<>" in sql
            or " except " in f" {sql} "
        )
    if "between" in text:
        score += int(" between " in f" {sql} " or (">=" in sql and "<=" in sql))
    if any(term in text for term in ("before", "after", "earlier", "later", "older", "newer")):
        score += int(any(op in sql for op in (">", "<", ">=", "<=")))
    if any(term in text for term in ("top ", "first ", "last ", "rank")):
        score += int(" order by " in f" {sql} " and " limit " in f" {sql} ")
    return score


def result_shape_score(candidate: dict[str, Any], row: dict[str, Any]) -> int:
    text = f"{row.get('question') or ''} {row.get('evidence') or ''}".lower()
    row_count = candidate.get("result_row_count")
    if row_count is None:
        return 0
    singular_terms = (
        "how many",
        "number of",
        "count of",
        "average",
        "mean",
        "total",
        "sum of",
        "ratio",
        "percentage",
        "maximum",
        "minimum",
        "highest",
        "lowest",
        "largest",
        "smallest",
    )
    list_terms = ("which", "what are", "list", "show all", "names of")
    if any(term in text for term in singular_terms):
        return int(int(row_count) == 1)
    if any(term in text for term in list_terms):
        return int(int(row_count) > 0)
    return 0


def select_candidate_bird_grounded(
    candidates: list[dict[str, Any]],
    row: dict[str, Any],
) -> dict[str, Any]:
    result_counts, sql_counts = candidate_counts(candidates)

    def score(candidate: dict[str, Any]) -> tuple[int, int, int, int, int, int, int, int, int, int]:
        violation_count = schema_violation_count(candidate, row)
        executable_score = 1 if candidate.get("executable") is True else 0
        schema_clean_score = 1 if violation_count == 0 else 0
        grounded_literals, ungrounded_literals = grounded_literal_stats(candidate, row)
        linked_tables, linked_columns = linked_schema_score(candidate, row)
        linked_score = linked_tables * 2 + linked_columns
        extra_tables = unlinked_table_count(candidate, row)
        operator_score = bird_operator_score(candidate, row)
        non_degenerate_score = 1 if candidate.get("result_degenerate") is False else 0
        shape_score = result_shape_score(candidate, row)
        result_score = result_counts.get(candidate.get("result_signature", ""), 0)
        sql_score = sql_counts.get(candidate.get("normalized_prediction", ""), 0)
        priority_score = architecture_priority(candidate)
        weighted = (
            10_000 * executable_score
            + 2_200 * non_degenerate_score
            + 1_800 * result_score
            + 700 * sql_score
            + 500 * schema_clean_score
            - 100 * violation_count
            + 120 * grounded_literals
            - 160 * ungrounded_literals
            + 80 * operator_score
            + 50 * linked_score
            - 60 * extra_tables
            + 40 * shape_score
            + 10 * priority_score
        )
        return (
            weighted,
            executable_score,
            schema_clean_score,
            -ungrounded_literals,
            operator_score,
            linked_score,
            result_score,
            sql_score,
            non_degenerate_score,
            priority_score,
        )

    return max(candidates, key=score)


def question_operator_score(candidate: dict[str, Any], row: dict[str, Any]) -> int:
    question = (row.get("question") or "").lower()
    sql = (candidate.get("normalized_prediction") or "").lower()
    score = 0
    if any(term in question for term in ("how many", "number of", "count of")):
        score += int("count(" in sql)
    if any(term in question for term in ("average", "avg", "mean")):
        score += int("avg(" in sql)
    if any(term in question for term in ("total", "sum of")):
        score += int("sum(" in sql)
    if any(term in question for term in ("maximum", "highest", "largest", "most")):
        score += int("max(" in sql or ("order by" in sql and "limit" in sql))
    if any(term in question for term in ("minimum", "lowest", "smallest", "least")):
        score += int("min(" in sql or ("order by" in sql and "limit" in sql))
    if any(term in question for term in ("different", "distinct", "unique")):
        score += int("distinct" in sql)
    return score


def select_candidate_execution_guided(
    candidates: list[dict[str, Any]],
    row: dict[str, Any],
) -> dict[str, Any]:
    result_counts, sql_counts = candidate_counts(candidates)

    def score(candidate: dict[str, Any]) -> tuple[int, int, int, int, int, int, int, int, int]:
        violation_count = schema_violation_count(candidate, row)
        executable_score = 1 if candidate.get("executable") is True else 0
        schema_clean_score = 1 if violation_count == 0 else 0
        result_score = result_counts.get(candidate.get("result_signature", ""), 0)
        sql_score = sql_counts.get(candidate.get("normalized_prediction", ""), 0)
        operator_score = question_operator_score(candidate, row)
        value_score = value_hint_overlap(candidate, row)
        non_degenerate_score = 1 if candidate.get("result_degenerate") is False else 0
        priority_score = architecture_priority(candidate)
        return (
            executable_score,
            schema_clean_score,
            -violation_count,
            result_score,
            sql_score,
            operator_score,
            value_score,
            non_degenerate_score,
            priority_score,
        )

    return max(candidates, key=score)


def select_candidate_by_strategy(
    candidates: list[dict[str, Any]],
    strategy: str,
    row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if strategy == "value_aware_voting":
        return select_candidate_value_aware(candidates)
    if strategy == "execution_consistency":
        return select_candidate(candidates)
    if strategy == "execution_guided_rerank":
        if row is None:
            raise ValueError("execution_guided_rerank requires the source row.")
        return select_candidate_execution_guided(candidates, row)
    if strategy == "bird_grounded_rerank":
        if row is None:
            raise ValueError("bird_grounded_rerank requires the source row.")
        return select_candidate_bird_grounded(candidates, row)
    raise ValueError(f"Unknown selection strategy: {strategy}")


def parse_architectures(value: str) -> list[str]:
    architectures = [part.strip() for part in value.split(",") if part.strip()]
    unknown = [name for name in architectures if name not in ARCHITECTURES]
    if unknown:
        raise ValueError(f"Unknown architectures: {', '.join(unknown)}")
    return architectures


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the multi-candidate NL2SQL pipeline.")
    parser.add_argument("--config", required=True, help="Experiment YAML config.")
    parser.add_argument("--input", required=True, help="Prepared JSONL file.")
    parser.add_argument("--output", required=True, help="Prediction JSONL path.")
    parser.add_argument("--adapter", default=None, help="Optional LoRA adapter path.")
    parser.add_argument(
        "--architectures",
        default=",".join(DEFAULT_ARCHITECTURES),
        help="Comma-separated prompt architectures.",
    )
    parser.add_argument("--samples-per-architecture", type=int, default=1)
    parser.add_argument("--temperature", type=float, default=0.35)
    parser.add_argument("--top-p", type=float, default=0.95)
    parser.add_argument(
        "--selection-strategy",
        choices=(
            "execution_consistency",
            "value_aware_voting",
            "execution_guided_rerank",
            "bird_grounded_rerank",
        ),
        default="execution_consistency",
    )
    parser.add_argument("--max-examples", type=int, default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    model_config = require(config, "model")
    generation = config.get("generation", {})
    architectures = parse_architectures(args.architectures)

    from peft import PeftModel

    from nl2sql_l20.modeling import load_causal_lm, load_tokenizer

    tokenizer = load_tokenizer(
        model_config["base_model"],
        trust_remote_code=bool(model_config.get("trust_remote_code", True)),
    )
    model = load_causal_lm(model_config)
    if args.adapter:
        model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()

    rows = list(read_jsonl(args.input))
    if args.max_examples is not None:
        rows = rows[: args.max_examples]

    predictions = []
    for row in tqdm(rows, desc="Running multi-path NL2SQL"):
        candidates = []
        for architecture in architectures:
            for candidate in generate_candidates(
                model=model,
                tokenizer=tokenizer,
                row=row,
                architecture=architecture,
                max_new_tokens=int(generation.get("max_new_tokens", 512)),
                temperature=args.temperature,
                top_p=args.top_p,
                sample_count=args.samples_per_architecture,
            ):
                candidates.append(annotate_execution(candidate, row.get("db_path", "")))

        selected = select_candidate_by_strategy(candidates, args.selection_strategy, row)
        predictions.append(
            {
                "id": row["id"],
                "benchmark": row.get("benchmark", ""),
                "db_id": row["db_id"],
                "question": row["question"],
                "prediction": selected["prediction"],
                "selected_architecture": selected["architecture"],
                "selected_sample_index": selected["sample_index"],
                "selection_strategy": args.selection_strategy,
                "candidates": candidates,
            }
        )

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    count = write_jsonl(args.output, predictions)
    print(f"Wrote {count} predictions to {args.output}")


if __name__ == "__main__":
    main()
