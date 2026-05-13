# Inference Cost

This document records inference cost for the accuracy-oriented multi-candidate runs. It
keeps cost separate from training MFU because the bottlenecks are different: generation,
SQLite execution checks, candidate selection, and JSONL writing rather than backward-pass
throughput.

## VAV-SQL-L20 n=30

Run:

- Benchmark: Spider dev, 1,034 examples.
- Model: `Qwen2.5-Coder-7B-Instruct` with the rich-context Spider LoRA adapter.
- Prompt architectures: `rich_context`, `query_plan`, `skeleton`.
- Sampling: 10 samples per architecture, 30 candidates per example.
- Selector: `value_aware_voting`.
- Output: `evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_vav_n30`.

Measured cost from the remote L20 run:

| Metric | Value |
| --- | ---: |
| Examples | 1,034 |
| Candidates per example | 30 |
| Total candidates | 31,020 |
| Wall-clock runtime | 2:28:23 |
| Single-L20 GPU-hours | 2.47 |
| Seconds per example | 8.61 |
| Examples per minute | 6.97 |
| Candidates per second | 3.48 |

Accuracy from the same run:

| Evaluator | Metric | Value |
| --- | --- | ---: |
| Local SQLite evaluator | Execution accuracy | 82.11% |
| Local SQLite evaluator | Normalized string EM | 52.03% |
| Official Spider evaluator | Execution accuracy | 81.90% |
| Official Spider evaluator | Exact match | 78.50% |

The official Spider evaluator exact match is not the same metric as this repo's
normalized string exact match. The local EM is a strict normalized-string comparison; the
official metric parses SQL structure and reports Spider's component-aware exact match.

## Evidence

- Local metrics: `evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_vav_n30/results.json`
- Official Spider stdout: `evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_vav_n30/spider_official/evaluation_stdout.txt`
- Inference log: `logs/remote_l20_sota_spider_vav_20260513_192853.log`
- Machine-readable cost summary: `evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_vav_n30/cost_summary.json`

The runtime includes model generation, SQLite candidate execution annotation,
value-aware selection, and prediction JSONL writing. It excludes queue waiting time before
the VAV command started. Continuous power logging was not captured during the VAV command,
so this repo reports GPU-hours rather than energy in kWh for this run.
