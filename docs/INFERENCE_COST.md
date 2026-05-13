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

## Retrospective Candidate-Budget Curve

The saved n=30 candidate pool can be re-selected with lower balanced candidate budgets.
This is not a fresh lower-budget generation run; it is a selector and cost analysis using
the same candidates already generated for the n=30 run. It answers a specific question:
how much of the final accuracy depends on seeing all 30 candidates?

Artifacts:

- `evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_vav_cost_curve/summary.json`
- `evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_vav_cost_curve/*/results.json`
- `evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_vav_cost_curve/*/spider_official/evaluation_stdout.txt`

Curve:

| Budget | Total candidates | Local EX | Official EX | Official EM | Estimated one-L20 wall-clock |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 4 | 4,136 | 82.59% | 82.20% | 78.10% | 19:47 |
| 8 | 8,272 | 82.30% | 82.00% | 78.60% | 39:34 |
| 12 | 12,408 | 82.21% | 82.00% | 78.10% | 59:21 |
| 16 | 16,544 | 82.30% | 82.00% | 78.40% | 1:19:08 |
| 30 | 31,020 | 82.11% | 81.90% | 78.50% | 2:28:23 |

The n=4 retrospective subset is the strongest Spider official execution result currently
checked in. The result is also a warning against brute-force scaling: after the selector
has diverse candidates, adding more samples can add plausible but wrong SQL and slightly
hurt execution accuracy. The next cost-aware direction is a learned selector that reaches
the n=4/n=8 band consistently without depending on a large candidate pool.

## EGS-SQL-L20 n=32

Run:

- Benchmark: Spider dev, 1,034 examples.
- Model: `Qwen2.5-Coder-7B-Instruct` with the rich-context Spider LoRA adapter.
- Prompt architectures: `rich_context`, `execution_first`, `query_plan`, `skeleton`.
- Sampling: 8 samples per architecture, 32 candidates per example.
- Selector: `execution_guided_rerank`.
- Output: `evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_egs_n32`.
- Machine-readable cost summary:
  `evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_egs_n32/cost_summary.json`.

Measured cost from the remote L20 run:

| Metric | Value |
| --- | ---: |
| Examples | 1,034 |
| Candidates per example | 32 |
| Total candidates | 33,088 |
| Wall-clock runtime | 2:54:16 |
| Single-L20 GPU-hours | 2.90 |
| Seconds per example | 10.11 |
| Examples per minute | 5.93 |
| Candidates per second | 3.16 |

Accuracy from the same run:

| Evaluator | Metric | Value |
| --- | --- | ---: |
| Local SQLite evaluator | Execution accuracy | 81.33% |
| Local SQLite evaluator | Normalized string EM | 51.06% |
| Official Spider evaluator | Execution accuracy | 82.00% |
| Official Spider evaluator | Exact match | 78.40% |

EGS improved safety metrics but not the top-line execution result. It reduced Spider dev
schema hallucinations to `2` while keeping execution errors at `4`, but it underperformed
both the full VAV n=30 run and the retrospective n=4 VAV subset. The result is useful
because it narrows the next optimization target: better learned selection or repair,
rather than more expensive hand-written execution-guided reranking.
