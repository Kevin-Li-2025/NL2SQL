# NL2SQL L20

Fine-tune and compare natural-language-to-SQL systems on public benchmarks using one
NVIDIA L20 GPU.

The first experiment keeps the base model fixed:

- Base model: `Qwen/Qwen2.5-Coder-7B-Instruct`
- Hardware target: 1x L20, QLoRA 4-bit training
- Benchmark target: Spider 1.0 first, BIRD / BIRD Mini-Dev next
- Comparison: same model and training data, different input architecture

## Why This Repo

The goal is not to publish another generic LoRA notebook. The goal is to build a
repeatable NL2SQL benchmark repo:

- public benchmark preparation
- direct vs schema-aware architecture comparison
- rich schema/value retrieval and multi-path inference
- QLoRA training configs sized for an L20
- inference output files
- normalized exact match and SQLite execution comparison
- export format for the official Spider evaluator

## Architectures

### `direct`

The model sees:

```text
Database
Dialect
Full schema
Question
```

This is the baseline.

### `schema_aware`

The model sees:

```text
Database
Dialect
Evidence
Relevant schema hints
Full schema with foreign keys
Question
```

The current schema linker is deliberately simple and reproducible. It matches question
tokens against table and column names, then expands through foreign keys. This gives us a
clean first comparison before adding learned retrieval or value linking.

### `rich_context`

The model sees an M-Schema style representation, matched database values, evidence, and
question-linked schema hints. This is the stronger training target for BIRD-style tasks.

### `MCR-SQL-L20`

The SOTA-oriented path is a multi-candidate pipeline using the same base model through
several prompt architectures:

```text
rich_context + decompose + query_plan + skeleton -> execution grouping -> selected SQL
```

See [docs/SOTA_ARCHITECTURE.md](docs/SOTA_ARCHITECTURE.md).

## Benchmarks

Recommended order:

1. Spider 1.0 for fast public reproducibility.
2. BIRD Mini-Dev for harder SQLite execution checks.
3. BIRD full dev when you have the database files locally.
4. LiveSQLBench later, because it is closer to current industrial workloads but needs a
   longer-context pipeline.

Official references:

- [Spider official site](https://yale-lily.github.io/spider)
- [Spider official GitHub evaluator](https://github.com/taoyds/spider)
- [BIRD official site](https://bird-bench.github.io/)
- [LiveSQLBench dataset card](https://huggingface.co/datasets/birdsql/livesqlbench-base-full-v1)
- [Qwen2.5-Coder model overview](https://qwen2.org/qwen2-5-coder/)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[train,dev]"
```

For the L20 utilization target, install the optional perf kernels on the CUDA machine:

```bash
pip install -e ".[train,perf,dev]"
```

## Prepare Spider

Download Spider 1.0 from the official site and unpack it under `data/raw/spider`, or pass
the unpacked path explicitly:

```bash
bash scripts/prepare_spider.sh data/raw/spider
```

This writes:

```text
data/processed/spider_train_no_value_hints.jsonl
data/processed/spider_dev.jsonl
```

## Train

Direct baseline:

```bash
bash scripts/train_direct_l20.sh
```

Schema-aware run:

```bash
bash scripts/train_schema_aware_l20.sh
```

Rich-context run:

```bash
bash scripts/train_rich_context_l20.sh
```

L20 high-throughput run with MFU logging:

```bash
bash scripts/probe_l20_mfu.sh
bash scripts/train_rich_context_l20_mfu.sh
```

The MFU logs are written under the experiment output directory as `perf.jsonl` and
`perf.summary.json`. See [docs/L20_MFU.md](docs/L20_MFU.md).

Deploy to the L20 server, upload project files and prepared Spider data, then start
probe + train + validation:

```bash
SSHPASS='your-password' bash scripts/deploy_l20_train_val.sh
```

The script defaults to `hhai@100.111.150.63:22` over Tailscale and
`/home/hhai/nl2sql-l20`.

Both scripts use QLoRA with LoRA on attention and MLP projection modules. The effective
batch size is `1 * 16 = 16` by default.

By default, the training scripts run [configs/benchmarks_after_train.yaml](configs/benchmarks_after_train.yaml)
after the adapter is saved. Missing benchmark JSONL files are skipped, so you can start
with Spider and add BIRD/LiveSQLBench later.

Disable the automatic benchmark stage:

```bash
RUN_BENCHMARKS=0 bash scripts/train_rich_context_l20.sh
```

Run the suite manually:

```bash
bash scripts/run_benchmarks_after_train.sh \
  configs/experiment_rich_context_spider.yaml \
  outputs/rich_context_spider_qwen25_coder_7b
```

## Infer And Evaluate

```bash
bash scripts/infer_eval_spider.sh \
  configs/experiment_schema_aware_spider.yaml \
  outputs/schema_aware_spider_qwen25_coder_7b \
  evals/schema_aware_spider_predictions.jsonl \
  evals/schema_aware_spider_results.json
```

The local evaluator reports:

- prediction presence rate
- normalized exact match
- SQLite execution accuracy when `db_path` exists
- executable rate and execution error rate
- schema hallucination rate
- missing predictions
- execution errors

For the official Spider evaluator:

```bash
nl2sql-export-spider \
  --gold-jsonl data/processed/spider_dev.jsonl \
  --pred-jsonl evals/schema_aware_spider_predictions.jsonl \
  --out-dir evals/spider_official
```

Then run `evaluation.py` from `taoyds/spider` with the generated `gold.txt` and `pred.txt`.

Multi-path pipeline:

```bash
bash scripts/run_mcr_spider.sh \
  configs/pipeline_mcr_l20.yaml \
  outputs/rich_context_spider_qwen25_coder_7b \
  evals/mcr_spider_predictions.jsonl \
  evals/mcr_spider_results.json
```

## Expected Repo Direction

The first meaningful result should be a table like this:

| Base model | Architecture | Benchmark | Normalized EM | Execution Acc |
| --- | --- | --- | ---: | ---: |
| Qwen2.5-Coder-7B-Instruct | direct | Spider dev | TBD | TBD |
| Qwen2.5-Coder-7B-Instruct | schema_aware | Spider dev | TBD | TBD |
| Qwen2.5-Coder-7B-Instruct | rich_context | Spider dev | 50.48% | 78.72% |
| Qwen2.5-Coder-7B-Instruct | direct | BIRD Mini-Dev | TBD | TBD |
| Qwen2.5-Coder-7B-Instruct | schema_aware | BIRD Mini-Dev | TBD | TBD |
| Qwen2.5-Coder-7B-Instruct | MCR-SQL-L20 | BIRD Mini-Dev | TBD | TBD |

After that, the next serious upgrades are value retrieval, learned schema linking,
self-consistency, and SQL repair. Those should be added as separate architectures so the
same base model comparison stays clean.
