from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from nl2sql_l20.evaluate import evaluate_rows
from nl2sql_l20.export_spider import export_spider_files
from nl2sql_l20.io import read_jsonl, write_json, write_jsonl
from nl2sql_l20.pipeline import annotate_execution, select_candidate_by_strategy
from nl2sql_l20.sql import normalize_sql


def candidate_architectures(candidates: list[dict[str, Any]]) -> list[str]:
    architectures = []
    seen = set()
    for candidate in candidates:
        architecture = str(candidate.get("architecture") or "unknown")
        if architecture not in seen:
            seen.add(architecture)
            architectures.append(architecture)
    return architectures


def balanced_candidate_subset(
    candidates: list[dict[str, Any]],
    budget: int,
) -> list[dict[str, Any]]:
    if budget <= 0:
        raise ValueError("Candidate budget must be positive.")
    if len(candidates) <= budget:
        return [dict(candidate) for candidate in candidates]

    by_architecture: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        by_architecture.setdefault(str(candidate.get("architecture") or "unknown"), []).append(
            candidate
        )

    selected = []
    architectures = candidate_architectures(candidates)
    sample_index = 0
    while len(selected) < budget:
        added = False
        for architecture in architectures:
            architecture_candidates = by_architecture.get(architecture, [])
            if sample_index < len(architecture_candidates):
                selected.append(dict(architecture_candidates[sample_index]))
                added = True
                if len(selected) >= budget:
                    break
        if not added:
            break
        sample_index += 1
    return selected


def prefix_candidate_subset(
    candidates: list[dict[str, Any]],
    budget: int,
) -> list[dict[str, Any]]:
    if budget <= 0:
        raise ValueError("Candidate budget must be positive.")
    return [dict(candidate) for candidate in candidates[:budget]]


def candidate_subset(
    candidates: list[dict[str, Any]],
    budget: int,
    policy: str,
) -> list[dict[str, Any]]:
    if policy == "balanced":
        return balanced_candidate_subset(candidates, budget)
    if policy == "prefix":
        return prefix_candidate_subset(candidates, budget)
    raise ValueError(f"Unknown subset policy: {policy}")


def ensure_candidate_annotations(
    candidates: list[dict[str, Any]],
    row: dict[str, Any],
) -> list[dict[str, Any]]:
    annotated = []
    for candidate in candidates:
        candidate = dict(candidate)
        candidate.setdefault("normalized_prediction", normalize_sql(candidate.get("prediction", "")))
        if "executable" not in candidate or "result_signature" not in candidate:
            candidate = annotate_execution(candidate, row.get("db_path", ""))
        annotated.append(candidate)
    return annotated


def select_prediction_for_budget(
    row: dict[str, Any],
    prediction_row: dict[str, Any],
    budget: int,
    strategy: str,
    subset_policy: str,
    include_candidates: bool = False,
) -> dict[str, Any]:
    candidates = prediction_row.get("candidates") or []
    if not candidates:
        prediction = prediction_row.get("prediction") or prediction_row.get("sql") or ""
        return {
            "id": row["id"],
            "benchmark": row.get("benchmark", ""),
            "db_id": row["db_id"],
            "question": row["question"],
            "prediction": prediction,
            "candidate_budget": budget,
            "available_candidates": 0,
            "selection_strategy": "source_prediction",
        }

    subset = ensure_candidate_annotations(
        candidate_subset(candidates, budget=budget, policy=subset_policy),
        row,
    )
    selected = select_candidate_by_strategy(subset, strategy, row)
    output = {
        "id": row["id"],
        "benchmark": row.get("benchmark", ""),
        "db_id": row["db_id"],
        "question": row["question"],
        "prediction": selected.get("prediction", ""),
        "selected_architecture": selected.get("architecture", ""),
        "selected_sample_index": selected.get("sample_index", 0),
        "selection_strategy": strategy,
        "candidate_budget": budget,
        "available_candidates": len(candidates),
        "subset_policy": subset_policy,
    }
    if include_candidates:
        output["candidates"] = subset
    return output


def estimated_seconds(source_seconds: float | None, budget: int, source_budget: int) -> float | None:
    if source_seconds is None:
        return None
    return float(source_seconds) * float(budget) / float(source_budget)


def run_curve(
    gold_rows: list[dict[str, Any]],
    prediction_rows: list[dict[str, Any]],
    budgets: list[int],
    out_dir: Path,
    strategy: str,
    subset_policy: str,
    include_candidates: bool = False,
    export_spider: bool = False,
    source_budget: int | None = None,
    source_seconds: float | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    prediction_by_id = {row["id"]: row for row in prediction_rows}
    summary: dict[str, Any] = {
        "strategy": strategy,
        "subset_policy": subset_policy,
        "source_budget": source_budget,
        "source_seconds": source_seconds,
        "budgets": {},
    }
    gold_source = out_dir / "_gold_source.jsonl"
    if export_spider:
        write_jsonl(gold_source, gold_rows)

    for budget in budgets:
        budget_name = f"n{budget:02d}"
        budget_dir = out_dir / budget_name
        budget_dir.mkdir(parents=True, exist_ok=True)
        predictions = [
            select_prediction_for_budget(
                row=gold_row,
                prediction_row=prediction_by_id.get(gold_row["id"], {}),
                budget=budget,
                strategy=strategy,
                subset_policy=subset_policy,
                include_candidates=include_candidates,
            )
            for gold_row in gold_rows
        ]
        pred_path = budget_dir / "predictions.jsonl"
        result_path = budget_dir / "results.json"
        cost_path = budget_dir / "cost_summary.json"
        write_jsonl(pred_path, predictions)
        result = evaluate_rows(gold_rows, predictions, execute=True)
        write_json(result_path, result)
        cost_summary = {
            "candidate_budget": budget,
            "total_examples": len(gold_rows),
            "total_candidates": budget * len(gold_rows),
            "subset_policy": subset_policy,
            "selection_strategy": strategy,
            "estimated_wall_clock_seconds": estimated_seconds(
                source_seconds, budget, source_budget or budget
            ),
            "local_sqlite_execution_accuracy": result["execution_accuracy"],
            "local_normalized_exact": result["normalized_exact"],
            "executable_rate": result["executable_rate"],
            "execution_error_rate": result["execution_error_rate"],
            "schema_hallucination_rate": result["schema_hallucination_rate"],
        }
        write_json(cost_path, cost_summary)
        spider_paths = None
        if export_spider:
            gold_path, spider_pred_path = export_spider_files(
                gold_jsonl=gold_source,
                pred_jsonl=pred_path,
                out_dir=budget_dir / "spider_official",
            )
            spider_paths = {"gold": str(gold_path), "pred": str(spider_pred_path)}
        summary["budgets"][budget_name] = {
            "predictions": str(pred_path),
            "results": str(result_path),
            "cost_summary": str(cost_path),
            "spider_official": spider_paths,
            "metrics": {key: value for key, value in result.items() if key != "details"},
        }

    summary_path = out_dir / "summary.json"
    write_json(summary_path, summary)
    if export_spider:
        gold_source.unlink(missing_ok=True)
    return summary


def parse_budgets(value: str) -> list[int]:
    budgets = [int(part.strip()) for part in value.split(",") if part.strip()]
    if not budgets:
        raise ValueError("At least one budget is required.")
    return budgets


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a retrospective candidate-budget accuracy/cost curve."
    )
    parser.add_argument("--gold", required=True, help="Prepared benchmark JSONL.")
    parser.add_argument("--pred", required=True, help="Prediction JSONL with candidate lists.")
    parser.add_argument("--out-dir", required=True, help="Output directory for curve artifacts.")
    parser.add_argument("--budgets", default="4,8,12,16,30")
    parser.add_argument(
        "--selection-strategy",
        choices=("execution_consistency", "value_aware_voting", "execution_guided_rerank"),
        default="value_aware_voting",
    )
    parser.add_argument("--subset-policy", choices=("balanced", "prefix"), default="balanced")
    parser.add_argument("--include-candidates", action="store_true")
    parser.add_argument("--export-spider", action="store_true")
    parser.add_argument("--source-budget", type=int, default=None)
    parser.add_argument("--source-seconds", type=float, default=None)
    args = parser.parse_args()

    gold_rows = list(read_jsonl(args.gold))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    gold_source = out_dir / "_gold_source.jsonl"
    write_jsonl(gold_source, gold_rows)
    summary = run_curve(
        gold_rows=gold_rows,
        prediction_rows=list(read_jsonl(args.pred)),
        budgets=parse_budgets(args.budgets),
        out_dir=out_dir,
        strategy=args.selection_strategy,
        subset_policy=args.subset_policy,
        include_candidates=args.include_candidates,
        export_spider=args.export_spider,
        source_budget=args.source_budget,
        source_seconds=args.source_seconds,
    )
    print(f"Wrote cost curve to {out_dir / 'summary.json'}")
    for name, entry in summary["budgets"].items():
        metrics = entry["metrics"]
        print(
            f"{name}: EM={metrics['normalized_exact']:.4f} "
            f"EX={metrics['execution_accuracy']:.4f} "
            f"ERR={metrics['execution_error_rate']:.4f} "
            f"HALL={metrics['schema_hallucination_rate']:.4f}"
        )


if __name__ == "__main__":
    main()
