from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from tqdm.auto import tqdm

from nl2sql_l20.candidate_data import build_repair_row, prepare_candidate_infos
from nl2sql_l20.config import load_config, require
from nl2sql_l20.evaluate import schema_violations
from nl2sql_l20.io import read_jsonl, write_jsonl
from nl2sql_l20.pipeline import select_candidate_execution_guided
from nl2sql_l20.prompts import apply_chat_template, build_messages
from nl2sql_l20.sql import execute_sqlite, extract_sql


def repair_status(sql: str, row: dict[str, Any]) -> dict[str, Any]:
    violations = schema_violations(sql, row)
    schema_violation_count = len(violations["tables"]) + len(violations["qualified_columns"])
    executable = None
    execution_error = ""
    row_count = None
    db_path = row.get("db_path") or ""
    if db_path:
        ok, result = execute_sqlite(sql, db_path)
        executable = ok
        if ok:
            row_count = len(result)
        else:
            execution_error = str(result)
    return {
        "executable": executable,
        "execution_error": execution_error,
        "result_row_count": row_count,
        "schema_violations": violations,
        "schema_violation_count": schema_violation_count,
    }


def use_repair(sql: str, row: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    status = repair_status(sql, row)
    if not sql.strip():
        return False, status
    if status["schema_violation_count"] > 0:
        return False, status
    if status["executable"] is False:
        return False, status
    return True, status


def fallback_candidate(row: dict[str, Any], prediction_row: dict[str, Any]) -> dict[str, Any]:
    candidates = prepare_candidate_infos(row, prediction_row)
    if candidates:
        return select_candidate_execution_guided(candidates, row)
    return {
        "prediction": prediction_row.get("prediction", ""),
        "architecture": prediction_row.get("selected_architecture", "fallback"),
        "sample_index": prediction_row.get("selected_sample_index", 0),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run candidate-repair NL2SQL inference.")
    parser.add_argument("--config", required=True, help="Repair experiment YAML config.")
    parser.add_argument("--input", required=True, help="Prepared benchmark JSONL.")
    parser.add_argument("--candidates", required=True, help="Candidate prediction JSONL.")
    parser.add_argument("--output", required=True, help="Output prediction JSONL.")
    parser.add_argument("--adapter", required=True, help="Candidate-repair LoRA adapter path.")
    parser.add_argument("--max-candidates", type=int, default=16)
    parser.add_argument("--max-examples", type=int, default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    model_config = require(config, "model")
    generation = config.get("generation", {})

    import torch
    from peft import PeftModel

    from nl2sql_l20.modeling import load_causal_lm, load_tokenizer

    tokenizer = load_tokenizer(
        model_config["base_model"],
        trust_remote_code=bool(model_config.get("trust_remote_code", True)),
    )
    model = load_causal_lm(model_config)
    model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()

    rows = list(read_jsonl(args.input))
    if args.max_examples is not None:
        rows = rows[: args.max_examples]
    candidate_rows = {row["id"]: row for row in read_jsonl(args.candidates)}

    temperature = float(generation.get("temperature", 0.0))
    generate_kwargs = {
        "max_new_tokens": int(generation.get("max_new_tokens", 512)),
        "do_sample": temperature > 0,
        "top_p": float(generation.get("top_p", 1.0)),
        "pad_token_id": tokenizer.pad_token_id,
        "eos_token_id": tokenizer.eos_token_id,
    }
    if temperature > 0:
        generate_kwargs["temperature"] = temperature

    predictions = []
    for row in tqdm(rows, desc="Repairing SQL"):
        prediction_row = candidate_rows.get(row["id"], {})
        repair_row = build_repair_row(
            row,
            prediction_row,
            max_candidates=args.max_candidates,
            require_executable=False,
            label_candidates=False,
        )
        if repair_row is None:
            selected = fallback_candidate(row, prediction_row)
            predictions.append(
                {
                    "id": row["id"],
                    "benchmark": row.get("benchmark", ""),
                    "db_id": row["db_id"],
                    "question": row["question"],
                    "prediction": selected.get("prediction", ""),
                    "repair_used": False,
                    "fallback_reason": "missing_candidates",
                    "fallback_architecture": selected.get("architecture", ""),
                }
            )
            continue

        prompt = apply_chat_template(
            tokenizer,
            build_messages(repair_row, "candidate_repair"),
            add_generation_prompt=True,
        )
        encoded = tokenizer(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            output_ids = model.generate(**encoded, **generate_kwargs)
        generated = output_ids[0, encoded["input_ids"].shape[1] :]
        raw_generation = tokenizer.decode(generated, skip_special_tokens=True).strip()
        repaired_sql = extract_sql(raw_generation)
        repair_ok, status = use_repair(repaired_sql, row)
        fallback = fallback_candidate(row, prediction_row)
        final_sql = repaired_sql if repair_ok else fallback.get("prediction", "")

        predictions.append(
            {
                "id": row["id"],
                "benchmark": row.get("benchmark", ""),
                "db_id": row["db_id"],
                "question": row["question"],
                "prediction": final_sql,
                "repair_prediction": repaired_sql,
                "repair_used": repair_ok,
                "repair_status": status,
                "fallback_prediction": fallback.get("prediction", ""),
                "fallback_architecture": fallback.get("architecture", ""),
                "fallback_sample_index": fallback.get("sample_index", 0),
                "candidate_count": repair_row.get("candidate_count", 0),
                "raw_generation": raw_generation,
            }
        )

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    count = write_jsonl(args.output, predictions)
    used = sum(int(row.get("repair_used", False)) for row in predictions)
    print(f"Wrote {count} repaired predictions to {args.output}; repair used for {used} rows.")


if __name__ == "__main__":
    main()
