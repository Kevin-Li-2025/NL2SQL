# Benchmarks

## Spider 1.0

Spider is the first target because it is public, small enough to iterate on quickly, and
has an official evaluator.

Expected local layout after download:

```text
data/raw/spider/
  tables.json
  train_spider.json
  dev.json
  database/
```

Prepare:

```bash
bash scripts/prepare_spider.sh data/raw/spider
```

The train split is prepared without SQLite value hints for speed:

```text
data/processed/spider_train_no_value_hints.jsonl
```

The dev split keeps value hints for richer evaluation prompts:

```text
data/processed/spider_dev.jsonl
```

Official evaluation:

```bash
nl2sql-export-spider \
  --gold-jsonl data/processed/spider_dev.jsonl \
  --pred-jsonl evals/predictions.jsonl \
  --out-dir evals/spider_official
```

Then pass `gold.txt` and `pred.txt` to the official Spider `evaluation.py`.

## BIRD

BIRD is harder and more realistic because it uses larger real-world databases and
benchmark-provided evidence.

The prep command supports local BIRD-style folders:

```bash
nl2sql-prepare bird \
  --bird-dir data/raw/bird \
  --split dev \
  --out data/processed/bird_dev.jsonl
```

The adapter searches for common layouts such as:

```text
data/raw/bird/dev/dev.json
data/raw/bird/dev/dev_databases/
data/raw/bird/dev.json
data/raw/bird/dev_databases/
```

## Metrics

The built-in evaluator is intentionally lightweight:

- normalized exact match
- SQLite execution match when a local database path exists
- executable rate
- execution error rate
- schema hallucination rate

For paper-grade numbers, use official benchmark evaluators and report their exact metric
names.

The post-train automation is documented in [BENCHMARK_AUTOMATION.md](BENCHMARK_AUTOMATION.md).
