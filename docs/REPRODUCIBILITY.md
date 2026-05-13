# Reproducibility

This repo is designed so a benchmark result can be traced from public data preparation to
training logs, generated SQL, evaluation JSON, and Spider official-evaluator export files.

## Environment

Recommended local setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[train,perf,dev]"
```

The completed L20 runs used:

- base model: `Qwen/Qwen2.5-Coder-7B-Instruct`;
- training method: BF16 LoRA;
- attention/kernel stack: PyTorch SDPA plus optional Liger kernels;
- hardware: one NVIDIA L20 GPU;
- MFU target: dense MFU above 0.60.

## Data Preparation

Spider:

```bash
bash scripts/prepare_spider.sh data/raw/spider
```

Expected processed files:

```text
data/processed/spider_train_no_value_hints.jsonl
data/processed/spider_dev.jsonl
```

Current prepared sizes:

| File | Rows |
| --- | ---: |
| `data/processed/spider_train_no_value_hints.jsonl` | 7,000 |
| `data/processed/spider_dev.jsonl` | 1,034 |

BIRD Mini-Dev:

```bash
bash scripts/prepare_bird.sh data/raw/bird_mini_dev/minidev/MINIDEV mini_dev
```

Expected processed file:

```text
data/processed/bird_mini_dev.jsonl
```

Current prepared size:

| File | Rows |
| --- | ---: |
| `data/processed/bird_mini_dev.jsonl` | 500 |

The raw benchmark data and database files are not committed. Download them from the
official benchmark sources.

## Training

Direct Spider LoRA:

```bash
bash scripts/train_direct_l20.sh
```

Schema-aware Spider LoRA:

```bash
bash scripts/train_schema_aware_l20.sh
```

Rich-context Spider LoRA:

```bash
bash scripts/train_rich_context_l20_mfu.sh
```

The high-throughput scripts write:

```text
outputs/<experiment_name>/perf.jsonl
outputs/<experiment_name>/perf.summary.json
```

Current checked-in MFU summaries:

| Experiment | Tail tokens/sec | Tail dense MFU | Target Met |
| --- | ---: | ---: | --- |
| `direct_spider_qwen25_coder_7b_l20_mfu` | 1725.46 | 0.6598 | yes |
| `rich_context_spider_qwen25_coder_7b_l20_mfu` | 1734.91 | 0.6634 | yes |

## Evaluation

Run the default post-train benchmark suite:

```bash
bash scripts/run_benchmarks_after_train.sh \
  configs/experiment_rich_context_spider_l20_mfu.yaml \
  outputs/rich_context_spider_qwen25_coder_7b_l20_mfu/checkpoint-96 \
  configs/benchmarks_after_train.yaml
```

Run MCR manually:

```bash
bash scripts/run_mcr_spider.sh \
  configs/pipeline_mcr_l20.yaml \
  outputs/rich_context_spider_qwen25_coder_7b_l20_mfu/checkpoint-96 \
  evals/after_train/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_mcr/predictions.jsonl \
  evals/after_train/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_mcr/results.json
```

The local evaluator reports:

- normalized exact match;
- SQLite execution accuracy;
- executable rate and execution error rate;
- schema hallucination rate;
- per-example details.

For official Spider evaluation, export the files and run the upstream evaluator:

```bash
nl2sql-export-spider \
  --gold-jsonl data/processed/spider_dev.jsonl \
  --pred-jsonl evals/after_train/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_mcr/predictions.jsonl \
  --out-dir evals/after_train/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_mcr/spider_official
```

Then run `evaluation.py` from `taoyds/spider` with the generated `gold.txt` and `pred.txt`.
Do not call a result an official Spider score until that evaluator output is checked in.

## Checked-In Result Artifacts

Current result artifacts are under:

```text
evals/after_train/direct_spider_qwen25_coder_7b_l20_mfu/
evals/after_train/rich_context_spider_qwen25_coder_7b_l20_mfu/
outputs/direct_spider_qwen25_coder_7b_l20_mfu/perf.summary.json
outputs/rich_context_spider_qwen25_coder_7b_l20_mfu/perf.summary.json
```

Each benchmark folder includes `predictions.jsonl` and `results.json`; Spider folders also
include `spider_official/gold.txt` and `spider_official/pred.txt`.

## Fair-Comparison Checklist

When adding a new headline number, record:

- base model and adapter path;
- benchmark split and example count;
- local evaluator or official evaluator;
- prompt context: full schema, schema subset, evidence, value hints, and retrieval source;
- candidate generations per example;
- whether training data changed;
- exact command used to produce predictions and metrics.
