from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from nl2sql_l20.config import load_config, require
from nl2sql_l20.evaluate import evaluate_rows
from nl2sql_l20.export_spider import export_spider_files
from nl2sql_l20.io import read_jsonl, write_json


def load_suite(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def command_env() -> dict[str, str]:
    env = dict(os.environ)
    repo_root = Path(__file__).resolve().parents[2]
    src_path = str(repo_root / "src")
    current = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src_path if not current else src_path + os.pathsep + current
    return env


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    raise TypeError(f"Expected list or comma-separated string, got {type(value)!r}")


def should_skip_for_architecture(benchmark: dict[str, Any], experiment_architecture: str) -> bool:
    only = as_list(benchmark.get("only_architectures"))
    return bool(only and experiment_architecture not in only)


def default_path(output_dir: Path, benchmark_name: str, suffix: str) -> Path:
    return output_dir / benchmark_name / suffix


def jsonl_count(path: Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def run_command(command: list[str]) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, check=True, env=command_env())


def run_prediction(
    experiment_config: str,
    adapter: str,
    benchmark: dict[str, Any],
    experiment_architecture: str,
    pred_path: Path,
) -> None:
    mode = benchmark.get("mode", "infer")
    input_path = str(benchmark["input"])
    max_examples = benchmark.get("max_examples")
    expected_rows = int(max_examples) if max_examples is not None else jsonl_count(Path(input_path))
    if pred_path.exists():
        existing_rows = jsonl_count(pred_path)
        if existing_rows == expected_rows:
            print(f"Reusing complete predictions at {pred_path} ({existing_rows} rows)", flush=True)
            return
        print(
            f"Regenerating {pred_path}: found {existing_rows} rows, expected {expected_rows}",
            flush=True,
        )

    if mode == "infer":
        architecture = benchmark.get("architecture") or experiment_architecture
        command = [
            sys.executable,
            "-m",
            "nl2sql_l20.infer",
            "--config",
            experiment_config,
            "--input",
            input_path,
            "--output",
            str(pred_path),
            "--architecture",
            architecture,
        ]
        if adapter:
            command.extend(["--adapter", adapter])
        if max_examples is not None:
            command.extend(["--max-examples", str(max_examples)])
        run_command(command)
        return

    if mode == "pipeline":
        command = [
            sys.executable,
            "-m",
            "nl2sql_l20.pipeline",
            "--config",
            benchmark.get("pipeline_config") or experiment_config,
            "--input",
            input_path,
            "--output",
            str(pred_path),
        ]
        if adapter:
            command.extend(["--adapter", adapter])
        architectures = benchmark.get("architectures")
        if architectures:
            command.extend(["--architectures", ",".join(as_list(architectures))])
        if benchmark.get("samples_per_architecture") is not None:
            command.extend(
                ["--samples-per-architecture", str(benchmark["samples_per_architecture"])]
            )
        if benchmark.get("temperature") is not None:
            command.extend(["--temperature", str(benchmark["temperature"])])
        if benchmark.get("top_p") is not None:
            command.extend(["--top-p", str(benchmark["top_p"])])
        if benchmark.get("selection_strategy") is not None:
            command.extend(["--selection-strategy", str(benchmark["selection_strategy"])])
        if max_examples is not None:
            command.extend(["--max-examples", str(max_examples)])
        run_command(command)
        return

    raise ValueError(f"Unknown benchmark mode: {mode}")


def evaluate_prediction(
    benchmark: dict[str, Any],
    pred_path: Path,
    result_path: Path,
) -> dict[str, Any]:
    result = evaluate_rows(
        list(read_jsonl(benchmark["input"])),
        list(read_jsonl(pred_path)),
        execute=bool(benchmark.get("execute", True)),
    )
    write_json(result_path, result)
    return {key: value for key, value in result.items() if key != "details"}


def run_benchmark_suite(
    experiment_config: str,
    suite_path: str,
    adapter: str | None = None,
) -> dict[str, Any]:
    experiment = load_config(experiment_config)
    suite = load_suite(suite_path)
    experiment_name = require(experiment, "experiment.name")
    experiment_architecture = require(experiment, "experiment.architecture")
    adapter = (
        adapter
        if adapter is not None
        else experiment.get("training", {}).get("output_dir", "")
    )

    output_dir = Path(suite.get("output_dir", "evals/after_train")) / experiment_name
    output_dir.mkdir(parents=True, exist_ok=True)
    skip_missing = bool(suite.get("skip_missing", True))

    summary: dict[str, Any] = {
        "experiment": experiment_name,
        "architecture": experiment_architecture,
        "adapter": adapter,
        "suite": str(suite_path),
        "benchmarks": {},
    }

    for benchmark in suite.get("benchmarks", []):
        name = benchmark["name"]
        input_path = Path(benchmark["input"])
        if should_skip_for_architecture(benchmark, experiment_architecture):
            summary["benchmarks"][name] = {"status": "skipped_architecture"}
            continue
        if not input_path.exists():
            status = {"status": "skipped_missing_input", "input": str(input_path)}
            summary["benchmarks"][name] = status
            if skip_missing:
                print(f"Skipping {name}: missing {input_path}")
                continue
            raise FileNotFoundError(f"Missing benchmark input: {input_path}")

        pred_path = Path(
            benchmark.get("predictions")
            or default_path(output_dir, name, "predictions.jsonl")
        )
        result_path = Path(
            benchmark.get("results")
            or default_path(output_dir, name, "results.json")
        )
        pred_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.parent.mkdir(parents=True, exist_ok=True)

        run_prediction(
            experiment_config=experiment_config,
            adapter=adapter or "",
            benchmark=benchmark,
            experiment_architecture=experiment_architecture,
            pred_path=pred_path,
        )
        metrics = evaluate_prediction(benchmark, pred_path, result_path)
        benchmark_summary: dict[str, Any] = {
            "status": "completed",
            "input": str(input_path),
            "predictions": str(pred_path),
            "results": str(result_path),
            "metrics": metrics,
        }

        if benchmark.get("export_spider"):
            export_dir = Path(
                benchmark.get("spider_export_dir")
                or default_path(output_dir, name, "spider_official")
            )
            gold_path, official_pred_path = export_spider_files(
                input_path,
                pred_path,
                export_dir,
            )
            benchmark_summary["spider_official"] = {
                "gold": str(gold_path),
                "pred": str(official_pred_path),
            }

        summary["benchmarks"][name] = benchmark_summary

    summary_path = output_dir / "summary.json"
    write_json(summary_path, summary)
    print(f"Wrote benchmark summary to {summary_path}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run configured NL2SQL benchmark suite.")
    parser.add_argument("--experiment-config", required=True, help="Experiment YAML config.")
    parser.add_argument("--suite", required=True, help="Benchmark suite YAML.")
    parser.add_argument("--adapter", default=None, help="Adapter path. Defaults to training.output_dir.")
    args = parser.parse_args()

    run_benchmark_suite(args.experiment_config, args.suite, adapter=args.adapter)


if __name__ == "__main__":
    main()
