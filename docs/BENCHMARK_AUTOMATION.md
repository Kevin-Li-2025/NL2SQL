# Benchmark Automation

Training scripts run benchmarks automatically after saving the LoRA adapter.

Default suite:

```text
configs/benchmarks_after_train.yaml
```

Default output:

```text
evals/after_train/<experiment_name>/
  summary.json
  spider_dev/
    predictions.jsonl
    results.json
    spider_official/
      gold.txt
      pred.txt
```

## Default Benchmarks

The suite includes:

- `spider_dev`
- `spider_dev_mcr` for `rich_context` adapters
- `bird_mini_dev` if `data/processed/bird_mini_dev.jsonl` exists
- `bird_dev` if `data/processed/bird_dev.jsonl` exists
- `bird_dev_mcr` for `rich_context` adapters
- `livesqlbench_base_lite` if prepared into the common JSONL format

Missing inputs are skipped by default.

## Metrics

The local evaluator writes:

- prediction presence rate
- normalized exact match
- normalized exact count
- SQLite execution accuracy
- executable rate
- execution error rate
- schema hallucination rate
- missing prediction count
- per-example details

For Spider paper-grade reporting, use the generated `spider_official/gold.txt` and
`spider_official/pred.txt` with the official Spider evaluator.

## Controls

Disable post-train benchmarks:

```bash
RUN_BENCHMARKS=0 bash scripts/train_rich_context_l20.sh
```

Use a custom suite:

```bash
BENCHMARK_SUITE=configs/my_benchmarks.yaml bash scripts/train_rich_context_l20.sh
```

Run manually:

```bash
bash scripts/run_benchmarks_after_train.sh \
  configs/experiment_rich_context_spider.yaml \
  outputs/rich_context_spider_qwen25_coder_7b \
  configs/benchmarks_after_train.yaml
```
