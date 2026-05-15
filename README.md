# NL2SQL L20

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Spider official EX](https://img.shields.io/badge/Spider_official_EX-82.20%25-brightgreen)
![BIRD fresh EX](https://img.shields.io/badge/BIRD_fresh_EX-47.80%25-yellowgreen)
![BIRD union EX](https://img.shields.io/badge/BIRD_union_EX-48.40%25-yellowgreen)
![L20 dense MFU](https://img.shields.io/badge/L20_dense_MFU-73.22%25-brightgreen)

Single-GPU natural-language-to-SQL fine-tuning and inference experiments using
`Qwen2.5-Coder-7B-Instruct`, Spider supervision, and Spider/BIRD evaluation.

## Status

Final experiment snapshot: `2026-05-15`.

The remote run queue has been stopped. No pretraining is active or planned for this
snapshot. The results below are saved local artifacts from LoRA fine-tuning and
test-time candidate selection experiments, not public leaderboard submissions.

## TL;DR

- Best Spider dev result: `82.20%` official execution accuracy from a retrospective
  n=4 value-aware voting subset of the saved n=30 candidate pool.
- Best fresh BIRD Mini-Dev result: `47.80%` execution accuracy from value-aware
  voting n=20 at temperature `0.9`.
- Best retrospective BIRD Mini-Dev union result: `48.40%` execution accuracy from
  seven saved candidate pools at an n=80 budget.
- Best L20 training efficiency: `73.22%` dense MFU for the schema-aware Spider LoRA
  probe, with `48.81%` LoRA-estimated MFU.
- Negative final ablations: candidate repair, temperature `0.92`, repeated
  temperature `0.9` pools, and value-grounded prompts did not beat the best fresh
  BIRD run, although several helped retrospective union selection.

## Contents

- [What This Repo Contains](#what-this-repo-contains)
- [System Overview](#system-overview)
- [Metrics](#metrics)
- [Headline Results](#headline-results)
- [Spider Dev Results](#spider-dev-results)
- [BIRD Mini-Dev Results](#bird-mini-dev-results)
- [BIRD Union Cost Curves](#bird-union-cost-curves)
- [Training Efficiency](#training-efficiency)
- [Reproduce](#reproduce)
- [Repository Map](#repository-map)
- [Result Interpretation](#result-interpretation)
- [References](#references)

## What This Repo Contains

This repository is a compact research-engineering workspace for:

- preparing Spider and BIRD-style text-to-SQL JSONL data;
- training LoRA adapters for direct, schema-aware, rich-context, and repair variants;
- generating SQL candidates with direct decoding, multi-candidate reranking, execution
  guided selection, and value-aware voting;
- evaluating saved predictions with local execution metrics and Spider official exports;
- running retrospective cost curves over saved candidate pools.

The project is intentionally scoped to one NVIDIA L20. It is useful for measuring how
far careful prompting, schema hints, value-aware voting, and candidate-pool selection can
move a Spider-trained 7B model without a larger pretraining phase.

## System Overview

```mermaid
flowchart LR
    A["Question + database"] --> B["Schema linking, FK expansion, value hints"]
    B --> C["Prompt families: direct, schema-aware, rich-context"]
    C --> D["Candidate generation: direct, MCR, VAV, EGS"]
    D --> E["SQLite execution and schema checks"]
    E --> F["Voting, reranking, repair, cost curves"]
    F --> G["Final SQL"]
    G --> H["Local metrics and Spider official export"]
```

## Metrics

- `EX` is execution accuracy and is the primary metric for BIRD Mini-Dev in this repo.
- `EM` is strict local normalized exact match unless the column says `Official EM`.
- Spider official `Exact Match` is the upstream parsed structure-level metric and should
  not be compared directly with local normalized EM.
- `Err` is execution-error rate. `Hall` is schema hallucination rate.
- BIRD Mini-Dev uses 500 examples. Spider dev uses 1,034 examples.
- BIRD results are out-of-domain transfer from Spider-trained adapters and are not BIRD
  leaderboard submissions.

## Headline Results

| Track | Best run | Candidates | Main metric | Artifact |
| --- | --- | ---: | ---: | --- |
| Spider dev | VAV cost curve n=4 | 4 | `82.20%` official EX | [stdout](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_vav_cost_curve/n04/spider_official/evaluation_stdout.txt) |
| Spider dev | VAV full pool n=30 | 30 | `82.11%` local EX / `81.90%` official EX | [results](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_vav_n30/results.json) |
| Spider dev | EGS n=32 | 32 | `82.00%` official EX | [stdout](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_egs_n32/spider_official/evaluation_stdout.txt) |
| BIRD Mini-Dev | VAV n=20, temp 0.9 | 20 | `47.80%` EX | [results](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev_vav_n20_t09/results.json) |
| BIRD Mini-Dev | Seven-pool VAV union n=80 | 80 | `48.40%` EX | [summary](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev_vav_n140_union_t075_t10_t09_t085_t092_t09b_t09c_cost_curve_vav/summary.json) |
| Training | schema-aware Spider LoRA | - | `73.22%` dense MFU | [perf](outputs/schema_aware_spider_qwen25_coder_7b_l20_mfu/perf.summary.json) |

## Spider Dev Results

| Run | Candidates | Local EM | Local EX | Official EM | Official EX | Err | Hall | Artifact |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Direct | 1 | 48.94% | 75.73% | - | - | 5.32% | 4.74% | [results](evals/after_train/direct_spider_qwen25_coder_7b_l20_mfu/spider_dev/results.json) |
| Schema-aware | 1 | 48.65% | 76.40% | - | - | 4.74% | 3.77% | [results](evals/after_train/schema_aware_spider_qwen25_coder_7b_l20_mfu/spider_dev/results.json) |
| Rich-context | 1 | 50.48% | 78.72% | - | - | 4.84% | 3.87% | [results](evals/after_train/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev/results.json) |
| MCR | 8 | 51.06% | 80.37% | - | - | 1.93% | 1.74% | [results](evals/after_train/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_mcr/results.json) |
| VAV full pool | 30 | 52.03% | 82.11% | 78.50% | 81.90% | 0.39% | 0.58% | [results](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_vav_n30/results.json) |
| VAV cost curve | 4 | 50.39% | 82.59% | 78.10% | 82.20% | 0.97% | 0.97% | [summary](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_vav_cost_curve/summary.json) |
| EGS | 32 | 51.06% | 81.33% | 78.40% | 82.00% | 0.39% | 0.19% | [results](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_egs_n32/results.json) |
| Candidate repair | repaired | 50.10% | 81.14% | - | - | 0.39% | 0.19% | [results](evals/sota/candidate_repair_spider_qwen25_coder_7b_l20_mfu/spider_dev_repair/results.json) |

Official Spider detail for the best n=4 run:

| Difficulty | Official EX |
| --- | ---: |
| Easy | 91.50% |
| Medium | 86.30% |
| Hard | 74.10% |
| Extra | 65.70% |
| All | 82.20% |

## BIRD Mini-Dev Results

### Single Pool Runs

| Run | Candidates / temp | EM | EX | Err | Hall | Artifact |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Direct | 1 | 0.80% | 21.60% | 20.00% | 12.40% | [results](evals/after_train/direct_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev/results.json) |
| Schema-aware | 1 | 1.20% | 37.40% | 15.00% | 8.40% | [results](evals/after_train/schema_aware_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev/results.json) |
| Rich-context | 1 | 0.60% | 37.20% | 16.60% | 10.80% | [results](evals/after_train/rich_context_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev/results.json) |
| MCR | 8 | 0.60% | 39.20% | 6.80% | 4.80% | [results](evals/after_train/rich_context_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev_mcr/results.json) |
| Candidate repair baseline | repaired | 1.20% | 42.20% | 4.40% | 2.40% | [results](evals/sota/candidate_repair_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev_repair/results.json) |
| EGS | n=16 | 0.80% | 41.40% | 2.00% | 1.20% | [results](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev_egs_n16/results.json) |
| VAV | n=12 | 1.80% | 45.40% | 2.20% | 2.00% | [results](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev_vav_n12/results.json) |
| VAV | n=16 | 1.00% | 46.40% | 1.80% | 1.60% | [results](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev_vav_n16/results.json) |
| VAV | n=20 default | 0.60% | 46.80% | 2.00% | 1.60% | [results](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev_vav_n20/results.json) |
| Candidate repair on VAV20 | max 16 repaired | 1.20% | 43.60% | 1.60% | 1.00% | [results](evals/sota/candidate_repair_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev_repair_vav20/results.json) |
| VAV | n=20, temp 1.0 | 1.20% | 46.40% | 1.80% | 1.80% | [results](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev_vav_n20_t10/results.json) |
| VAV | n=20, temp 0.9 | 0.80% | 47.80% | 1.60% | 1.40% | [results](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev_vav_n20_t09/results.json) |
| VAV | n=20, temp 0.85 | 1.00% | 47.20% | 2.00% | 2.20% | [results](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev_vav_n20_t085/results.json) |
| VAV | n=20, temp 0.92 | 1.00% | 45.00% | 2.00% | 2.00% | [results](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev_vav_n20_t092/results.json) |
| VAV repeat | n=20, temp 0.9b | 0.80% | 45.60% | 2.20% | 1.60% | [results](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev_vav_n20_t09b/results.json) |
| VAV repeat | n=20, temp 0.9c | 1.20% | 45.20% | 2.40% | 2.60% | [results](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev_vav_n20_t09c/results.json) |
| Value-grounded VAV | n=20, temp 0.9 | 1.00% | 45.20% | 2.60% | 2.40% | [results](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev_value_grounded_n20_t09/results.json) |

### Best Fresh BIRD Run

The best fresh, non-retrospective BIRD Mini-Dev run is:

```text
evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev_vav_n20_t09/results.json
EX:   47.80%
EM:    0.80%
Err:   1.60%
Hall:  1.40%
```

## BIRD Union Cost Curves

Retrospective union curves reuse saved candidate pools and select at different candidate
budgets. They are useful for offline analysis and verifier development, but they should
not be presented as fresh single-run generation results.

### Seven-Pool Union

Pools: default, temp `1.0`, temp `0.9`, temp `0.85`, temp `0.92`, temp `0.9b`, temp `0.9c`.

Artifact: [summary](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev_vav_n140_union_t075_t10_t09_t085_t092_t09b_t09c_cost_curve_vav/summary.json)

| Budget | EM | EX | Err | Hall |
| ---: | ---: | ---: | ---: | ---: |
| n=20 | 0.80% | 46.40% | 1.60% | 1.80% |
| n=40 | 0.80% | 46.60% | 1.60% | 1.20% |
| n=60 | 0.80% | 48.20% | 1.60% | 1.20% |
| n=80 | 0.80% | 48.40% | 1.60% | 1.20% |
| n=100 | 1.00% | 48.20% | 1.60% | 1.20% |
| n=120 | 1.00% | 47.60% | 1.60% | 1.60% |
| n=140 | 1.00% | 48.00% | 1.40% | 1.40% |

### Eight-Pool Union

Pools: the seven-pool union plus value-grounded temp `0.9`.

Artifact: [summary](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev_vav_n160_union_t075_t10_t09_t085_t092_t09b_t09c_vg09_cost_curve_vav/summary.json)

| Budget | EM | EX | Err | Hall |
| ---: | ---: | ---: | ---: | ---: |
| n=20 | 0.80% | 46.40% | 1.60% | 1.80% |
| n=40 | 0.80% | 46.60% | 1.60% | 1.20% |
| n=60 | 1.00% | 47.60% | 1.60% | 1.60% |
| n=80 | 1.00% | 47.60% | 1.60% | 1.60% |
| n=100 | 1.00% | 48.20% | 1.40% | 1.40% |
| n=120 | 1.00% | 48.40% | 1.60% | 1.40% |
| n=140 | 1.00% | 48.00% | 1.60% | 1.40% |
| n=160 | 1.00% | 48.00% | 1.60% | 1.40% |

The eight-pool curve ties the seven-pool best but does not improve it.

## Training Efficiency

| Adapter | Dense MFU | LoRA-est. MFU | Tokens/s | Step | Target met | Artifact |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Direct Spider LoRA | 65.98% | - | 1725.46 | 48 | - | [perf](outputs/direct_spider_qwen25_coder_7b_l20_mfu/perf.summary.json) |
| Schema-aware Spider LoRA | 73.22% | 48.81% | 1914.90 | 64 | yes | [perf](outputs/schema_aware_spider_qwen25_coder_7b_l20_mfu/perf.summary.json) |
| Rich-context Spider LoRA | 66.34% | - | 1734.91 | 96 | - | [perf](outputs/rich_context_spider_qwen25_coder_7b_l20_mfu/perf.summary.json) |
| Candidate-repair LoRA | 61.73% | - | 1614.37 | 180 | - | [perf](outputs/candidate_repair_spider_qwen25_coder_7b_l20_mfu/perf.summary.json) |

## Reproduce

### Install

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[train]"
```

### Prepare Data

Spider and BIRD source data are expected under local dataset directories. The prepared
JSONL files used by the saved results live under `data/processed/`.

```bash
python -m nl2sql_l20.prepare spider \
  --root /path/to/spider \
  --split dev \
  --out data/processed/spider_dev_no_value_hints.jsonl
```

### Run a Benchmark Suite

```bash
python -m nl2sql_l20.benchmark_suite \
  --experiment configs/experiment_rich_context_spider_l20_mfu.yaml \
  --suite configs/benchmarks_after_train.yaml \
  --adapter outputs/rich_context_spider_qwen25_coder_7b_l20_mfu
```

### Run a Retrospective Cost Curve

```bash
python -m nl2sql_l20.cost_curve \
  --gold data/processed/bird_mini_dev_no_value_hints.jsonl \
  --pred evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev_vav_n20_t09/predictions.jsonl \
  --out evals/sota/example_cost_curve \
  --budgets 4,8,12,16,20 \
  --selection-strategy value_aware_voting
```

### Export Spider Official Evaluation Files

```bash
python -m nl2sql_l20.export_spider \
  --gold data/processed/spider_dev_no_value_hints.jsonl \
  --pred evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_vav_n30/predictions.jsonl \
  --out evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_vav_n30/spider_official
```

The helper script `scripts/run_spider_official_eval.sh` runs the upstream Spider evaluator
when a local checkout of the official evaluator is available.

## Repository Map

| Path | Purpose |
| --- | --- |
| `configs/` | Training, inference, benchmark-suite, and follow-up experiment configs |
| `src/nl2sql_l20/` | Data prep, training, inference, voting, repair, export, and evaluation code |
| `scripts/` | Local and remote run helpers |
| `evals/after_train/` | Single-adapter post-training benchmark outputs |
| `evals/sota/` | Multi-candidate, EGS, repair, union, and cost-curve outputs |
| `outputs/` | LoRA adapter outputs and performance summaries |
| `docs/` | Deeper experiment notes and architecture documentation |
| `tests/` | Unit tests for prompt selection, pipeline behavior, repair, and cost curves |

## Result Interpretation

- Rich-context prompting improved Spider single-candidate EX from `75.73%` to `78.72%`.
- Multi-candidate selection was the main Spider gain: VAV n=4 retrospective reached
  `82.20%` official EX and EGS n=32 reached `82.00%` official EX.
- On BIRD, schema-aware and rich-context prompting removed much of the direct-transfer
  execution failure rate, but strict EM stayed low because BIRD SQL forms diverge from
  Spider-style supervision.
- BIRD value-aware voting n=20 at temperature `0.9` is the best fresh generation result.
- Larger unions still contain useful complementary candidates, but the gains are small
  and retrospective. They are best treated as verifier/reranker development signal.
- Candidate repair reduced some hallucination/error rates but hurt BIRD execution
  accuracy relative to VAV, so it is a negative ablation for this snapshot.
- Value-grounded BIRD-specific prompts did not improve fresh BIRD EX in the final run.

## References

- [Spider official benchmark](https://yale-lily.github.io/spider)
- [BIRD official benchmark](https://bird-bench.github.io/)
- [Qwen2.5-Coder model family](https://qwenlm.github.io/blog/qwen2.5-coder-family/)
- [GitHub Docs: About README files](https://docs.github.com/en/enterprise-cloud@latest/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes)
- [Google README style guide](https://google.github.io/styleguide/docguide/READMEs.html)

## License

MIT. See [LICENSE](LICENSE).
